"""Offline checks for fixed-panel model requests and saved-round statistics."""

import asyncio
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

HAS_DEPS = all(importlib.util.find_spec(name) for name in ("pandas", "numpy", "sklearn"))


def chat_choice(text="P", logp=-.2, logn=-1.7):
    return NS(message=NS(content=text), logprobs=NS(content=[
        NS(token=" " + text, logprob=logp if text == "P" else logn,
           top_logprobs=[NS(token="P", logprob=logp), NS(token="N", logprob=logn)])]))


@unittest.skipUnless(HAS_DEPS, "Install the evaluation extra for evaluation tests.")
class QuestEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mofinder.evaluation import quest
        cls.module = quest
        cls.repo = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.module.load_config(self.repo / "configs/quest_evaluation.json")

    def test_panel_conditions_only_messages(self):
        questions = self.module.load_questions(self.config["questions_file"])
        self.assertEqual(len(questions), 22)
        self.assertEqual(sum(q["label"] == "P" for q in questions), 11)
        self.assertEqual(questions[1]["time_h"], 144)
        self.assertEqual(questions[1]["metal_precursor"], "ZrOCl2·8H2O")
        self.assertEqual(questions[12]["time_h"], 24)
        with (self.repo / "benchmarks/mof_quest/human_questions.csv").open(encoding="utf-8", newline="") as stream:
            human_questions = {row["reaction_id"]: row for row in csv.DictReader(stream)}
        self.assertEqual(set(human_questions), {q["reaction_id"] for q in questions})
        items = self.module.build_items_from_manual_questions(questions)
        for q, item in zip(questions, items):
            condition = json.loads(item["user_text"])
            human = human_questions[q["reaction_id"]]
            self.assertEqual(condition, json.loads(human["conditions_json"]))
            self.assertEqual(q["label"], human["label"])
            self.assertEqual(tuple(condition), self.module.CONDITION_FIELDS)
            self.assertEqual(condition, {key: q[key] for key in self.module.CONDITION_FIELDS})
            self.assertEqual(item["messages"], [{"role": "system", "content": item["system_text"]},
                                                {"role": "user", "content": item["user_text"]}])
            self.assertEqual(item["reaction_id"], q["reaction_id"])
        self.assertEqual(items[0]["system_text"], self.config["prompt_file"].read_text())

    def test_validation_no_api_or_output_and_source_group_constraints(self):
        self.config["output_root"] = self.root / "not-created"
        with patch.dict("sys.modules", {"openai": None}):
            report = self.module.validate_config(self.config)
        self.assertFalse(self.config["output_root"].exists())
        self.assertTrue(report["groups"][self.config["default_group"]]["valid"])
        self.assertTrue(report["groups"]["nonreasoning"]["valid"])
        self.assertTrue(report["groups"]["nonreasoning_web"]["warnings"])
        self.assertEqual(report["groups"]["latest_fine_tuned"]["requests"], 440)

    def test_chat_request_parity_and_web_flag_branch(self):
        request = AsyncMock(return_value=NS(choices=[chat_choice()]))
        client = NS(chat=NS(completions=NS(create=request)))
        messages = [{"role": "system", "content": "classify"}, {"role": "user", "content": "{}"}]
        text, choice, backend = asyncio.run(self.module.call_model_generic(
            "gpt-4.1", "classify", "{}", messages, "none", True, client=client))
        self.assertEqual((text, backend), ("P", "chat"))
        self.assertEqual(request.call_args.kwargs, dict(model="gpt-4.1", messages=messages,
                         temperature=0, top_p=1, max_tokens=2, logprobs=True,
                         top_logprobs=5, seed=7))
        lp_p, lp_n, argmax = self.module.extract_logprobs_for_label_chat(choice, "P")
        self.assertEqual((lp_p, lp_n, argmax), (-.2, -1.7, True))
        p, n = self.module.prob_from_pair(lp_p, lp_n)
        self.assertAlmostEqual(p + n, 1)
        self.assertAlmostEqual(p, 0.8175744761936437)
        self.assertEqual(self.module.prob_from_pair(None, -1), (None, None))

    def test_responses_request_effort_and_web_parity(self):
        request = AsyncMock(return_value=NS(output_text=" N "))
        client = NS(responses=NS(create=request))
        result = asyncio.run(self.module.call_model_generic(
            "gpt-5", " classify ", '{"time_h": 2}', [], "high", True, client=client))
        self.assertEqual(result, ("N", None, "responses"))
        self.assertEqual(request.call_args.kwargs, dict(model="gpt-5",
            input='classify\n\nReaction conditions as JSON:\n{"time_h": 2}',
            reasoning={"effort": "high"}, tools=[{"type": "web_search"}]))
        asyncio.run(self.module.call_model_generic(
            "gpt-5.1", "classify", "{}", [], "none", False, client=client))
        self.assertEqual(request.call_args.kwargs, dict(model="gpt-5.1", input="classify\n\nReaction conditions as JSON:\n{}"))

    def test_response_text_fallback_never_parses_metadata(self):
        m = self.module
        self.assertEqual(m.extract_text_from_responses_obj(NS(output=[NS(content=[NS(text="P")])])), "P")
        self.assertEqual(m.extract_text_from_responses_obj(NS(model_dump=lambda: {"output": [{"content": [{"text": "N"}]}]})), "N")
        self.assertEqual(m.extract_text_from_responses_obj(NS(model_dump=lambda: {"type": "response", "status": "incomplete"})), "")
        self.assertEqual(m.extract_text_from_responses_obj(NS(id="resp_P")), "")

    def test_label_parsing_and_valid_only_metric_denominator(self):
        m = self.module
        # The parser returns the first P/N character in response text.
        for text, expected in [("P", "P"), (" n ", "N"), ("Label: P", "P"), ("", ""), ("?", "")]:
            self.assertEqual(m.parse_pred_label(text), expected)
        result = m.running_metrics([{"gold_label": "P", "pred_label": "P"},
                                    {"gold_label": "N", "pred_label": "P"},
                                    {"gold_label": "P", "pred_label": ""}])
        self.assertEqual(result["accuracy"], .5)
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], 1)
        self.assertAlmostEqual(result["f1"], 2 / 3)

    def test_retry_counts_and_empty_failed_result(self):
        request = AsyncMock(side_effect=RuntimeError("controlled fixture"))
        client = NS(chat=NS(completions=NS(create=request)))
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()) as sleep:
            result = asyncio.run(self.module.call_model_chat("fixture", [], retries=3, client=client))
        self.assertEqual(result, ("", None))
        self.assertEqual(request.await_count, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 2, 4])

    def test_two_round_rows_metrics_and_reanalysis(self):
        questions = self.module.load_questions(self.config["questions_file"])
        questions = [questions[0], questions[11]]
        responses = iter(["P", "N", "N", "?"])
        async def create(**kwargs):
            return NS(choices=[chat_choice(next(responses))])
        client = NS(chat=NS(completions=NS(create=create)))
        with contextlib.redirect_stdout(io.StringIO()):
            summary = asyncio.run(self.module.evaluate_mof_classifier(
                ["fixture-model"], rounds=2, out_dir=self.root / "run", max_concurrency=1,
                manual_questions=questions, client=client, reasoning_effort="none"))
        paths = list((self.root / "run").glob("*.csv"))
        self.assertEqual(len(paths), 1)
        saved = self.module.pd.read_csv(paths[0], keep_default_na=False)
        self.assertEqual(len(saved), 4)
        self.assertEqual(saved["reaction_id"].tolist(), [questions[0]["reaction_id"], questions[1]["reaction_id"]] * 2)
        self.assertEqual(saved["error"].tolist()[-1], "no_extra_or_bad_label")
        source = summary["fixture-model"]
        self.assertEqual(source["mean"]["accuracy"], .5)
        self.assertEqual(source["std"]["accuracy"], .5)
        analyzed = next(iter(self.module.analyze_results(paths).values()))
        for key in ("round_metrics", "mean", "std"):
            self.assertEqual(source[key], analyzed[key])
        self.assertEqual(analyzed["round_counts"], [{"total": 2, "scored": 2, "unscored": 0}, {"total": 2, "scored": 1, "unscored": 1}])

    def test_invalid_request_group_fails_before_client_and_writes(self):
        self.config["groups"]["nonreasoning"]["model_ids"] = ["gpt-5"]
        with patch.dict("sys.modules", {"openai": None}):
            with self.assertRaises(ValueError):
                asyncio.run(self.module.run_evaluation(self.config, "nonreasoning", output_dir=self.root / "out"))
        self.assertFalse((self.root / "out").exists())

    def test_configured_run_records_manifest_and_preserves_outputs(self):
        self.config["groups"]["latest_fine_tuned"]["rounds"] = 1
        request = AsyncMock(return_value=NS(choices=[chat_choice()]))
        client = NS(chat=NS(completions=NS(create=request)))
        destination = self.root / "configured"
        with contextlib.redirect_stdout(io.StringIO()):
            result = asyncio.run(self.module.run_evaluation(
                self.config, client=client, output_dir=destination))
        self.assertEqual(request.await_count, 22)
        manifest = json.loads((destination / "run_manifest.json").read_text())
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["settings"]["rounds"], 1)
        self.assertEqual(manifest["settings"]["seed"], 7)
        self.assertEqual(result["output_dir"], destination)
        self.assertTrue((destination / "metrics_summary.json").is_file())
        saved = self.module.pd.read_csv(next(destination.glob("*.csv")))
        self.assertEqual(set(saved["web_search_enabled"]), {False})
        with self.assertRaisesRegex(ValueError, "empty output directory"):
            asyncio.run(self.module.run_evaluation(self.config, client=client, output_dir=destination))
        self.assertEqual(request.await_count, 22)

    def test_question_ids_are_not_assumed_to_encode_all_conditions(self):
        records = json.loads(self.config["questions_file"].read_text())
        records[1]["reaction_id"] = records[0]["reaction_id"]
        path = self.root / "questions.json"
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.module.load_questions(path)


if __name__ == "__main__":
    unittest.main()
