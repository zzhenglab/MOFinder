"""Offline checks for P/N holdout requests, probabilities, metrics, and resume."""

import asyncio
import importlib.util
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

HAS_DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in ("pandas", "sklearn"))


def token(text, logprob, alternatives=()):
    return SimpleNamespace(token=text, logprob=logprob, top_logprobs=[
        SimpleNamespace(token=label, logprob=probability) for label, probability in alternatives
    ])


def choice(text, tokens=None):
    return SimpleNamespace(message=SimpleNamespace(content=text),
                           logprobs=SimpleNamespace(content=tokens or []))


def record(label="P", index=0):
    return {"messages": [
        {"role": "system", "content": "Return P or N."},
        {"role": "user", "content": json.dumps({"fixture_index": index, "temperature_C": 120})},
        {"role": "assistant", "content": label},
    ]}


@unittest.skipUnless(HAS_DEPENDENCIES, "Install the evaluation extra for holdout tests.")
class HoldoutEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mofinder.evaluation import holdout
        cls.module = holdout
        cls.repo = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.holdout = self.root / "holdout.jsonl"
        self.write_records([record("P", 0), record("N", 1)])
        self.settings = self.module.load_settings(self.repo / "configs/holdout_evaluation.json")
        self.settings.update(holdout_paths=[self.holdout], training_path=self.holdout,
                             output_dir=self.root / "out")

    def write_records(self, records):
        self.holdout.write_text("".join(json.dumps(rec) + "\n" for rec in records), encoding="utf-8")

    def client(self, choices):
        responses = [SimpleNamespace(choices=[ch]) for ch in choices]
        create = AsyncMock(side_effect=responses)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def run_mock(self, client, **kwargs):
        return asyncio.run(self.module.evaluate_holdout(
            "fixture-model", self.holdout, "fixture", self.root / "out", client=client, **kwargs
        ))

    def test_only_system_and_user_messages_are_sent(self):
        system, user, messages = self.module.build_messages(record())
        self.assertEqual(messages, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        self.assertEqual([m["role"] for m in messages], ["system", "user"])

    def test_only_standalone_pn_responses_are_accepted(self):
        expected = {" P ": "P", " n\n": "N", "cannot determine": "", "explanation": "",
                    "Label: P": "", "P or N": "", "N. More information needed": "", "?": "", "": ""}
        for text, label in expected.items():
            self.assertEqual(self.module.parse_pred_label(text), label)
        self.assertEqual(self.module.parse_pred_label(None), "")

    def test_selected_label_token_position_and_whitespace(self):
        ch = choice("P", [token("\n", -.01), token(" P", -.2, [(" N", -1.7)]), token("N", -.1)])
        lp_P, lp_N, argmax = self.module.extract_logprobs_for_label(ch, "P")
        self.assertEqual((lp_P, lp_N, argmax), (-.2, -1.7, True))
        p, n = self.module.prob_from_pair(lp_P, lp_N)
        self.assertAlmostEqual(p, math.exp(-.2) / (math.exp(-.2) + math.exp(-1.7)))
        self.assertAlmostEqual(p + n, 1.0)

    def test_missing_logprobs_and_stable_large_negative_values(self):
        self.assertEqual(self.module.extract_logprobs_for_label(choice("P"), "P"), (None, None, None))
        self.assertEqual(self.module.prob_from_pair(-.2, None), (None, None))
        self.assertEqual(self.module.prob_from_pair(-1000, -1000), (.5, .5))

    def test_token_fallback_attributes_probability_to_actual_token(self):
        # A fallback N token must not have its likelihood assigned to P.
        ch = choice("Explanation N", [token("N", -.2, [("P", -1.0), ("N", -.2)])])
        self.assertEqual(self.module.extract_logprobs_for_label(ch, "P"), (-1.0, -.2, False))
        ch = choice("N", [token("N", -.2)])
        self.assertEqual(self.module.extract_logprobs_for_label(ch, "P"), (None, -.2, None))

    def test_nonanswers_are_saved_without_scoring_and_not_reparsed_offline(self):
        result = self.run_mock(self.client([choice("explanation"), choice("cannot determine")]))
        self.assertEqual(result["scored_records"], 0)
        self.assertEqual(result["error_records"], 2)
        path = self.root / "out/fixture.csv"
        frame = self.module.pd.read_csv(path, keep_default_na=False)
        self.assertEqual(frame["model_output"].tolist(), ["explanation", "cannot determine"])
        self.assertEqual(frame["pred_label"].tolist(), ["", ""])
        # Archived CSVs retain their recorded labels during analysis.
        frame["pred_label"] = ["P", "N"]
        frame.to_csv(path, index=False)
        self.assertEqual(self.module.analyze_saved(path)["scored_records"], 2)

    def test_metric_denominator_and_unscored_coverage(self):
        rows = [dict(gold_label="P", pred_label="P", error=""),
                dict(gold_label="N", pred_label="P", error=""),
                dict(gold_label="P", pred_label="", error="no_choice_or_bad_label")]
        result = self.module.summarize_rows(rows)
        self.assertEqual(result["metrics"], {"accuracy": .5, "precision": .5, "recall": 1.0, "f1": 2/3})
        self.assertEqual((result["records"], result["scored_records"], result["unscored_records"]), (3, 2, 1))
        self.assertEqual(result["coverage"], 2/3)
        self.assertEqual(result["error_records"], 1)

    def test_validate_is_read_only_and_rejects_nonbinary_references(self):
        before = sorted(self.root.rglob("*"))
        result = self.module.validate_inputs(self.settings)
        self.assertEqual(result["labels"], {"N": 1, "P": 1})
        self.assertEqual(before, sorted(self.root.rglob("*")))
        self.write_records([record("unknown")])
        with self.assertRaisesRegex(ValueError, "outside P/N"):
            self.module.validate_inputs(self.settings)

    def test_request_parameters_output_and_offline_analysis(self):
        client = self.client([choice("P", [token("P", -.1, [("N", -2)])]), choice("N")])
        result = self.run_mock(client)
        self.assertEqual(result["new_records"], 2)
        self.assertEqual(result["metrics"]["accuracy"], 1.0)
        for call in client.chat.completions.create.call_args_list:
            self.assertEqual(set(call.kwargs), {"model", "messages", "temperature", "top_p", "max_tokens", "logprobs", "top_logprobs", "seed"})
            self.assertEqual(call.kwargs["model"], "fixture-model")
            self.assertEqual(call.kwargs["seed"], 7)
            self.assertEqual(call.kwargs["max_tokens"], 2)
            self.assertEqual([m["role"] for m in call.kwargs["messages"]], ["system", "user"])
        saved = self.module.analyze_saved(result["csv_path"])
        self.assertEqual(saved["metrics"], result["metrics"])
        self.assertTrue((self.root / "out/fixture.metrics.json").is_file())

    def test_resume_skips_all_recorded_attempts_and_rejects_changed_inputs(self):
        client = self.client([choice("?"), choice("N")])
        self.run_mock(client)
        other = self.client([])
        result = self.run_mock(other)
        other.chat.completions.create.assert_not_called()
        self.assertEqual(result["new_records"], 0)
        self.assertEqual(result["error_records"], 1)
        self.write_records([record("P", 99), record("N", 1)])
        with self.assertRaisesRegex(ValueError, "inputs or request settings changed"):
            self.run_mock(other)
        other.chat.completions.create.assert_not_called()

    def test_resume_rejects_different_model_or_seed(self):
        self.run_mock(self.client([choice("P"), choice("N")]))
        with self.assertRaisesRegex(ValueError, "inputs or request settings changed"):
            self.run_mock(self.client([]), seed=8)
        with self.assertRaisesRegex(ValueError, "inputs or request settings changed"):
            asyncio.run(self.module.evaluate_holdout("other", self.holdout, "fixture", self.root / "out", client=self.client([])))

    def test_resume_rejects_prior_label_parsing_protocol(self):
        self.run_mock(self.client([choice("P"), choice("N")]))
        path = self.root / "out/fixture.manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["signature"]["label_parser"], "standalone_pn_v1")
        del manifest["signature"]["label_parser"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        client = self.client([])
        with self.assertRaisesRegex(ValueError, "inputs or request settings changed"):
            self.run_mock(client)
        client.chat.completions.create.assert_not_called()

    def test_resume_rejects_missing_manifest_and_duplicate_saved_rows(self):
        self.run_mock(self.client([choice("P"), choice("N")]))
        manifest = self.root / "out/fixture.manifest.json"
        manifest_bytes = manifest.read_bytes()
        manifest.unlink()
        client = self.client([])
        with self.assertRaisesRegex(ValueError, "no run manifest"):
            self.run_mock(client)
        client.chat.completions.create.assert_not_called()
        manifest.write_bytes(manifest_bytes)
        path = self.root / "out/fixture.csv"
        frame = self.module.pd.read_csv(path, keep_default_na=False)
        self.module.pd.concat([frame, frame.iloc[:1]]).to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "duplicate or out-of-range"):
            self.run_mock(client)
        client.chat.completions.create.assert_not_called()

    def test_resume_rejects_changed_saved_prompt(self):
        self.run_mock(self.client([choice("P"), choice("N")]))
        path = self.root / "out/fixture.csv"
        frame = self.module.pd.read_csv(path, keep_default_na=False)
        frame.loc[0, "user_text"] = "different conditions"
        frame.to_csv(path, index=False)
        client = self.client([])
        with self.assertRaisesRegex(ValueError, "differ from the selected model or holdout records"):
            self.run_mock(client)
        client.chat.completions.create.assert_not_called()

    def test_retries_retain_original_error_row_and_backoff(self):
        self.write_records([record()])
        client = self.client([])
        client.chat.completions.create.side_effect = RuntimeError("fixture API failure")
        with patch.object(self.module.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            result = self.run_mock(client, retries=3)
        self.assertEqual(client.chat.completions.create.await_count, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 2, 4])
        self.assertEqual(result["scored_records"], 0)
        self.assertEqual(result["error_records"], 1)
        self.assertEqual(result["metrics"]["accuracy"], 0.0)

    def test_test_mode_limits_pending_records_then_resume_completes(self):
        self.write_records([record("P", i) for i in range(12)])
        result = self.run_mock(self.client([choice("P")] * 10), test_mode=True)
        self.assertEqual(result["new_records"], 10)
        result = self.run_mock(self.client([choice("P")] * 2))
        self.assertEqual(result["new_records"], 2)
        self.assertEqual(result["records"], 12)

    def test_sanity_test_uses_first_record_and_original_parameters(self):
        client = self.client([choice("P", [token("P", -.1, [("N", -2)])])])
        before = sorted(self.root.rglob("*"))
        result = asyncio.run(self.module.sanity_test(self.settings, client=client))
        self.assertTrue(result["correct"])
        self.assertEqual(before, sorted(self.root.rglob("*")))
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(set(request), {"model", "messages", "temperature", "max_tokens", "logprobs", "top_logprobs"})
        self.assertEqual(request["model"], "gpt-4.1")

    def test_unknown_model_selection_fails_before_dispatch(self):
        client = self.client([])
        with self.assertRaisesRegex(ValueError, "Unknown model"):
            asyncio.run(self.module.run_config(self.settings, client=client, model_names=["unknown"]))
        client.chat.completions.create.assert_not_called()
