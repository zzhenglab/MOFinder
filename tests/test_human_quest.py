"""Question-ID alignment and scoring of deidentified human responses."""

import csv
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from zipfile import ZipFile

from mofinder.evaluation.human_quest import (
    analyse, compare_panels, export_workbook, load_benchmark, wilson_interval, write_analysis,
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

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "Install openpyxl for workbook export tests.")
    def test_workbook_export_reads_both_question_column_layouts(self):
        from openpyxl import Workbook

        for start_column, json_header, source_columns, id_column in (
            (15, "JSON", "O:T", "Q"),
            (16, "Current reaction JSON", "P:U", "R"),
        ):
            with self.subTest(source_columns=source_columns), tempfile.TemporaryDirectory() as directory:
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = "Sheet1"
                headers = ["Question Number", "DOI", "Questions", json_header,
                           "Difficulty Level?", "Ground Truth?"]
                for column, header in enumerate(headers, start_column):
                    sheet.cell(1, column, header)
                for number, reaction_id, label in ((1, "rxn_a", "P"), (2, "rxn_b", "N")):
                    messages = {"messages": [
                        {"role": "user", "content": json.dumps({"time_h": number * 72})},
                        {"role": "assistant", "content": label},
                    ]}
                    values = [number, "10.0000/example", reaction_id, json.dumps(messages), "easy", label]
                    for column, value in enumerate(values, start_column):
                        sheet.cell(number + 1, column, value)
                sheet.cell(5, 1, "outside question panel")
                responses = workbook.create_sheet("Sheet1.1 Responses")
                responses.append(["participant", "score", "question_ids"])
                responses.append(["anonymous", 2, json.dumps({
                    "User_Experience": "1-3 years", "rxn_b": "Likely Fail", "rxn_a": "Likely Success",
                })])
                responses.append(["outside response panel"])
                for name in ("Sheet1.2 Questions", "Sheet1.3 Calculations", "Sheet2 Summary"):
                    workbook.create_sheet(name)
                path = Path(directory) / "questions.xlsx"
                workbook.save(path)
                workbook.close()
                # The supplied workbook omits worksheet dimensions, so rows can be short.
                with ZipFile(path) as source:
                    members = [(member, source.read(member.filename)) for member in source.infolist()]
                with ZipFile(path, "w") as target:
                    for member, content in members:
                        if member.filename in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
                            content = re.sub(rb"<dimension\b[^>]*/>", b"", content)
                        target.writestr(member, content)
                output = Path(directory) / "export"
                manifest = export_workbook(path, output)
                self.assertEqual((manifest["questions"], manifest["responses"]), (2, 2))
                self.assertEqual(manifest["question_source"],
                                 f"Sheet1 columns {source_columns}, located by headers; "
                                 f"response mapping uses the reaction ID in column {id_column}.")
                with (output / "human_questions.csv").open(encoding="utf-8", newline="") as stream:
                    questions = list(csv.DictReader(stream))
                self.assertEqual([q["reaction_id"] for q in questions], ["rxn_a", "rxn_b"])
                self.assertEqual([q["label"] for q in questions], ["P", "N"])
                self.assertEqual(json.loads(questions[1]["conditions_json"]), {"time_h": 144})
                result = load_benchmark(output / "human_questions.csv", output / "human_responses.csv")
                self.assertEqual(result["summary"]["correct"], 2)


if __name__ == "__main__":
    unittest.main()
