"""Count-matched controls preserve the anchor distance, labels, and exclusions."""

from copy import deepcopy
import json
import unittest

from mofinder.datasets.artificial_control import (
    FIELDS, condition_key, generate_count_matched, inputs,
)


def record(values, label):
    return {"messages": [
        {"role": "system", "content": "Predict P or N."},
        {"role": "user", "content": json.dumps(values)},
        {"role": "assistant", "content": label},
    ]}


def source(values, row_number):
    return {
        "cluster_key": (f"metal={values[FIELDS[0]]}|linker={values[FIELDS[1]]}"
                        f"|solvent={values[FIELDS[3]]}"),
        "doi_norm": f"10.example/{row_number}",
    }


def fixture(change_counts=(1, 2, 3), null_modulator=False):
    positive_values = []
    for i in range(32):
        values = {field: (f"{field}-{i}" if j < 4 else float(10 * i + j))
                  for j, field in enumerate(FIELDS)}
        if null_modulator and i:
            values["modulator"] = None
        positive_values.append(values)
    train = [record(values, "P") for values in positive_values]
    neighbors = []
    for k in change_counts:
        values = positive_values[0].copy()
        for j, field in enumerate(FIELDS[:k]):
            values[field] = f"absent-{field}" if j < 4 else -1000.0
        train.append(record(values, "N"))
        neighbors.append({
            "baseline_row_1based": len(train), "nearest_positive_row_1based": 1,
            "changed_fields": list(FIELDS[:k]),
        })
    sources = {i: source(inputs(row), i) for i, row in enumerate(train, 1)}
    return train, [], neighbors, sources, {}


class CountMatchedControlTests(unittest.TestCase):
    def test_preserves_slots_prompts_and_anchor_counts_reproducibly(self):
        args = fixture()
        original = deepcopy(args)
        output, provenance, diagnostics = generate_count_matched(*args, seed=101)
        self.assertEqual((output, provenance, diagnostics),
                         generate_count_matched(*args, seed=101))
        self.assertEqual(args, original)
        self.assertEqual(len(output), len(args[0]))
        self.assertEqual(diagnostics["original_reference_count_histogram"], {1: 1, 2: 1, 3: 1})
        self.assertEqual(diagnostics["synthetic_reference_count_histogram"], {1: 1, 2: 1, 3: 1})
        self.assertGreater(diagnostics["different_original_mask_rows"], 0)
        donors = {field: {inputs(row)[field] for row in args[0][:32]} for field in FIELDS}
        for before, after in zip(args[0], output):
            self.assertEqual(before["messages"][0], after["messages"][0])
            self.assertEqual(before["messages"][2], after["messages"][2])
            if before["messages"][2]["content"] == "P":
                self.assertEqual(before, after)
        for item in provenance:
            anchor = inputs(args[0][item["reference_positive_row_1based"] - 1])
            candidate = inputs(output[item["baseline_row_1based"] - 1])
            actual = [field for field in FIELDS if anchor[field] != candidate[field]]
            self.assertEqual(actual, item["changed_fields"])
            self.assertEqual(len(actual), item["n_changed_fields"])
            self.assertEqual(len(actual), len(item["original_changed_fields"]))
            for field in actual:
                self.assertIn(candidate[field], donors[field])
        self.assertEqual(diagnostics["known_training_condition_collisions"], 0)
        self.assertEqual(diagnostics["unique_synthetic_negatives"], 3)

    def test_null_is_available_as_an_empirical_positive_donor(self):
        output, provenance, diagnostics = generate_count_matched(
            *fixture((8,), null_modulator=True), seed=101)
        self.assertIsNone(inputs(output[-1])["modulator"])
        self.assertEqual(provenance[0]["n_changed_fields"], 8)
        self.assertTrue(diagnostics["null_donors_allowed"])

    def test_original_negative_field_identities_and_values_do_not_control_draws(self):
        args = fixture((2,))
        expected, _, _ = generate_count_matched(*args, seed=101)
        # Replace two originally changed reagent fields with two numerical changes.
        # k and the positive anchor stay the same; generated inputs should too.
        modified = deepcopy(args)
        values = inputs(modified[0][0])
        values["temperature_C"] = -12345.0
        values["time_h"] = -98765.0
        modified[0][-1] = record(values, "N")
        modified[2][0]["changed_fields"] = ["temperature_C", "time_h"]
        actual, provenance, _ = generate_count_matched(*modified, seed=101)
        self.assertEqual(actual, expected)
        self.assertEqual(provenance[0]["original_changed_fields"], ["temperature_C", "time_h"])

    def test_extra_exclusion_retries_same_chosen_subset(self):
        args = fixture((3,))
        first, original_provenance, _ = generate_count_matched(*args, seed=101)
        excluded = condition_key(inputs(first[-1]))
        output, provenance, diagnostics = generate_count_matched(
            *args, seed=101, excluded_condition_keys={excluded})
        self.assertNotEqual(condition_key(inputs(output[-1])), excluded)
        self.assertEqual(provenance[0]["changed_fields"], original_provenance[0]["changed_fields"])
        self.assertGreater(provenance[0]["candidate_attempts"], 1)
        self.assertGreater(diagnostics["rejected_candidates"]["excluded_processed_condition"], 0)
        self.assertEqual(diagnostics["excluded_processed_condition_collisions"], 0)

    def test_holdout_conditions_and_clusters_are_excluded(self):
        args = fixture((8,))
        first, _, _ = generate_count_matched(*args, seed=101)
        forbidden_values = inputs(first[-1])
        holdout = [record(forbidden_values, "P")]
        holdout_sources = {1: source(forbidden_values, 1)}
        output, _, diagnostics = generate_count_matched(
            args[0], holdout, args[2], args[3], holdout_sources, seed=101)
        self.assertGreater(diagnostics["rejected_candidates"]["holdout_condition"], 0)
        self.assertEqual(diagnostics["holdout_condition_collisions"], 0)
        self.assertEqual(diagnostics["holdout_cluster_collisions"], 0)
        self.assertNotEqual(source(inputs(output[-1]), 1)["cluster_key"],
                            holdout_sources[1]["cluster_key"])

    def test_impossible_fixed_subset_fails_without_relaxation(self):
        args = fixture((1,))
        anchor = inputs(args[0][0])
        donor = anchor.copy()
        donor[FIELDS[0]] = "alternative metal"
        negative = anchor.copy()
        negative[FIELDS[0]] = "original negative metal"
        train = [record(anchor, "P"), record(donor, "P"), record(negative, "N")]
        sources = {i: source(inputs(row), i) for i, row in enumerate(train, 1)}
        neighbors = [{"baseline_row_1based": 3, "nearest_positive_row_1based": 1,
                      "changed_fields": [FIELDS[0]]}]
        with self.assertRaisesRegex(ValueError, "donor support exhausted.*No mask or exclusion was relaxed"):
            generate_count_matched(train, [], neighbors, sources, {}, seed=101)


if __name__ == "__main__":
    unittest.main()
