"""Offline checks for condition features, cluster splits, and training JSONL."""

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

HAS_TABLE_DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in ("pandas", "openpyxl"))


def synthetic_tables(pd):
    """Synthetic reaction records for filtering and split tests."""
    positives, negatives, years = [], [], []
    for i in range(20):
        row = {
            "doi": f"10.0000/fixture.{i}", "metal_1": "Zn(NO3)2",
            "linker_1": f"fixture linker {i}", "solvent_main": "water",
            "modulator_1": None, "metel_concnertation": 20.0,
            "M_L_ratio": "1:2", "temperature_c": 100.0, "time_h": 24.0,
        }
        positives.append(row)
        negatives.append(dict(row, temperature_c=20.0))
        years.append({"DOI": row["doi"], "Publication Year": 2000 + i})
    forced = {
        "doi": "10.0000/forced", "metal_1": "ZrOCl2·8H2O",
        "linker_1": "1H-pyrazole-3,5-dicarboxylic acid",
        "modulator_1": "formic acid", "solvent_main": "dimethylformamide",
        "metel_concnertation": 26.0, "M_L_ratio": 0.87,
        "temperature_c": 130.0, "time_h": 72.0,
    }
    positives.extend([forced, dict(forced)])  # Duplicate positive record.
    negatives.extend([dict(forced, temperature_c=30.0), dict(forced)])  # Conflicting negative label.
    positives.append(dict(positives[0], metal_1=None))  # Missing required reagent.
    years.append({"DOI": forced["doi"], "Publication Year": 2020})
    return pd.DataFrame(positives), pd.DataFrame(negatives), pd.DataFrame(years)


