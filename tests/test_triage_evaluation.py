"""Saved-run checks for coverage, reference revisions, and response integrity."""

import json
from pathlib import Path
import tempfile
import unittest

from mofinder.evaluation.triage import evaluate_run, load_saved_run, select_saved_run
from mofinder.literature.triage import GT_COLUMNS, save_csv


def reference(doi, consensus):
    row = dict.fromkeys(GT_COLUMNS, "")
    row.update({"DOI": doi, "Consensus GT": consensus, "Resolution method": "Unanimous"})
    row.update({f"Annotator {i}": consensus for i in range(1, 5)})
    return row


class SavedRunEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / "runs" / "screening"
        self.run.mkdir(parents=True)
        self.ground_truth_file = self.root / "current_reference.csv"
        self.reference = [reference(f"10.1234/{letter}", label)
                          for letter, label in zip("abcd", "YNYY")]
        save_csv(self.reference, self.ground_truth_file, GT_COLUMNS)
        screening_reference = [dict(row) for row in self.reference]
        screening_reference[1]["Consensus GT"] = "Y"
        save_csv(screening_reference, self.run / "reference_used.csv", GT_COLUMNS)
        save_csv([{"DOI": "10.1234/d", "Reason": "Empty abstract"}],
                 self.run / "reference_not_screened.csv", ["DOI", "Reason"])
        self.rows = []
        for name, labels in [("A", "YY"), ("B", "NN")]:
            for letter, label in zip("ab", labels):
                self.rows.append({"Run ID": "screening", "DOI": f"10.1234/{letter}",
                                  "Configuration": name, "Round": 1, "Agent_YN": label,
                                  "Status": "ok"})
            self.rows.append({"Run ID": "screening", "DOI": "10.1234/c",
                              "Configuration": name, "Round": 1, "Agent_YN": "",
                              "Status": "error", "Error": "Recorded test failure"})
        self.manifest = {
            "run_id": "screening", "completed": True, "models": [{"name": "A"}, {"name": "B"}],
            "rounds": 1, "recorded_requests": len(self.rows), "scheduled_publications": 3,
            "reference_publications": 4, "benchmark_only": True,
            "created_utc": "2026-01-01T00:00:00+00:00",
        }
        self.write_run()

    def write_run(self):
        (self.run / "run_manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.run / "responses.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8"
        )

    def test_reference_revision_failures_and_pairs_keep_their_denominators(self):
        original = {path: path.read_bytes() for path in self.run.iterdir()}
        context = evaluate_run(load_saved_run(self.run, self.ground_truth_file, bootstraps=200))
        for result in context["metrics"]:
            self.assertEqual(result["Reference N"], 4)
            self.assertEqual(result["Scheduled reference N"], 3)
            self.assertEqual(result["Scored N"], 2)
            self.assertEqual(result["Unscored reference N"], 2)
            self.assertEqual(result["Coverage of reference"], 0.5)
            self.assertEqual(result["Accuracy"], 0.5)
        first = context["metrics"][0]
        self.assertEqual((first["TP"], first["FP"], first["TN"], first["FN"]), (1, 1, 0, 0))
        self.assertEqual(context["ground_truth_changes"], [{
            "DOI": "10.1234/b", "Screening-time GT": "Y", "Current GT": "N", "Change": "Label changed"
        }])
        unscored = [row for row in context["paper_results"] if row["Outcome"] == "Unscored"]
        self.assertEqual(len(unscored), 4)
        self.assertEqual({row["Status"] for row in unscored}, {"error", "not_screened"})
        for comparison in context["paired_comparisons"]:
            self.assertEqual(comparison["Common scored N"], 2)
            self.assertEqual(comparison["A correct only"], 1)
            self.assertEqual(comparison["B correct only"], 1)
            self.assertEqual(comparison["McNemar exact p (accuracy; unadjusted)"], 1)
        self.assertEqual(len(list(context["output_dir"].glob("*.csv"))), 17)
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_journal_takes_precedence_over_stale_csv_and_csv_fallback_works(self):
        save_csv(self.rows[:1], self.run / "predictions.csv")
        context = load_saved_run(self.run, self.ground_truth_file, bootstraps=20)
        self.assertEqual(context["prediction_source"].name, "responses.jsonl")
        self.assertEqual(len(context["rows"]), 6)
        (self.run / "responses.jsonl").unlink()
        save_csv(self.rows, self.run / "predictions.csv")
        csv_context = load_saved_run(self.run, self.ground_truth_file, bootstraps=20)
        self.assertEqual(csv_context["prediction_source"].name, "predictions.csv")
        self.assertEqual(csv_context["rows"][0]["Round"], 1)

    def test_duplicate_predictions_are_rejected_before_analysis_is_written(self):
        self.rows.append(dict(self.rows[0]))
        self.manifest["recorded_requests"] = len(self.rows)
        self.write_run()
        with self.assertRaisesRegex(ValueError, "Duplicate saved prediction"):
            load_saved_run(self.run, self.ground_truth_file)
        self.assertFalse(list(self.run.glob("analysis_*")))

    def test_missing_response_is_unscored_when_scheduled_doi_is_recoverable(self):
        self.rows = [row for row in self.rows if row["DOI"] != "10.1234/c"]
        self.manifest["recorded_requests"] = len(self.rows)
        self.write_run()
        context = evaluate_run(load_saved_run(self.run, self.ground_truth_file, bootstraps=20))
        missing = [row for row in context["paper_results"] if row["Normalized DOI"] == "10.1234/c"]
        self.assertEqual({row["Status"] for row in missing}, {"not_returned"})
        self.assertEqual({row["Scheduled reference N"] for row in context["metrics"]}, {3})

    def test_latest_selection_skips_incomplete_screening(self):
        incomplete = self.root / "runs" / "incomplete"
        incomplete.mkdir()
        (incomplete / "run_manifest.json").write_text(json.dumps({
            **self.manifest, "completed": False, "created_utc": "2026-02-01T00:00:00+00:00"
        }), encoding="utf-8")
        (incomplete / "responses.jsonl").write_text(json.dumps(self.rows[0]) + "\n", encoding="utf-8")
        self.assertEqual(select_saved_run(self.root / "runs"), self.run.resolve())


if __name__ == "__main__":
    unittest.main()
