"""Negative-plan selection, parent provenance, and Cartesian expansion checks."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    import pandas as pd
    from pydantic import ValidationError
    from mofinder.extraction import negative as neg
    from mofinder.extraction import enumerate_failures as enum
except ImportError:
    pd = None


@unittest.skipIf(pd is None, "Install the mining extra to run negative-extraction tests")
class NegativeExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.doi = "10.0000/example"
        self.success_dir = self.root / "success"
        self.plan_dir = self.root / "plans"
        self.enum_dir = self.root / "enumerated"
        self.plan_csv = self.root / "plans.csv"
        self.enum_csv = self.root / "enumerated.csv"
        self.base = {
            "mof_name": "MOF-A", "reference": self.doi,
            "metals": [{"name_full": "Zn(NO3)2", "amount_value": 1, "amount_unit": "mmol"}],
            "linkers": [{"name_full": "terephthalic acid", "amount_value": 1, "amount_unit": "mmol"}],
            "modulators": [],
            "solvents": [{"name_full": "DMF", "role": "main", "amount_value_ml": 5},
                         {"name_full": "water", "role": "secondary", "amount_value_ml": 1}],
            "conditions": {"temperature_c": 120, "time_h": 24, "vessel_type": "sealed vial"},
            "post_processing": {"washing_solvent": "DMF"},
            "structure_properties": {"topology_code": "pcu", "applications": ["adsorption"]},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def write_base(self, doi=None, index=1, synthesis=None):
        directory = self.success_dir / neg.sanitize_for_path(doi or self.doi)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"synthesis_{index:03d}.json"
        path.write_text(json.dumps(synthesis or self.base, ensure_ascii=False, indent=2))
        return path

    def plan(self, **variation):
        return neg.PaperModificationPlan(
            rationale_overall="Lower temperatures did not produce crystals.",
            plans=[neg.BaseModificationPlan(
                based_on_success_index=1, mof_name="MOF-A", modification_notes="Text reports failure below 100 C.",
                variations=neg.VariationSet(**variation),
            )],
        )

    def plan_rows(self, doi=None, index=1, note="Lower temperatures gave no crystals.", **variation):
        model = self.plan(**variation)
        model.plans[0].based_on_success_index = index
        return neg.flatten_plan_rows(doi or self.doi, "article.pdf", "SI.pdf", "raw.json", model, ["plan.json"], note)

    def write_plans(self, rows):
        pd.DataFrame(rows).to_csv(self.plan_csv, index=False)

    def expand(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return enum.enumerate_failures(
                str(self.plan_csv), str(self.enum_csv), success_dir=str(self.success_dir),
                enum_json_dir=str(self.enum_dir), plan_json_dir=str(self.plan_dir), **kwargs,
            )

    def test_prompts_match_revised_notebook_runtime_strings(self):
        self.assertEqual(hashlib.sha256(neg.NEG_SYSTEM_PROMPT.encode()).hexdigest(), "ff8e42516811e89d5da01861ad54211e1f2bc51012887c17d6cc7f218fe88b5a")
        self.assertEqual(hashlib.sha256(neg.NEG_USER_PROMPT_TEMPLATE.encode()).hexdigest(), "b82ae665db326573c8ca1d9e06b5d86fce5cbf57a47e065ffd569726ccceea44")

    def test_text_only_plan_records_empty_parent_snapshot(self):
        neg.save_plan_payloads(self.doi, "{}", self.plan(temperature_c=[60]), str(self.plan_dir), [])
        self.write_base()
        with self.assertRaisesRegex(ValueError, "success index is absent"):
            enum.read_success_syn(self.doi, 1, str(self.success_dir), str(self.plan_dir))

    def test_schema_restricts_editable_classes(self):
        with self.assertRaises(ValidationError):
            neg.VariationSet(pressure_bar=[10])
        plan = self.plan(temperature_c=[60, 80])
        self.assertEqual(plan.plans[0].variations.temperature_c, [60.0, 80.0])

    def test_model_request_retains_prompt_and_success_order(self):
        model = self.plan(temperature_c=[60])
        response = SimpleNamespace(output_text='{"plans":[]}', output_parsed=model)
        client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=response)))
        main = self.root / "article.txt"
        main.write_text("Only high temperature formed crystals.")
        raw, parsed = neg._neg_build_plan(client, self.doi, str(main), "", ["{\"id\": 2}", "{\"id\": 1}"], "prior notes")
        request = client.responses.parse.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5")
        self.assertEqual(request["reasoning"], {"effort": "medium"})
        self.assertEqual(request["input"][0]["content"], neg.NEG_SYSTEM_PROMPT)
        self.assertIn('-- SUCCESS 1 --\n{"id": 2}\n\n-- SUCCESS 2 --\n{"id": 1}', request["input"][1]["content"])
        self.assertIn("Only high temperature formed crystals.", request["input"][1]["content"])
        self.assertEqual(raw, response.output_text)
        self.assertIs(parsed, model)

    def test_yes_only_worker_never_calls_client_for_other_dois(self):
        with patch.object(neg, "_make_client", side_effect=AssertionError("unexpected API client")):
            result = neg.process_negative_item_yes(
                {"doi": self.doi, "main_pdf": "", "si_pdf": ""}, "gpt-5", str(self.plan_dir), "absent.csv", set()
            )
        self.assertEqual(result["status"], "skipped_no_yes")
        self.assertEqual(result["rows"], [])
        self.assertFalse(self.plan_dir.exists())

    def test_empty_notes_keep_source_yes_gate_behavior(self):
        self.write_base()
        rows = self.plan_rows(note="", temperature_c=[60])
        self.assertEqual(rows[0]["article_trial_or_failure"], "")
        self.write_plans(rows)
        self.expand()
        self.assertFalse(self.enum_csv.exists())
        self.assertFalse(self.enum_dir.exists())

    def test_cartesian_order_and_unvaried_fields_are_preserved(self):
        self.write_base()
        original = copy.deepcopy(self.base)
        self.write_plans(self.plan_rows(
            metal_1=[{"name_full": "CuCl2", "amount_value": 2, "amount_unit": "mmol"},
                     {"name_full": "CoCl2", "amount_value": 3, "amount_unit": "mmol"}],
            temperature_c=[60, 80], time_h=[4, 8, 12],
        ))
        result = self.expand()
        self.assertEqual(result["rows_written"], 12)
        frame = pd.read_csv(self.enum_csv)
        self.assertEqual(frame["metal_1"].tolist(), ["CuCl2"] * 6 + ["CoCl2"] * 6)
        self.assertEqual(frame["temperature_c"].tolist(), [60] * 3 + [80] * 3 + [60] * 3 + [80] * 3)
        self.assertEqual(frame["time_h"].tolist(), [4, 8, 12] * 4)
        payload = json.loads(Path(frame.iloc[0]["parsed_json"]).read_text())
        self.assertEqual(payload["synthesis"]["solvents"], original["solvents"])
        self.assertEqual(payload["synthesis"]["post_processing"], original["post_processing"])
        self.assertEqual(payload["synthesis"]["structure_properties"], original["structure_properties"])
        self.assertEqual(payload["varied_classes"], ["metal_1", "temperature_c", "time_h"])
        self.assertEqual(json.loads(self.write_base().read_text()), original)

    def test_success_snapshot_keeps_deduplicated_model_parent_identity(self):
        other = {**self.base, "mof_name": "MOF-B", "reference": "unique-parent"}
        self.write_base(index=1)
        self.write_base(index=2)
        self.write_base(index=3, synthesis=other)
        successes = neg._load_all_success_jsons(self.doi, str(self.success_dir))
        self.assertEqual(len(successes), 2)
        model = self.plan(temperature_c=[60])
        model.plans[0].based_on_success_index = 2
        neg.save_plan_payloads(self.doi, "{}", model, str(self.plan_dir), successes)
        self.write_plans(self.plan_rows(index=2, temperature_c=[60]))
        self.expand()
        frame = pd.read_csv(self.enum_csv)
        payload = json.loads(Path(frame.iloc[0]["parsed_json"]).read_text())
        self.assertEqual(payload["synthesis"]["reference"], "unique-parent")
        self.assertEqual(payload["based_on_success_index"], 2)

    def test_corrupt_or_out_of_range_snapshot_cannot_fall_back(self):
        self.write_base()
        parent = self.plan_dir / neg.sanitize_for_path(self.doi)
        parent.mkdir(parents=True)
        snapshot = parent / "success_bases.json"
        for contents in ("{invalid", json.dumps({"doi": self.doi, "syntheses": []}),
                         json.dumps({"doi": "wrong-doi", "syntheses": [self.base]})):
            snapshot.write_text(contents)
            with self.assertRaisesRegex(ValueError, "Cannot use recorded parent"):
                enum.read_success_syn(self.doi, 1, str(self.success_dir), str(self.plan_dir))

    def test_missing_or_changed_recorded_snapshot_cannot_use_legacy_parent(self):
        self.write_base()
        values = neg._load_all_success_jsons(self.doi, str(self.success_dir))
        neg.save_plan_payloads(self.doi, "{}", self.plan(temperature_c=[60]), str(self.plan_dir), values)
        snapshot = self.plan_dir / neg.sanitize_for_path(self.doi) / "success_bases.json"
        contents = snapshot.read_text()
        snapshot.unlink()
        with self.assertRaisesRegex(ValueError, "snapshot is missing"):
            enum.read_success_syn(self.doi, 1, str(self.success_dir), str(self.plan_dir))
        snapshot.write_text(contents + " ")
        with self.assertRaisesRegex(ValueError, "snapshot has changed"):
            enum.read_success_syn(self.doi, 1, str(self.success_dir), str(self.plan_dir))

    def test_parent_snapshot_preserves_gaps_and_skipped_unreadable_files(self):
        self.write_base(index=1)
        later = self.write_base(index=3, synthesis={**self.base, "mof_name": "MOF-C"})
        later.with_name("synthesis_002.json").mkdir()
        values = neg._load_all_success_jsons(self.doi, str(self.success_dir))
        self.assertEqual(len(values), 2)
        neg.save_plan_payloads(self.doi, "{}", self.plan(temperature_c=[60]), str(self.plan_dir), values)
        self.assertEqual(enum.read_success_syn(self.doi, 2, str(self.success_dir), str(self.plan_dir))["mof_name"], "MOF-C")

    def test_all_empty_options_are_not_enumerated(self):
        self.write_base()
        row = self.plan_rows(temperature_c=[60])[0]
        row["temperature_c_options"] = "[]"
        self.write_plans([row])
        result = self.expand()
        self.assertEqual(result["rows_written"], 0)
        self.assertFalse(self.enum_csv.exists())

    def test_exclusions_apply_with_both_logging_settings(self):
        rows = []
        for doi, index in [("10.1002/chem.201802189", 2), ("10.1021/acsmaterialslett.0c00456", 1)]:
            self.write_base(doi=doi, index=index)
            rows.extend(self.plan_rows(doi=doi, index=index, temperature_c=[60]))
        self.write_plans(rows)
        for verbosity in (True, False):
            self.expand(verbose_skip=verbosity)
            self.assertFalse(self.enum_csv.exists())
            self.assertFalse(self.enum_dir.exists())

    def test_original_curated_options_and_rounding(self):
        doi = "10.1002/chem.201802189"
        self.write_base(doi=doi)
        self.write_plans(self.plan_rows(
            doi=doi, temperature_c=[60], time_h=[4],
            metal_1=[{"name_full": value} for value in ("A", "B", "C")],
            linker_1=[{"name_full": value} for value in ("L1", "L2", "L3", "L4")],
        ))
        self.expand()
        frame = pd.read_csv(self.enum_csv)
        self.assertEqual(len(frame), 8)
        self.assertEqual(set(frame["metal_1"]), {"A", "B"})
        self.assertEqual(set(frame["linker_1"]), {"L1", "L2"})
        self.assertEqual(set(frame["temperature_c"]), {80, 140})
        self.assertEqual(set(frame["time_h"]), {12})

    def test_resume_skips_existing_pair_without_rewriting(self):
        self.write_base()
        self.write_plans(self.plan_rows(temperature_c=[60, 80]))
        self.expand()
        before = self.enum_csv.read_bytes()
        self.expand()
        self.assertEqual(self.enum_csv.read_bytes(), before)
        self.assertEqual(len(list(self.enum_dir.rglob("combo_*.json"))), 2)

    def test_enumeration_preview_writes_nothing(self):
        self.write_base()
        self.write_plans(self.plan_rows(temperature_c=[60]))
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        preview = self.expand(dry_run=True)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(preview, [{"doi": self.doi, "based_on_success_index": 1}])
        self.assertEqual(before, after)

    def test_mining_preview_deduplicates_yes_dois_without_writes(self):
        manifest = self.root / "manifest.csv"
        pd.DataFrame([
            {"DOI": self.doi, "Main File": "main.pdf", "SI File": ""},
            {"DOI": self.doi, "Main File": "duplicate.pdf", "SI File": ""},
            {"DOI": "10.0000/no", "Main File": "no.pdf", "SI File": ""},
        ]).to_csv(manifest, index=False)
        positive = self.root / "positive.csv"
        pd.DataFrame([
            {"doi": self.doi, "article_trial_or_failure": " YES "},
            {"doi": "10.0000/no", "article_trial_or_failure": "no"},
        ]).to_csv(positive, index=False)
        with patch.object(neg, "_make_client", side_effect=AssertionError("unexpected client")), contextlib.redirect_stdout(io.StringIO()):
            preview = neg.run_negative(str(manifest), str(positive), str(self.plan_csv),
                                       json_out_dir=str(self.plan_dir), summarize_trials_first=True, dry_run=True)
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["main_pdf"], "main.pdf")
        self.assertFalse(self.plan_csv.exists())
        self.assertFalse(self.plan_dir.exists())
        self.assertFalse((self.root / "mof_trials_yes_7.csv").exists())

    def test_failed_worker_is_recorded_without_success_artifacts(self):
        with patch.object(neg, "_make_client", side_effect=ValueError("missing credentials")), contextlib.redirect_stdout(io.StringIO()):
            result = neg.process_negative_item_yes(
                {"doi": self.doi, "main_pdf": "", "si_pdf": ""}, "gpt-5", str(self.plan_dir), "absent.csv", {self.doi}
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["rows"][0]["error"], "missing credentials")
        self.assertFalse(self.plan_dir.exists())


if __name__ == "__main__":
    unittest.main()