@unittest.skipUnless(HAS_TABLE_DEPENDENCIES, "Install the datasets extra for dataset tests.")
class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from mofinder.datasets import prepare
        cls.pd, cls.module = pd, prepare
        cls.repo = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = self.module.load_settings(self.repo / "configs/dataset_preparation.json")
        pos, neg, meta = synthetic_tables(self.pd)
        for name, frame in (("positive_csv", pos), ("negative_csv", neg), ("metadata_file", meta)):
            path = self.root / f"{name}.csv"
            frame.to_csv(path, index=False)
            self.settings[name] = path
        self.settings["output_dir"] = self.root / "out"

    def test_original_condition_fields_and_number_parsing(self):
        row = synthetic_tables(self.pd)[0].iloc[0]
        result = self.module.row_to_conditions(row)
        self.assertEqual(list(result), ["metal_precursor", "organic_linker", "modulator", "solvent", "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h"])
        self.assertEqual(result["M_L_ratio"], .5)
        self.assertEqual(self.module.parse_ml_ratio("1:1:1"), .5)
        self.assertIsNone(self.module.parse_ml_ratio("1:0"))
        self.assertEqual(self.module.normalize_doi(r"C:\papers\10.1021_jacs.2c09756_SI.pdf"), "10.1021/jacs.2c09756")

    def test_validation_does_not_write_or_prepare(self):
        before = sorted(self.root.rglob("*"))
        result = self.module.validate_inputs(self.settings)
        self.assertTrue(result["valid"])
        self.assertEqual(before, sorted(self.root.rglob("*")))
        self.settings["negative_csv"] = self.root / "missing.csv"
        self.assertFalse(self.module.validate_inputs(self.settings)["valid"])

    def test_cluster_split_forced_holdout_conflicts_and_exact_ratio(self):
        result = self.module.prepare(self.settings)
        train, holdout = result["train"], result["holdout"]
        self.assertFalse(set(train.cluster_key) & set(holdout.cluster_key))
        self.assertFalse(set(train.condition_key) & set(holdout.condition_key))
        self.assertFalse(train.is_forced_condition.any())
        self.assertTrue(holdout.is_forced_representative.any())
        self.assertTrue(holdout.loc[holdout.is_forced_condition, "is_success"].all())
        tc, hc = self.module.count_labels(train), self.module.count_labels(holdout)
        self.assertEqual(tc["P"] * hc["N"], tc["N"] * hc["P"])
        self.assertEqual(result["summary"]["counts"]["rows_deduped_exact_input_within_label"], 1)
        self.assertEqual(result["summary"]["counts"]["rows_skipped_required"], 1)
        coverage = result["summary"]["forced_holdout"]
        self.assertEqual(coverage["questions"][0]["matched_rows"], 1)
        self.assertEqual(len(coverage["questions_not_found_after_filters"]), 21)

    def test_repeated_runs_keep_jsonl_and_assignments_identical(self):
        first = self.module.prepare(self.settings)
        expected = {p.name: p.read_bytes() for p in self.settings["output_dir"].glob("*.jsonl")}
        assignments = (self.settings["output_dir"] / "mof_ft_split_assignments.csv").read_bytes()
        self.settings["output_dir"] = self.root / "out_again"
        second = self.module.prepare(self.settings)
        self.assertEqual(expected, {p.name: p.read_bytes() for p in self.settings["output_dir"].glob("*.jsonl")})
        self.assertEqual(assignments, (self.settings["output_dir"] / "mof_ft_split_assignments.csv").read_bytes())
        self.assertEqual(first["train"].source_row_id.tolist(), second["train"].source_row_id.tolist())

    def test_year_subsets_only_contain_training_records(self):
        result = self.module.prepare(self.settings)
        root = self.settings["output_dir"]
        train = set((root / "mof_ft_train.jsonl").read_text().splitlines())
        holdout = set((root / "mof_ft_holdout.jsonl").read_text().splitlines())
        for key, count in (("year_outputs", 6), ("year_outputs_5periods", 8)):
            outputs = result["summary"]["outputs"][key]
            self.assertEqual(len(outputs), count)
            for entry in outputs:
                lines = set(Path(entry["path"]).read_text().splitlines())
                self.assertLessEqual(lines, train)
                self.assertFalse(lines & holdout)
        records = [json.loads(line) for line in train | holdout]
        prompt = self.settings["prompt_file"].read_text(encoding="utf-8")
        for record in records:
            self.assertEqual(record["messages"][0], {"role": "system", "content": prompt})
            self.assertIn(record["messages"][2]["content"], ("P", "N"))

    def test_forced_only_holdout_set_does_not_attempt_empty_swap(self):
        self.settings["holdout_cluster_frac"] = .049
        result = self.module.prepare(self.settings)
        self.assertEqual(result["holdout"].cluster_key.nunique(), 1)
        self.assertTrue(result["holdout"].is_forced_cluster.all())

    def test_impossible_single_label_partition_fails_before_writing(self):
        negative = self.pd.read_csv(self.settings["negative_csv"])
        negative.iloc[0:0].to_csv(self.settings["negative_csv"], index=False)
        with self.assertRaises(ValueError):
            self.module.prepare(self.settings)
        self.assertFalse(self.settings["output_dir"].exists())

    def test_cluster_keys_use_sets_while_exact_conditions_preserve_order(self):
        row = synthetic_tables(self.pd)[0].iloc[0].to_dict()
        row.update(linker_1="A", linker_2="B")
        swapped = dict(row, linker_1="B", linker_2="A")
        self.assertEqual(self.module.build_cluster_key(row), self.module.build_cluster_key(swapped))
        self.assertNotEqual(self.module.canonical_condition_key(row), self.module.canonical_condition_key(swapped))

    def test_split_validation_rejects_forced_condition_in_training(self):
        result = self.module.prepare(self.settings)
        forced = {result["train"].condition_key.iloc[0]}
        with self.assertRaisesRegex(ValueError, "forced benchmark"):
            self.module.validate_split(result["train"], result["holdout"], forced)

    def test_archived_split_assignments_match_training_and_holdout(self):
        assignments = self.pd.read_csv(self.repo / "data/splits/split_assignments.csv")
        self.assertTrue(assignments.source_row_id.is_unique)
        train_clusters = set(assignments.loc[assignments.split == "train", "cluster_key"])
        holdout_clusters = set(assignments.loc[assignments.split == "holdout", "cluster_key"])
        self.assertFalse(train_clusters & holdout_clusters)
        manifest = json.loads((self.repo / "data/training/manifest.json").read_text())
        for entry in manifest["files"]:
            path = self.repo / entry["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            split = "train" if path.name == "train.jsonl" else "holdout"
            selected = assignments.loc[assignments.split == split]
            expected = set(zip(selected.condition_key, selected.is_success))
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            actual = set()
            for record in records:
                messages = {message["role"]: message["content"] for message in record["messages"]}
                key = self.module.forced_question_condition_key(json.loads(messages["user"]))
                actual.add((key, messages["assistant"] == "P"))
            self.assertEqual(len(records), len(selected))
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
