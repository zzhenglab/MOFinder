"""Offline checks for training data transfer and prediction exports."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from mofinder.training.common import binary_metrics, export_predictions, sha256
from mofinder.training.prepare import prepare_bundle, validate_bundle, validate_dataset
from mofinder.training.records import (
    REACTION_PROMPT_FILE, read_message_rows, read_reaction_prompt,
    render_prompt, tokenize_prompts,
)


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.condition = {
            "metal_precursor": "Cu(NO3)2·2.5H2O", "organic_linker": "benzene-1,4-dicarboxylic acid",
            "modulator": None, "solvent": "water", "metal_concentration_mM": 20.0,
            "M_L_ratio": 1.0, "temperature_C": 100.0, "time_h": 12.0,
        }
        for name, label in (("train", "P"), ("holdout", "N")):
            row = {"messages": [
                {"role": "system", "content": "Predict P or N."},
                {"role": "user", "content": json.dumps(self.condition, ensure_ascii=False)},
                {"role": "assistant", "content": label},
            ]}
            (self.root / f"{name}.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def prepare(self, *, config=None, prompt=None):
        return prepare_bundle(
            self.root / "train.jsonl", self.root / "holdout.jsonl",
            self.repo / "benchmarks/mof_quest/questions.json",
            self.repo / "data/splits/class_map.json",
            config or self.repo / "configs/training_hpc.json", self.root / "bundle",
            prompt=prompt,
        )

    def test_bundle_preserves_bytes_and_separates_labels(self):
        manifest = self.prepare()
        for name in ("train", "holdout"):
            self.assertEqual((self.root / f"{name}.jsonl").read_bytes(),
                             (self.root / "bundle/data" / f"{name}.jsonl").read_bytes())
        rows, _ = read_message_rows(self.root / "bundle/data/questions.jsonl")
        self.assertEqual(len(rows), 22)
        self.assertTrue(all(set(row["reaction"]) == set(self.condition) for row in rows))
        self.assertTrue(all(message["role"] != "assistant" for row in rows for message in row["messages"]))
        self.assertEqual(validate_bundle(self.root / "bundle"), manifest)
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_changed_inputs_fail_validation(self):
        self.prepare()
        path = self.root / "bundle/data/train.jsonl"
        path.write_text(path.read_text().replace('"P"', '"N"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changed"):
            validate_bundle(self.root / "bundle")

    def test_changed_prompt_fails_validation(self):
        self.prepare()
        path = self.root / "bundle/prompts/reaction_prediction.txt"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changed reaction prediction prompt"):
            validate_bundle(self.root / "bundle")

    def test_all_datasets_render_the_full_canonical_prompt(self):
        manifest = self.prepare()
        canonical = read_reaction_prompt()
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["recipe"]["prompt_style"], "reaction_prediction")
        self.assertEqual(manifest["recipe"]["max_length"], 512)
        bundled = self.root / "bundle" / manifest["reaction_prediction"]["path"]
        self.assertEqual(bundled.read_bytes(), REACTION_PROMPT_FILE.read_bytes())
        for name in ("train", "holdout", "manual22"):
            with self.subTest(dataset=name):
                rows, source_prompt = read_message_rows(
                    self.root / "bundle" / manifest["datasets"][name]["path"]
                )
                # Existing split files retain their original system messages;
                # training must nevertheless use the shared full instructions.
                if name == "manual22":
                    self.assertEqual(source_prompt, canonical)
                else:
                    self.assertEqual(source_prompt, "Predict P or N.")
                for row in rows:
                    rendered = render_prompt(row)
                    self.assertTrue(rendered.startswith(canonical.strip() + "\n\nReaction conditions:\n"))
                    self.assertNotIn("Predict P or N.", rendered)
                    self.assertEqual(rendered, render_prompt(dict(row, labels=1 - row["labels"])))
                    self.assertTrue(rendered.endswith("\n\nLabel:"))
                    condition_json = rendered.split("\n\nReaction conditions:\n", 1)[1].rsplit("\n\nLabel:", 1)[0]
                    self.assertEqual(json.loads(condition_json), row["reaction"])

    def test_custom_full_prompt_is_bundled_and_used_for_manual_questions(self):
        prompt = self.root / "custom_prompt.txt"
        instructions = "Classify these reaction conditions as P or N. Preserve chemistry such as Cu\u00b7H2O.\n"
        prompt.write_text(instructions, encoding="utf-8")
        manifest = self.prepare(prompt=prompt)
        bundled = self.root / "bundle" / manifest["reaction_prediction"]["path"]
        self.assertEqual(bundled.read_bytes(), prompt.read_bytes())
        self.assertEqual(manifest["reaction_prediction"]["sha256"], sha256(prompt))
        for name, info in manifest["datasets"].items():
            rows, source_prompt = read_message_rows(self.root / "bundle" / info["path"])
            with self.subTest(dataset=name):
                if name == "manual22":
                    self.assertEqual(source_prompt, instructions)
                for row in rows:
                    self.assertTrue(render_prompt(row, read_reaction_prompt(bundled)).startswith(instructions.strip() + "\n\n"))
        self.assertEqual(validate_bundle(self.root / "bundle"), manifest)
        bundled.write_text(instructions + "Changed instructions.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changed reaction prediction prompt"):
            validate_bundle(self.root / "bundle")

    def test_blank_and_placeholder_prompts_are_rejected(self):
        path = self.root / "prompt.txt"
        for content in ("", " \n\t", "Predict P or N for {conditions}."):
            with self.subTest(prompt=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "full instructions"):
                    read_reaction_prompt(path)
                with self.assertRaisesRegex(ValueError, "full instructions"):
                    self.prepare(prompt=path)
                self.assertFalse((self.root / "bundle").exists())

    def test_legacy_and_missing_prompt_bundles_require_rebuilding(self):
        manifest = self.prepare()
        manifest_path = self.root / "bundle/manifest.json"
        for change in ("legacy_schema", "missing_schema", "missing_prompt"):
            altered = dict(manifest)
            if change == "legacy_schema":
                altered["schema_version"] = 1
            elif change == "missing_schema":
                del altered["schema_version"]
            else:
                del altered["reaction_prediction"]
            with self.subTest(change=change):
                manifest_path.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, r"Rebuild.*tools/training/prepare_hpc\.py"):
                    validate_bundle(self.root / "bundle")

    def test_other_prompt_styles_are_rejected(self):
        settings = json.loads((self.repo / "configs/training_hpc.json").read_text(encoding="utf-8"))
        config = self.root / "config.json"
        for style in ("short", "chat", "long", None):
            with self.subTest(style=style):
                settings["recipe"]["prompt_style"] = style
                config.write_text(json.dumps(settings), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, r"recipe\.prompt_style to reaction_prediction"):
                    self.prepare(config=config)
                self.assertFalse((self.root / "bundle").exists())

    def test_invalid_max_lengths_are_rejected(self):
        settings = json.loads((self.repo / "configs/training_hpc.json").read_text(encoding="utf-8"))
        config = self.root / "config.json"
        for length in (0, -1, 1.5, "512", True, None):
            with self.subTest(max_length=length):
                settings["recipe"]["max_length"] = length
                config.write_text(json.dumps(settings), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, r"recipe\.max_length must be a positive integer"):
                    self.prepare(config=config)
                tokenizer = Mock()
                with self.assertRaisesRegex(ValueError, r"recipe\.max_length must be a positive integer"):
                    tokenize_prompts(["reaction conditions"], tokenizer, length)
                tokenizer.assert_not_called()
                self.assertFalse((self.root / "bundle").exists())

    def test_bundle_validation_checks_the_prompt_recipe(self):
        manifest = self.prepare()
        manifest_path = self.root / "bundle/manifest.json"
        for field, value in (("prompt_style", "short"), ("max_length", 0)):
            altered = {**manifest, "recipe": {**manifest["recipe"], field: value}}
            with self.subTest(field=field):
                manifest_path.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, rf"recipe\.{field}"):
                    validate_bundle(self.root / "bundle")

    def test_tokenization_keeps_every_token_at_the_length_limit(self):
        encoded = {"input_ids": [list(range(511)), list(range(512))],
                   "attention_mask": [[1] * 511, [1] * 512]}
        tokenizer = Mock(return_value=encoded)
        texts = ["first complete reaction prompt", "second complete reaction prompt"]
        self.assertIs(tokenize_prompts(texts, tokenizer, 512), encoded)
        tokenizer.assert_called_once_with(texts, truncation=False, padding=False)

    def test_overlength_prompts_fail_with_original_row_and_limit(self):
        tokenizer = Mock(return_value={"input_ids": [list(range(512)), list(range(513))]})
        texts = ["first complete reaction prompt", "second complete reaction prompt"]
        with self.assertRaisesRegex(ValueError, r"row 100 needs 513 tokens; recipe\.max_length is 512.*No prompt was truncated"):
            tokenize_prompts(texts, tokenizer, 512, indices=[5, 99])
        tokenizer.assert_called_once_with(texts, truncation=False, padding=False)
        with self.assertRaisesRegex(ValueError, r"row 2 needs 513 tokens"):
            tokenize_prompts(texts, tokenizer, 512)

    def test_extra_answer_fields_are_rejected(self):
        path = self.root / "train.jsonl"
        row = json.loads(path.read_text())
        condition = dict(self.condition, label="P")
        row["messages"][1]["content"] = json.dumps(condition)
        path.write_text(json.dumps(row), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "eight reaction-condition"):
            validate_dataset(path)

    def test_prepare_and_validate_do_not_import_gpu_libraries(self):
        self.prepare()
        code = '''
import sys
class BlockGPUImports:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"torch", "transformers", "peft", "datasets", "accelerate"}:
            raise RuntimeError("Unexpected GPU import: " + name)
sys.meta_path.insert(0, BlockGPUImports())
from mofinder.training.train import main
main(["--bundle", sys.argv[1], "--validate-only"])
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.root / "bundle")],
                                capture_output=True, text=True, cwd=self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_predictions_and_metrics_share_threshold_and_order(self):
        rows = []
        for index, label in enumerate((0, 1, 0, 1)):
            rows.append({"record_id": str(index), "labels": label, "messages": []})
        probabilities, labels = [.1, .5, .8, .4], [0, 1, 0, 1]
        metrics = binary_metrics(probabilities, labels)
        self.assertEqual(metrics["confusion_matrix_NP"], [[1, 1], [1, 1]])
        self.assertEqual(metrics["accuracy"], .5)
        path = self.root / "predictions.jsonl"
        metadata = export_predictions(path, rows, probabilities, labels, [-1., 0., 2., -.2],
                                      ["conditions"] * 4, "run", 2500, "holdout",
                                      {"path": "data/holdout.jsonl", "sha256": "example"})
        exported = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([row["pred"] for row in exported], ["N", "P", "P", "N"])
        self.assertEqual([row["source_row_index"] for row in exported], [0, 1, 2, 3])
        self.assertEqual(metadata["sha256"], sha256(path))

    def test_full_prompt_preserves_unicode_and_excludes_answer(self):
        rows, _ = read_message_rows(self.root / "train.jsonl")
        rendered = render_prompt(rows[0])
        self.assertIn("Cu(NO3)2·2.5H2O", rendered)
        self.assertTrue(rendered.endswith("\n\nLabel:"))
        self.assertNotIn('"assistant"', rendered)


if __name__ == "__main__":
    unittest.main()
