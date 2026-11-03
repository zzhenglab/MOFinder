"""Offline checks for publication identity, human labels, and statistics."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from mofinder.literature import triage


def reference(doi, consensus="Y", annotations=("Y", "Y", "Y", "Y")):
    row = dict.fromkeys(triage.GT_COLUMNS, "")
    row.update({"DOI": doi, "Consensus GT": consensus})
    row.update({f"Annotator {i}": value for i, value in enumerate(annotations, 1)})
    return row


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def validate(self, ground_truth, metadata, **kwargs):
        gt_file, metadata_file = self.folder / "reference.csv", self.folder / "metadata.csv"
        triage.save_csv(ground_truth, gt_file, triage.GT_COLUMNS)
        triage.save_csv(metadata, metadata_file, ["DOI", "Title", "Abstract"])
        return triage.validate_inputs(metadata_file, gt_file, **kwargs)

    def test_consensus_is_preserved_independently_of_votes(self):
        ground_truth = [reference("10.1234/a", "N", ("Y", "Y", "Y", "N"))]
        data = self.validate(ground_truth, [{"DOI": "https://doi.org/10.1234/A", "Abstract": "Text"}])
        self.assertEqual(data["ground_truth_by_doi"]["10.1234/a"]["Consensus GT"], "N")
        self.assertEqual(triage.votes(data["ground_truth"][0]), (3, 1))
        self.assertEqual(triage.validation_summary(data)["consensus_counts"], {"N": 1})
        self.assertNotIn("Consensus GT", data["papers"][0])

    def test_ambiguous_ratings_are_not_binary_votes(self):
        row = reference("10.1234/a", annotations=("Y", "Y/N", "", "N"))
        self.assertEqual(triage.votes(row), (1, 1))
        report = triage.human_agreement([row], bootstraps=20)
        self.assertEqual(report[0]["Binary ratings"], 2)
        self.assertEqual(report[0]["Ambiguous or missing ratings"], 2)
        self.assertEqual(report[0]["Complete four-binary-rating papers"], 0)
        self.assertEqual(report[0]["Estimate"], 0.0)

    def test_missing_abstracts_retain_the_reference_denominator(self):
        ground_truth = [reference(f"10.1234/{letter}") for letter in "abcd"]
        metadata = [
            {"DOI": "10.1234/a", "Abstract": "First abstract"},
            {"DOI": "10.1234/b", "Abstract": "   "},
            {"DOI": "10.1234/c", "Abstract": "Third abstract"},
        ]
        data = self.validate(ground_truth, metadata, max_papers=1)
        self.assertEqual(triage.validation_summary(data)["reference_publications"], 4)
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual({row["DOI"]: row["Reason"] for row in data["missing_reference"]}, {
            "10.1234/b": "Empty abstract",
            "10.1234/c": "Outside max_papers subset",
            "10.1234/d": "DOI absent from metadata",
        })

    def test_identical_duplicates_collapse_but_conflicts_raise(self):
        row = {"DOI": "10.1234/a", "Title": "Title", "Abstract": "Text"}
        data = self.validate([reference("10.1234/a")], [row, dict(row)])
        self.assertEqual(data["identical_duplicates"], 1)
        self.assertEqual(len(data["papers"]), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting metadata.*10.1234/a"):
            self.validate([reference("10.1234/a")], [row, {**row, "Abstract": "Different"}])

    def test_outside_benchmark_conflicts_are_explicit_in_full_scope(self):
        metadata = [
            {"DOI": "10.1234/a", "Abstract": "Reference"},
            {"DOI": "10.1234/b", "Abstract": "Outside"},
            {"DOI": "10.1234/b", "Abstract": "Conflicting outside"},
        ]
        data = self.validate([reference("10.1234/a")], metadata)
        self.assertEqual(data["paper_ids"], {"10.1234/a"})
        with self.assertRaisesRegex(ValueError, "Conflicting metadata.*10.1234/b"):
            self.validate([reference("10.1234/a")], metadata, benchmark_only=False)

    def test_ambiguous_consensus_and_duplicate_reference_fail(self):
        metadata = [{"DOI": "10.1234/a", "Abstract": "Text"}]
        with self.assertRaisesRegex(ValueError, "Non-binary consensus"):
            self.validate([reference("10.1234/a", "Y/N")], metadata)
        with self.assertRaisesRegex(ValueError, "Duplicate reference DOI"):
            self.validate([reference("10.1234/a"), reference("https://doi.org/10.1234/A")], metadata)


class StatisticsTests(unittest.TestCase):
    def test_confusion_metrics_match_hand_calculation(self):
        counts = triage.confusion([1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0])
        np.testing.assert_array_equal(counts, [2, 1, 2, 1])
        metrics = triage.metric_values(counts)
        for name in ["Accuracy", "Precision", "Recall", "Specificity", "F1", "Balanced accuracy", "NPV"]:
            self.assertAlmostEqual(float(metrics[name]), 2 / 3)
        self.assertAlmostEqual(float(metrics["MCC"]), 1 / 3)

    def test_undefined_metrics_remain_undefined(self):
        metrics = triage.metric_values([0, 0, 4, 0])
        self.assertEqual(float(metrics["Accuracy"]), 1)
        for name in ["Precision", "Recall", "F1", "Balanced accuracy", "MCC"]:
            self.assertTrue(np.isnan(metrics[name]), name)
        self.assertTrue(all(np.isnan(value) for value in triage.wilson(0, 0)))
        low, high = triage.wilson(5, 10)
        self.assertAlmostEqual(low, 0.236593090512564)
        self.assertAlmostEqual(high, 0.763406909487436)

    def test_agreement_uses_available_pairs_and_complete_cases(self):
        # Unanimous Y, unanimous N, a 3:1 split, then two disagreeing available ratings.
        values = triage.agreement_values([[4, 0], [0, 4], [3, 1], [1, 1]], [1, 1, 1, 1])
        self.assertAlmostEqual(float(values["Raw pairwise agreement (available ratings)"][0]), 15 / 19)
        self.assertAlmostEqual(float(values["Fleiss kappa (four binary ratings)"][0]), 23 / 35)
        self.assertAlmostEqual(float(values["Krippendorff alpha (available binary ratings)"][0]), 11 / 24)
        self.assertAlmostEqual(float(values["Four-rater unanimity / all papers"][0]), 0.5)


if __name__ == "__main__":
    unittest.main()
