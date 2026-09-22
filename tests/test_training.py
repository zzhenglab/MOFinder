"""Offline checks for training data transfer and prediction exports."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mofinder.training.common import binary_metrics, export_predictions, sha256
from mofinder.training.prepare import prepare_bundle, validate_bundle, validate_dataset
from mofinder.training.records import read_message_rows, render_prompt


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

    def prepare(self):
        return prepare_bundle(
            self.root / "train.jsonl", self.root / "holdout.jsonl",
            self.repo / "benchmarks/mof_quest/questions.json",
            self.repo / "data/splits/class_map.json",
            self.repo / "configs/training_hpc.json", self.root / "bundle",
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
        path = self.root / "bundle/prompts/gptoss_short.txt"
        path.write_text(path.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changed short prompt"):
            validate_bundle(self.root / "bundle")

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

    def test_short_prompt_preserves_unicode_and_excludes_answer(self):
        rows, _ = read_message_rows(self.root / "train.jsonl")
        rendered = render_prompt(rows[0], None, "short")
        self.assertIn("Cu(NO3)2·2.5H2O", rendered)
        self.assertTrue(rendered.endswith("\nAnswer:"))
        self.assertNotIn('"assistant"', rendered)


if __name__ == "__main__":
    unittest.main()
