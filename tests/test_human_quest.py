"""Question-ID alignment and scoring of deidentified human responses."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from mofinder.evaluation.human_quest import (
    analyse, compare_panels, load_benchmark, wilson_interval, write_analysis,
)


ROOT = Path(__file__).resolve().parents[1]


def response(participant, reaction, answer, experience="1-3 years", score=""):
    return {"participant_id": participant, "reaction_id": reaction, "response": answer,
            "experience": experience, "stored_score": score}


class HumanQuestTests(unittest.TestCase):
    def setUp(self):
        self.questions = [{"question": "Q1", "reaction_id": "rxn_a", "label": "P"},
                          {"question": "Q2", "reaction_id": "rxn_b", "label": "N"}]

    def test_randomised_response_order_is_aligned_by_reaction_id(self):
        rows = [response("P002", "rxn_b", "Likely Fail"),
                response("P001", "rxn_a", "Very Confident Success"),
                response("P002", "rxn_a", "Likely Success"),
                response("P001", "rxn_b", "Very Confident Fail")]
        result = analyse(self.questions, rows)
        reverse = analyse(list(reversed(self.questions)), list(reversed(rows)))
        self.assertEqual(result["summary"], reverse["summary"])
        self.assertEqual(result["summary"]["accuracy"], 1)
        self.assertEqual([row["correct"] for row in result["participants"]], [2, 2])

    def test_confidence_does_not_reverse_negative_predictions(self):
        rows = [response("P001", "rxn_a", "Very Confident Fail"),
                response("P001", "rxn_b", "Likely Success"),
                response("P002", "rxn_a", "Likely Success"),
                response("P002", "rxn_b", "Very Confident Fail")]
        result = analyse(self.questions, rows)
        very_confident = next(row for row in result["confidence"]
                              if row["experience"] == "Overall" and row["confidence"] == "Very Confident")
        self.assertEqual((very_confident["responses"], very_confident["correct"]), (2, 1))
        self.assertEqual(result["summary"]["tied_questions"], 2)
        self.assertIsNone(result["summary"]["majority_accuracy"])

    def test_missing_answers_use_answered_denominator(self):
        result = analyse(self.questions, [response("P001", "rxn_b", "Likely Fail")])
        self.assertEqual(result["participants"][0]["missing"], 1)
        self.assertEqual(result["participants"][0]["accuracy"], 1)
        self.assertIsNone(result["questions"][0]["accuracy"])
        self.assertIsNone(result["summary"]["fleiss_kappa"])

    def test_invalid_or_ambiguous_mappings_fail(self):
        valid = response("P001", "rxn_a", "Likely Success")
        for rows in ([valid, valid], [response("P001", "rxn_missing", "Likely Success")],
                     [response("P001", "rxn_a", "Maybe")],
                     [valid, response("P001", "rxn_b", "Likely Fail", experience=">3 years")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                analyse(self.questions, rows)
        with self.assertRaises(ValueError):
            analyse(self.questions + [self.questions[0]], [valid])

    def test_wilson_values_match_source_workbook(self):
        low, high = wilson_interval(80, 98)
        self.assertAlmostEqual(low, 0.7282500277598462)
        self.assertAlmostEqual(high, 0.8805393662448049)
        self.assertEqual(wilson_interval(0, 0), (None, None))
        self.assertAlmostEqual(wilson_interval(0, 5)[0], 0)
        self.assertAlmostEqual(wilson_interval(5, 5)[1], 1)
        with self.assertRaises(ValueError):
            wilson_interval(2, 1)

    def test_packaged_cohort_matches_raw_source_counts(self):
        result = load_benchmark(ROOT / "benchmarks/mof_quest/human_questions.csv",
                                ROOT / "benchmarks/mof_quest/human_responses.csv")
        self.assertEqual(result["summary"]["participants"], 98)
        self.assertEqual(result["summary"]["responses"], 2156)
        self.assertEqual(result["summary"]["correct"], 1118)
        self.assertEqual(result["summary"]["stored_score_mismatches"], 0)
        self.assertAlmostEqual(result["summary"]["accuracy"], 1118 / 2156)
        self.assertEqual([row["participants"] for row in result["experience"]], [30, 29, 39, 98])
        self.assertEqual([row["responses"] for row in result["confidence"][:4]], [283, 1019, 653, 201])
        self.assertEqual([row["correct"] for row in result["questions"]],
                         [80, 72, 77, 67, 64, 60, 48, 61, 50, 45, 47, 48, 55, 42, 51, 47, 52, 38, 33, 32, 27, 22])
        with tempfile.TemporaryDirectory() as directory:
            write_analysis(result, directory)
            summary = json.loads((Path(directory) / "summary.json").read_text())
            self.assertEqual(summary, result["summary"])
            with (Path(directory) / "participants.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 98)

    def test_packaged_exports_contain_only_anonymous_scientific_fields(self):
        path = ROOT / "benchmarks/mof_quest/human_responses.csv"
        with path.open() as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(set(reader.fieldnames),
                             {"participant_id", "experience", "reaction_id", "response", "stored_score"})
            rows = list(reader)
        self.assertTrue(all(row["participant_id"].startswith("P") for row in rows))
        self.assertNotIn("@", path.read_text())

    def test_interrater_statistics_match_independent_two_item_example(self):
        rows = [response("P001", "rxn_a", "Likely Success"),
                response("P002", "rxn_a", "Likely Success"),
                response("P001", "rxn_b", "Likely Success"),
                response("P002", "rxn_b", "Likely Fail")]
        result = analyse(self.questions, rows)["summary"]
        # Item agreements are 1 and 0; the pooled positive fraction is 3/4.
        self.assertEqual(result["raw_pairwise_agreement"], 0.5)
        self.assertAlmostEqual(result["fleiss_kappa"], -1 / 3)
        self.assertAlmostEqual(result["krippendorff_alpha"], 0)
        self.assertAlmostEqual(result["gwet_ac1"], 0.2)

    def test_matching_ids_do_not_hide_changed_conditions(self):
        human = [{"question": "Q2", "reaction_id": "rxn_a", "label": "P",
                  "conditions_json": '{"time_h": 6}'}]
        model = [{"question": "Q2", "reaction_id": "rxn_a", "label": "P",
                  "conditions": {"time_h": 144}}]
        comparison = compare_panels(human, model)
        self.assertTrue(comparison["all_shared_labels_match"])
        self.assertEqual(comparison["condition_differences"][0]["differences"],
                         {"time_h": {"human": 6, "model": 144}})


if __name__ == "__main__":
    unittest.main()
