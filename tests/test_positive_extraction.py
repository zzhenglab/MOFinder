"""Offline extraction checks and CSV recovery from saved JSON files."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in ("pandas", "pydantic"))
if AVAILABLE:
    import pandas as pd
    from mofinder.extraction import positive, backfill
    from mofinder.extraction.schemas import ArticleExtraction

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/positive_reference.json").read_text(encoding="utf-8"))


@unittest.skipUnless(AVAILABLE, "Install the mining extra for extraction tests")
class PositiveExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.article = ArticleExtraction.model_validate(copy.deepcopy(FIXTURE["article"]))
        self.manifest = self.base / "manifest.csv"
        self.doi = "10.example/synthetic"
        pd.DataFrame([{"DOI": self.doi, "Main File": "article.pdf", "SI File": "si.pdf"}]).to_csv(self.manifest, index=False)

    def save(self, article=None):
        article = self.article if article is None else article
        paths = positive.save_json_payloads(self.doi, article.model_dump_json(), article, self.base / "json")
        return paths, Path(paths["article_parsed_path"]).parent

    def test_original_schema_and_prompts_are_unchanged(self):
        names = {"SYSTEM_PROMPT": "positive_system.txt", "USER_PROMPT_TEMPLATE": "positive_user.txt"}
        for key, filename in names.items():
            data = (ROOT / "prompts" / filename).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), FIXTURE["prompt_sha256"][key])
        schema_hash = hashlib.sha256(json.dumps(ArticleExtraction.model_json_schema(), sort_keys=True).encode()).hexdigest()
        self.assertEqual(schema_hash, FIXTURE["schema_sha256"])

    def test_flatten_matches_original_with_truncation_roles_and_zero_values(self):
        rows = positive.flatten_row(self.doi, "article.pdf", "si.pdf", "raw.json", self.article,
                                    ["synthesis_001.json", "synthesis_002.json"], "article_extraction.json")
        self.assertEqual(rows, FIXTURE["expected_rows"])
        self.assertEqual(len(rows[0]), len(rows[1]))

    def test_empty_syntheses_preserve_original_row_and_flag_behavior(self):
        article = ArticleExtraction(syntheses=[], trial_or_failure_reported="yes", trial_or_failure_notes="evidence")
        row = positive.flatten_row(self.doi, "a", "b", "raw", article, [], "article.json")[0]
        self.assertEqual(row["article_trial_or_failure"], "")
        self.assertEqual(row["parsed_json"], "article.json")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(set(row), set(FIXTURE["expected_rows"][0]))

    def test_payload_roundtrip_and_rerun_removes_stale_syntheses(self):
        paths, directory = self.save()
        self.assertEqual(json.loads(Path(paths["article_parsed_path"]).read_text(encoding="utf-8")), self.article.model_dump())
        self.assertEqual(len(list(directory.glob("synthesis_*.json"))), 2)
        smaller = self.article.model_copy(update={"syntheses": self.article.syntheses[:1]})
        self.save(smaller)
        self.assertEqual([p.name for p in directory.glob("synthesis_*.json")], ["synthesis_001.json"])
        positive.save_json_payloads(self.doi, "unstructured response", smaller, self.base / "json")
        self.assertFalse((directory / "raw_output.json").exists())
        self.assertEqual((directory / "raw_output.txt").read_text(encoding="utf-8"), "unstructured response")

    def test_backfill_matches_live_csv_values(self):
        paths, directory = self.save()
        live = positive.flatten_row(self.doi, "a", "b", paths["raw_path"], self.article,
                                    paths["syn_paths"], paths["article_parsed_path"])
        restored = backfill.flatten_rows_from_article_dir(self.doi, "a", "b", directory)
        for expected, actual in zip(live, restored):
            self.assertEqual({k: "" if v is None else v for k, v in expected.items()}, actual)

    def test_backfill_recovers_missing_article_and_keeps_correct_record_path(self):
        _, directory = self.save()
        (directory / "article_extraction.json").unlink()
        (directory / "synthesis_001.json").write_text("{truncated")
        restored = backfill.flatten_rows_from_article_dir(self.doi, "a", "b", directory)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["mof_name"], "MOF-other")
        self.assertTrue(restored[0]["parsed_json"].endswith("synthesis_002.json"))

    def test_backfill_valid_empty_article_is_authoritative(self):
        _, directory = self.save()
        (directory / "article_extraction.json").write_text(json.dumps({"syntheses": [], "trial_or_failure_reported": "no"}))
        restored = backfill.flatten_rows_from_article_dir(self.doi, "a", "b", directory)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["mof_name"], "")

    def test_backfill_invalid_payload_remains_recoverable(self):
        _, directory = self.save()
        for path in directory.glob("*.json"):
            path.write_text("{truncated")
        target = self.base / "out.csv"
        report = backfill.backfill_from_json(self.manifest, self.base / "json", target)
        self.assertEqual(len(report["invalid_json_dois"]), 1)
        self.assertFalse(target.exists())
        self.save()
        report = backfill.backfill_from_json(self.manifest, self.base / "json", target)
        self.assertEqual(report["rows_written"], 2)
        self.assertEqual(backfill.backfill_from_json(self.manifest, self.base / "json", target)["processed"], 0)

    def test_backfill_missing_json_report_is_written_beside_output(self):
        target = self.base / "nested" / "out.csv"
        report = backfill.backfill_from_json(self.manifest, self.base / "missing", target)
        self.assertEqual(report["missing_json_dois"], [self.doi])
        self.assertEqual((target.parent / "missing_json_dois.txt").read_text(encoding="utf-8"), self.doi + "\n")

    def test_request_matches_notebook_schema_and_prompt(self):
        recorded = []
        def parse(**kwargs):
            recorded.append(kwargs)
            return SimpleNamespace(output_text=self.article.model_dump_json(), output_parsed=self.article)
        client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
        with patch.object(positive, "read_any_text", side_effect=["article text", "SI text"]):
            raw, parsed = positive.extract_one(client, self.doi, "a", "b", "example-model")
        expected_user = (ROOT / "prompts/positive_user.txt").read_text(encoding="utf-8").format(doi=self.doi, article_text="article text", si_text="SI text")
        self.assertEqual(recorded, [{"model": "example-model", "input": [
            {"role": "system", "content": (ROOT / "prompts/positive_system.txt").read_text(encoding="utf-8")},
            {"role": "user", "content": expected_user}], "text_format": ArticleExtraction}])
        self.assertIs(parsed, self.article)

    def test_empty_documents_do_not_send_request(self):
        client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **_: self.fail("No request expected")))
        with patch.object(positive, "read_any_text", return_value=""):
            with self.assertRaisesRegex(ValueError, "No readable"):
                positive.extract_one(client, self.doi, "a", "b")

    def test_retry_once_and_failed_row_is_complete(self):
        fake_openai = SimpleNamespace(OpenAI=lambda: object())
        with patch.dict(sys.modules, {"openai": fake_openai}), patch.object(positive, "extract_one", side_effect=RuntimeError("fixture failure")) as extract, patch.object(positive.time, "sleep"):
            result = positive._process_item({"doi": self.doi, "main_pdf": "a", "si_pdf": "b"}, "example-model", str(self.base))
        self.assertEqual(extract.call_count, 2)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(set(result["rows"][0]), set(FIXTURE["expected_rows"][0]))
        self.assertEqual(result["rows"][0]["error"], "fixture failure")

    def test_dimension_check_skips_incompatible_rows_and_preserves_unicode(self):
        target = self.base / "out.csv"
        row = copy.deepcopy(FIXTURE["expected_rows"][0])
        row["metal_1"] = "Zn\x00b7H₂O\nsecond\tline"
        self.assertEqual(positive.append_rows(target, [row, {"doi": "bad"}]), (1, 1))
        loaded = pd.read_csv(target, keep_default_na=False)
        self.assertEqual(loaded.loc[0, "metal_1"], "Zn·H₂O\\nsecond line")

    def test_runner_deduplicates_and_resumes_all_recorded_dois(self):
        frame = pd.read_csv(self.manifest)
        pd.concat([frame, frame]).to_csv(self.manifest, index=False)
        row = copy.deepcopy(FIXTURE["expected_rows"][0]); row["status"] = "failed"
        result = {"doi": self.doi, "rows": [row], "elapsed": 0, "synth_count": 0}
        target = self.base / "output.csv"
        with patch.object(positive, "_process_item", return_value=result) as worker:
            report = positive.run(self.manifest, target, json_out_dir=self.base / "json")
            self.assertEqual(report["processed"], 1)
            self.assertEqual(worker.call_count, 1)
            self.assertEqual(positive.run(self.manifest, target, json_out_dir=self.base / "json")["processed"], 0)
            self.assertEqual(worker.call_count, 1)

    def test_conflicting_paths_and_slug_collisions_are_rejected(self):
        original = {"DOI": self.doi, "Main File": "article.pdf", "SI File": "si.pdf"}
        for other, message in [(dict(original, **{"Main File": "other.pdf"}), "Conflicting"),
                               (dict(original, DOI="10.example_synthetic"), "same JSON")]:
            pd.DataFrame([original, other]).to_csv(self.manifest, index=False)
            with self.assertRaisesRegex(ValueError, message):
                positive.read_manifest(self.manifest)

    def test_invalid_resume_csv_stops_before_work_is_submitted(self):
        target = self.base / "output.csv"
        target.write_text('unexpected,columns\none,two\n')
        with patch.object(positive, "_process_item") as worker:
            with self.assertRaisesRegex(ValueError, "Cannot resume"):
                positive.run(self.manifest, target, json_out_dir=self.base / "json")
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
