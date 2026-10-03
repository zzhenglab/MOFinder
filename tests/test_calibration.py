"""Hand-calculated calibration examples and complete-cohort validation."""
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from mofinder.evaluation import calibration as cal


class CalibrationMetricTests(unittest.TestCase):
    def test_perfect_and_confidently_wrong_predictions(self):
        perfect = cal.calibration_metrics([0, 1], [0, 1])
        self.assertEqual((perfect["ece"], perfect["brier"], perfect["accuracy"]), (0, 0, 1))
        wrong = cal.calibration_metrics([0, 1], [1, 0])
        self.assertEqual((wrong["ece"], wrong["brier"], wrong["accuracy"]), (1, 1, 0))

    def test_equal_width_boundaries_last_includes_one_and_ties_predict_p(self):
        # .49 belongs to bin 0, .5 and 1 belong to bin 1. Pooling .49 with
        # .5 instead would incorrectly cancel their opposite residuals.
        out = cal.calibration_metrics([0, 1, 1], [.49, .5, 1], bins=2)
        self.assertAlmostEqual(out["ece"], (.49 + .5)/3)
        self.assertAlmostEqual(out["brier"], (.49**2 + .5**2)/3)
        self.assertEqual(out["accuracy"], 1)
        self.assertEqual(cal.calibration_metrics([0], [.5])["accuracy"], 0)

    def test_ece_is_record_weighted_not_unweighted_bin_mean(self):
        out = cal.calibration_metrics([0, 0, 0, 0], [.1, .1, .1, .8], bins=2)
        self.assertAlmostEqual(out["ece"], (3*.1 + .8)/4)
        self.assertNotAlmostEqual(out["ece"], (.1 + .8)/2)
        self.assertAlmostEqual(out["brier"], (3*.01 + .64)/4)

    def test_within_bin_signed_residuals_cancel_before_absolute_value(self):
        self.assertEqual(cal.calibration_metrics([0, 1], [.5, .5])["ece"], 0)
        self.assertEqual(cal.calibration_metrics([0, 1], [.5, .5])["brier"], .25)

    def test_bad_arrays_and_bins_fail_without_dropping(self):
        for labels, p in [([], []), ([0], []), ([0], [math.nan]), ([0], [math.inf]),
                          ([0], [-.1]), ([0], [1.1]), ([2], [.1]), ([math.nan], [.1]),
                          ([[0]], [[.1]])]:
            with self.subTest(labels=labels, p=p), self.assertRaises(ValueError):
                cal.calibration_metrics(labels, p)
        for bins in [0, -1, 1.5, True]:
            with self.assertRaises(ValueError):
                cal.calibration_metrics([0], [.1], bins=bins)

    def test_two_token_normalization_is_stable_and_p_oriented(self):
        self.assertEqual(cal.token_probability(-1000, -1000), .5)
        self.assertAlmostEqual(cal.token_probability(math.log(.8), math.log(.2)), .8)
        self.assertEqual(cal.token_probability(0, -10000), 1)
        self.assertEqual(cal.token_probability(-10000, 0), 0)
        for p, n in [(math.nan, -1), (-1, math.inf), (-math.inf, -1), (None, -1)]:
            with self.assertRaises(ValueError):
                cal.token_probability(p, n)

    def test_cluster_bootstrap_matches_explicit_shared_draws_and_row_multiplicity(self):
        # Unequal cluster sizes distinguish DOI resampling from iid row draws
        # and equal weighting of cluster means. Two models share every draw.
        y = np.array([0, 0, 1, 1, 1, 0])
        models = {"a": np.array([.1, .2, .8, .6, .7, .4]),
                  "b": np.array([.9, .8, .2, .4, .3, .6])}
        groups = np.array(["A", "A", "A", "B", "C", "C"])
        n, seed = 200, 17
        result = cal.evaluate_predictions(y, models, dois=groups, bootstrap=n, seed=seed)
        rng = np.random.default_rng(seed)
        expected = {name: [] for name in models}
        members = [np.flatnonzero(groups == name) for name in sorted(set(groups))]
        for _ in range(n):
            rows = np.concatenate([members[j] for j in rng.integers(0, 3, size=3)])
            for name, p in models.items():
                # Direct record expansion independent of group aggregation.
                mask = np.floor(p[rows]*10).astype(int)
                ece = sum(abs(np.sum(y[rows][mask == b] - p[rows][mask == b])) for b in range(10))/len(rows)
                expected[name].append([np.mean((p[rows] >= .5) == y[rows]), ece,
                                       np.mean((p[rows]-y[rows])**2)])
        for name in models:
            bounds = np.quantile(expected[name], [.025, .975], axis=0)
            for i, metric in enumerate(["accuracy", "ece", "brier"]):
                np.testing.assert_allclose(result["models"][name][metric+"_ci95"], bounds[:, i], atol=1e-14)
        self.assertEqual(result["doi_groups"], 3)

    def test_bootstrap_requires_real_group_ids_and_paired_model_lengths(self):
        for dois in [None, ["A"], ["A", ""], ["A", "A"]]:
            with self.assertRaises(ValueError):
                cal.evaluate_predictions([0, 1], {"a": [.1, .9]}, dois=dois, bootstrap=10)
        with self.assertRaises(ValueError):
            cal.evaluate_predictions([0, 1], {"a": [.1, .9], "b": [.2]})


class CalibrationCSVTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "predictions.csv"
        self.rows = [{"record_id": str(i), "input_sha256": f"{i:064x}", "doi": f"paper-{i}", "y": y,
                      **{name: p for name in cal.DEFAULT_COLUMNS}}
                     for i, (y, p) in enumerate([(0, .1), (1, .8)], 1)]

    def write(self, rows=None):
        rows = self.rows if rows is None else rows
        with self.path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    def test_wide_csv_has_one_shared_complete_cohort(self):
        self.write()
        data = cal.load_predictions(self.path)
        self.assertEqual(tuple(data.probabilities), cal.DEFAULT_COLUMNS)
        np.testing.assert_array_equal(data.labels, [0, 1])
        self.assertEqual(data.dois, ("paper-1", "paper-2"))

    def test_missing_nonfinite_out_of_range_labels_and_duplicate_identities_fail(self):
        for column, value in [(cal.DEFAULT_COLUMNS[0], ""), (cal.DEFAULT_COLUMNS[1], "nan"),
                              (cal.DEFAULT_COLUMNS[2], "inf"), (cal.DEFAULT_COLUMNS[0], "1.01"),
                              ("y", "2"), ("doi", ""), ("record_id", "1"),
                              ("input_sha256", f"{1:064x}"), ("input_sha256", "not-a-hash")]:
            rows = [dict(row) for row in self.rows]; rows[1][column] = value
            self.write(rows)
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                cal.load_predictions(self.path)

    def test_actual_holdout_csv_columns_and_canonical_input_duplicates(self):
        rows = [{"example_index": i, "user_text": json.dumps({"temperature_C": 100+i}),
                 "gold_label": label, "prob_P": p} for i, label, p in [(0, "N", .2), (1, "P", .7)]]
        self.write(rows)
        data = cal.load_predictions(self.path, probability_columns=["prob_P"], label_column="gold_label")
        self.assertIsNone(data.dois)
        np.testing.assert_array_equal(data.labels, [0, 1])
        rows[1]["user_text"] = '{ "temperature_C" : 100 }'
        self.write(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate input"):
            cal.load_predictions(self.path, probability_columns=["prob_P"], label_column="gold_label")

    def test_cli_json_prints_metrics_and_writes_no_output_files(self):
        self.write()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cal.main(["--csv", str(self.path), "--json"])
        result = json.loads(output.getvalue())
        self.assertAlmostEqual(result["models"][cal.DEFAULT_COLUMNS[0]]["ece"], .15)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
