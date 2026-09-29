"""Offline matched-cohort and explicit-feature-profile regression tests."""

import csv
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from mofinder.datasets.prepare import canonical_condition_key, row_to_conditions
from mofinder.datasets.process_enrich import extend_input_description, main, prepare_process_enrich
from mofinder.training.common import sha256
from mofinder.training.prepare import prepare_bundle, validate_bundle, validate_dataset
from mofinder.training.records import INPUT_FIELDS, PROCESS_FIELDS, PROCESS_PROMPT_FILE, REACTION_PROMPT_FILE


class ProcessEnrichTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.sources = []
        for index in range(4):
            self.sources.append({
                "doi": f"10.1000/test{index}", "metal_1": "Zn(NO3)2",
                "linker_1": f"ligand {index}", "solvent_main": "water",
                "metel_concnertation": "20", "M_L_ratio": "1:2",
                "temperature_c": "100", "time_h": "24",
                "vessel_type_raw": "25-mL Teflon-lined autoclave",
                "stirring_raw": "not stated", "vessel_type": "PTFE-lined autoclave",
                "vessel_volume_mL": "25", "agitation": "Not reported",
            })
        self.sources[1]["vessel_volume_mL"] = "Not reported"
        self.sources[3]["vessel_volume_mL"] = "Ambiguous"
        self.write_csv(self.root / "positive.csv", self.sources[:2])
        self.write_csv(self.root / "negative.csv", self.sources[2:])
        self.assignments = [{
            "source_row_id": str(index), "condition_key": canonical_condition_key(row),
            "doi_norm": row["doi"], "cluster_key": f"cluster {index}",
            "is_success": "True" if index < 2 else "False",
            "split": "train" if index % 2 == 0 else "holdout",
        } for index, row in enumerate(self.sources)]
        self.write_csv(self.root / "assignments.csv", self.assignments)
        # Baseline JSONL order deliberately differs from assignment/source order.
        for name, order in (("train", (2, 0)), ("holdout", (3, 1))):
            records = [{"messages": [
                {"role": "system", "content": REACTION_PROMPT_FILE.read_text(encoding="utf-8").rstrip("\r\n")},
                {"role": "user", "content": json.dumps(row_to_conditions(self.sources[index]))},
                {"role": "assistant", "content": "P" if index < 2 else "N"},
            ]} for index in order]
            (self.root / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        self.settings = {
            "positive_csv": self.root / "positive.csv", "negative_csv": self.root / "negative.csv",
            "baseline_train": self.root / "train.jsonl", "baseline_holdout": self.root / "holdout.jsonl",
            "split_assignments": self.root / "assignments.csv", "prompt_file": PROCESS_PROMPT_FILE,
            "output_dir": self.root / "enriched", "project_root": self.root,
        }

    def write_csv(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def records(self, path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def bundle(self, **overrides):
        options = {
            "train": self.root / "enriched/train_process_enrich.jsonl", "holdout": self.root / "enriched/holdout_process_enrich.jsonl",
            "questions": self.repo / "benchmarks/mof_quest/questions.json",
            "class_map": self.repo / "data/processed_data_json/class_map.json",
            "config": self.repo / "configs/training_hpc.json", "output": self.root / "bundle",
            "feature_profile": "process_enrich", "manual_process_policy": "missing_control",
        }
        options.update(overrides)
        return prepare_bundle(**options)

    def test_preserves_all_baseline_inputs_labels_order_and_source_membership(self):
        before = {name: sha256(self.root / f"{name}.jsonl") for name in ("train", "holdout")}
        manifest = prepare_process_enrich(self.settings)
        self.assertEqual(manifest["validation"]["mapped_source_rows"], 4)
        self.assertEqual(manifest["source_csv_rows"], {"P": 2, "N": 2})
        self.assertFalse((self.root / "enriched/reaction_prediction_process_enrich_11field.txt").exists())
        self.assertEqual(manifest["reaction_prediction"]["sha256"], sha256(PROCESS_PROMPT_FILE))
        self.assertEqual(Path(manifest["reaction_prediction"]["path"]), PROCESS_PROMPT_FILE)
        self.assertTrue(manifest["reaction_prediction"]["path_base"].startswith("project_root"))
        for split, order in (("train", [2, 0]), ("holdout", [3, 1])):
            self.assertEqual(before[split], sha256(self.root / f"{split}.jsonl"))
            enriched_path = self.root / "enriched" / f"{split}_process_enrich.jsonl"
            self.assertEqual(manifest["datasets"][split]["path"], enriched_path.name)
            with (self.root / "enriched" / f"{split}_sources.csv").open(encoding="utf-8") as handle:
                source_ids = [int(item["source_row_id"]) for item in csv.DictReader(handle)]
            self.assertEqual(source_ids, order)
            for original, enriched in zip(self.records(self.root / f"{split}.jsonl"), self.records(enriched_path)):
                self.assertEqual(enriched["messages"][0]["content"],
                                 extend_input_description(original["messages"][0]["content"]))
                self.assertEqual(original["messages"][2], enriched["messages"][2])
                original_conditions = json.loads(original["messages"][1]["content"])
                enriched_conditions = json.loads(enriched["messages"][1]["content"])
                self.assertEqual(set(enriched_conditions), set(INPUT_FIELDS + PROCESS_FIELDS))
                self.assertEqual(original_conditions, {key: enriched_conditions[key] for key in INPUT_FIELDS})
            validate_dataset(enriched_path, "process_enrich", PROCESS_PROMPT_FILE.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "eight reaction-condition"):
                validate_dataset(enriched_path)
        with self.assertRaises(FileExistsError):
            prepare_process_enrich(self.settings)

    def test_unrelated_system_prompt_changes_rejected(self):
        custom = self.root / "extra_prompt.txt"
        custom.write_text(PROCESS_PROMPT_FILE.read_text(encoding="utf-8") + "\nExtra guidance.", encoding="utf-8")
        self.settings["prompt_file"] = custom
        with self.assertRaisesRegex(ValueError, "change only the input list"):
            prepare_process_enrich(self.settings)
        self.assertFalse(self.settings["output_dir"].exists())

    def test_changed_source_order_rejected(self):
        self.write_csv(self.root / "positive.csv", list(reversed(self.sources[:2])))
        with self.assertRaisesRegex(ValueError, "Source chemistry"):
            prepare_process_enrich(self.settings)
        self.assertFalse((self.root / "enriched").exists())

    def test_ambiguous_mapping_rejected(self):
        self.sources[1] = dict(self.sources[0])
        self.write_csv(self.root / "positive.csv", self.sources[:2])
        self.assignments[1].update(condition_key=self.assignments[0]["condition_key"], doi_norm=self.assignments[0]["doi_norm"])
        self.write_csv(self.root / "assignments.csv", self.assignments)
        with self.assertRaisesRegex(ValueError, "Ambiguous condition-key"):
            prepare_process_enrich(self.settings)

    def test_changed_baseline_label_rejected(self):
        path = self.root / "train.jsonl"
        records = self.records(path)
        records[0]["messages"][2]["content"] = "P"
        path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "No archived source mapping"):
            prepare_process_enrich(self.settings)
        self.assertFalse((self.root / "enriched").exists())

    def test_reusing_or_omitting_baseline_records_rejected(self):
        path = self.root / "train.jsonl"
        original = path.read_text(encoding="utf-8")
        path.write_text(original + original.splitlines()[0] + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reused source row"):
            prepare_process_enrich(self.settings)
        path.write_text(original.splitlines()[0] + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not consumed"):
            prepare_process_enrich(self.settings)

    def test_unresolved_and_invalid_volume_handling(self):
        for value in ("", "nan", "-1", "inf", "25 mL"):
            self.sources[0]["vessel_volume_mL"] = value
            self.write_csv(self.root / "positive.csv", self.sources[:2])
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare_process_enrich(self.settings)

    def test_process_bundle_requires_explicit_missing_benchmark_policy(self):
        prepare_process_enrich(self.settings)
        with self.assertRaisesRegex(ValueError, "no curated process annotations"):
            self.bundle(manual_process_policy=None)
        manifest = self.bundle()
        self.assertEqual(manifest["feature_profile"], "process_enrich")
        self.assertEqual(validate_bundle(self.root / "bundle"), manifest)
        for name in ("train", "holdout"):
            self.assertEqual((self.root / "enriched" / f"{name}_process_enrich.jsonl").read_bytes(),
                             (self.root / "bundle/data" / f"{name}.jsonl").read_bytes())
        benchmark = self.records(self.root / "bundle/data/questions.jsonl")
        self.assertEqual(len(benchmark), 22)
        for item in benchmark:
            conditions = json.loads(item["messages"][1]["content"])
            self.assertTrue(all(conditions[field] == "Not reported" for field in PROCESS_FIELDS))
        # Selecting the process schema must not bypass outcome-leakage checks.
        path = self.root / "enriched/train_process_enrich.jsonl"
        rows = self.records(path)
        conditions = json.loads(rows[0]["messages"][1]["content"])
        conditions["label"] = "N"
        rows[0]["messages"][1]["content"] = json.dumps(conditions)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "eleven process_enrich"):
            validate_dataset(path, "process_enrich")

    def test_process_bundle_rejects_wrong_prompt(self):
        prepare_process_enrich(self.settings)
        custom = self.root / "prompt.txt"
        custom.write_text("Predict P or N.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "System prompt differs"):
            self.bundle(prompt=custom)

    def test_cli_output_override_keeps_config_and_default_destination_unchanged(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({key: str(value) for key, value in self.settings.items()}), encoding="utf-8")
        original_hash = sha256(config)
        destination = self.root / "reproduced"
        with redirect_stdout(StringIO()):
            main(["--config", str(config), "--output", str(destination)])
        self.assertEqual(original_hash, sha256(config))
        self.assertFalse(self.settings["output_dir"].exists())
        self.assertEqual(len(self.records(destination / "train_process_enrich.jsonl")), 2)


if __name__ == "__main__":
    unittest.main()
