"""Chemical conversion, branch-specific filtering, and protected-record checks."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from mofinder.curation import load_config, run_pipeline, validate_inputs


@unittest.skipUnless(importlib.util.find_spec("pandas"), "Install the curation extra for curation tests.")
class CurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from mofinder.curation import initial, metals, linkers, solvents, features, descriptions, trimming
        cls.pd = pd
        cls.modules = dict(initial=initial, metals=metals, linkers=linkers, solvents=solvents, features=features, descriptions=descriptions, trimming=trimming)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lookup = self.root / "mw.csv"
        self.lookup.write_text('terephthalic acid,166.13\n"1,4-dicarboxybenzene",166.13\n', encoding="utf-8")

    def row(self, **changes):
        row = dict(doi="10.1234/example", main_pdf="example.pdf", si_pdf="", article_trial_or_failure="yes",
                   metal_1="Zn(NO3)2·6H2O", metal_1_amount_value="0.1", metal_1_amount_unit="mmol", metal_1_amount_text="0.1 mmol",
                   linker_1="terephthalic acid", linker_1_amount_value="16.613", linker_1_amount_unit="mg", linker_1_amount_text="16.613 mg",
                   solvent_main="N,N-dimethylformamide", solvent_main_abbr="DMF", solvent_main_amount_text="10 mL", solvent_main_ml="10",
                   temperature_c="100", temperature_c_text="100 C", time_h="24", vessel_type="glass vial", yield_percent="60",
                   metal_cluster_connectivity="Zn4O tetrahedral cluster", topology_code="pcu", mof_name="example", pore_diameter_A="10")
        row.update(changes)
        return row

    def stage(self, stage, rows, mode="positive", **kwargs):
        source, output = self.root / "input.csv", self.root / "output.csv"
        self.pd.DataFrame(rows).to_csv(source, index=False)
        module = self.modules[stage]
        function = getattr(module, f"clean_{mode}" if stage in {"initial", "linkers", "descriptions"} else "clean")
        if stage == "linkers":
            kwargs["linker_mw_path"] = self.lookup
        with redirect_stdout(StringIO()):
            function(source, output, **kwargs)
        return self.pd.read_csv(output, dtype=str, keep_default_na=False)

    def settings(self):
        return {"linker_mw_csv": self.lookup,
                "positive": {"input_csv": self.root / "input.csv", "output_dir": self.root / "positive"},
                "negative": {"input_csv": self.root / "input.csv", "output_dir": self.root / "negative"},
                "trimming": {"top_n": 10, "yield_bottom_frac": 0.1}}

    def test_initial_retains_distinct_slow_cooling_rules_and_row_alignment(self):
        rows = [self.row(row_id="missing", main_pdf=""), self.row(row_id="slow", temperature_c_text="slow cooling"), self.row(row_id="ordinary")]
        positive = self.stage("initial", rows)
        negative = self.stage("initial", rows, mode="negative")
        self.assertEqual(positive.row_id.tolist(), ["ordinary"])
        self.assertEqual(negative.row_id.tolist(), ["slow", "ordinary"])
        self.assertEqual(negative.metal_1.tolist(), ["Zn(NO3)2·6H2O"] * 2)

    def test_empty_initial_selection_is_saved_and_pipeline_stops_clearly(self):
        self.pd.DataFrame([self.row(main_pdf="", si_pdf="")]).to_csv(self.root / "input.csv", index=False)
        with self.assertRaisesRegex(ValueError, "No records remain after positive initial"):
            run_pipeline(self.settings(), mode="positive", reports=False)
        path = self.root / "positive/mof_extraction_1.csv"
        frame = self.pd.read_csv(path)
        self.assertEqual(len(frame), 0)
        self.assertIn("article_trial_or_failure", frame.columns)

    def test_initial_retains_distinct_pore_outlier_rules(self):
        rows = [self.row(pore_diameter_A=str(v)) for v in (10, 20, 30)]
        self.assertEqual(self.stage("initial", rows).pore_diameter_A.tolist(), ["10", "20", "30"])
        self.assertEqual(self.stage("initial", rows, mode="negative").pore_diameter_A.tolist(), ["10", "20", ""])

    def test_initial_normalizes_room_temperature_crystal_code_and_topology(self):
        frame = self.stage("initial", [self.row(temperature_c="", temperature_c_text="RT", crystal_code="CCDC 123456", topology_code="pcu-a")])
        self.assertEqual(frame.loc[0, ["temperature_c", "crystal_code", "topology_code"]].tolist(), ["25", "123456", "pcu-a"])

    def test_both_initial_branches_fill_time_without_changing_source_text(self):
        cases = [("overnight", "", "12"), ("12–24 h (stirred)", "", "24"),
                 ("2 to 4 weeks", "", "672"), ("serval days", "", "144"),
                 ("several months", "", "2160"), ("immediately precipitated", "", "0.1"),
                 ("crystals formed immediately (≤5 min)", "", ""),
                 ("24 h after 2–3 d aging", "24", "24")]
        rows = [self.row(main_pdf="", time_h="", time_text="overnight")]
        rows += [self.row(time_h=value, time_text=text) for text, value, _ in cases]
        for mode in ("positive", "negative"):
            with self.subTest(mode=mode):
                frame = self.stage("initial", rows, mode=mode)
                self.assertEqual(frame.time_h.tolist(), [expected for _, _, expected in cases])
                self.assertEqual(frame.time_text.tolist(), [text for text, _, _ in cases])

    def test_metal_formula_mass_conversion_and_unique_short_pruning(self):
        rows = [self.row(row_id="mass", metal_1="Cu(NO3)2", metal_1_amount_value="187.556", metal_1_amount_unit="mg", metal_1_amount_text="187.556 mg"),
                self.row(row_id="single", metal_1="ZrCl4"),
                self.row(row_id="invalid", metal_1="MOF-5")]
        frame = self.stage("metals", rows)
        self.assertEqual(frame.row_id.tolist(), ["mass"])
        self.assertEqual(frame.loc[0, "metal_1_amount_unit"], "mmol")
        self.assertAlmostEqual(float(frame.loc[0, "metal_1_amount_value"]), 1.0, places=3)

    def test_formula_counts_include_complete_hydrate_and_bracket_multipliers(self):
        from mofinder.curation.formula import ATOM_MASS, molar_mass, parse_formula_counts
        cases = {
            "Cu(NO3)2": {"Cu": 1, "N": 2, "O": 6},
            "Zn(NO3)2·6H2O": {"Zn": 1, "N": 2, "O": 12, "H": 12},
            "Cu(NO3)2·2.5H2O": {"Cu": 1, "N": 2, "O": 8.5, "H": 5},
            "CaSO4·1/2H2O": {"Ca": 1, "S": 1, "O": 4.5, "H": 1},
            "[Cu(NH3)4]SO4·H2O": {"Cu": 1, "N": 4, "H": 14, "S": 1, "O": 5},
        }
        for formula, counts in cases.items():
            with self.subTest(formula=formula):
                self.assertEqual(parse_formula_counts(formula), counts)
                expected = sum(ATOM_MASS[element] * number for element, number in counts.items())
                self.assertAlmostEqual(molar_mass(formula), expected, places=8)

    def test_hydrated_precursor_mass_conversion_uses_corrected_formula_mass(self):
        from mofinder.curation.formula import ATOM_MASS
        mass = ATOM_MASS["Zn"] + 2 * ATOM_MASS["N"] + 12 * ATOM_MASS["O"] + 12 * ATOM_MASS["H"]
        frame = self.stage("metals", [self.row(metal_1_amount_value=str(mass), metal_1_amount_unit="mg", metal_1_amount_text=f"{mass} mg")])
        self.assertEqual(frame.loc[0, "metal_1_amount_unit"], "mmol")
        self.assertAlmostEqual(float(frame.loc[0, "metal_1_amount_value"]), 1.0, places=6)

    def test_linker_mass_micro_mol_and_equivalent_units(self):
        rows = [self.row(row_id="mg"), self.row(row_id="g", linker_1_amount_value="0.016613", linker_1_amount_unit="g"),
                self.row(row_id="micro", linker_1_amount_value="100", linker_1_amount_unit="µmol"),
                self.row(row_id="mol", linker_1_amount_value="0.0001", linker_1_amount_unit="mol"),
                self.row(row_id="eq", linker_1_amount_value="2", linker_1_amount_unit="eq"),
                self.row(row_id="unknown", linker_1="unmapped ligand", linker_1_amount_unit="mg")]
        frame = self.stage("linkers", rows)
        self.assertEqual(frame.row_id.tolist(), ["mg", "g", "micro", "mol", "eq"])
        self.assertEqual(frame.linker_1_amount_value.tolist(), ["0.1", "0.1", "0.1", "0.1", "2"])
        self.assertEqual(frame.linker_1_amount_unit.tolist(), ["mmol"] * 4 + ["eq"])

    def test_linker_branch_maps_remain_distinct(self):
        rows = [self.row(linker_1="1,4-dicarboxybenzene", linker_1_amount_unit="mmol")]
        self.assertEqual(self.stage("linkers", rows).loc[0, "linker_1"], "terephthalic acid")
        self.assertEqual(self.stage("linkers", rows, mode="negative").loc[0, "linker_1"], "1,4-dicarboxybenzene")

    def test_h3btb_alias_normalization_and_mass_conversion(self):
        canonical = "1,3,5-Tris(4-carboxyphenyl)benzene"
        self.lookup.write_text('"1,3,5-tris(4-carboxyphenyl)benzene",438.4\n', encoding="utf-8")
        for mode in ("positive", "negative"):
            with self.subTest(mode=mode):
                rows = [self.row(linker_1=name, linker_1_amount_value="43.84") for name in ("h3btb", "H3BTB")]
                initial = self.stage("initial", rows, mode=mode)
                self.assertEqual(initial.linker_1.tolist(), [canonical] * 2)
                for inputs in (rows, initial.to_dict("records")):
                    converted = self.stage("linkers", inputs, mode=mode)
                    self.assertEqual(converted.linker_1.tolist(), [canonical] * 2)
                    self.assertEqual(converted.linker_1_amount_unit.tolist(), ["mmol"] * 2)
                    self.assertEqual(converted.linker_1_amount_value.tolist(), ["0.1"] * 2)

    def test_unresolved_linker_weights_keep_molar_values_and_filter_mass_values(self):
        self.lookup.write_text("unknown ligand,\nterephthalic acid,166.13\n", encoding="utf-8")
        rows = [self.row(row_id="known"),
                self.row(row_id="unknown_mass", linker_1="unknown ligand"),
                self.row(row_id="unknown_molar", linker_1="unknown ligand", linker_1_amount_value="0.1", linker_1_amount_unit="mmol")]
        self.pd.DataFrame(rows).to_csv(self.root / "input.csv", index=False)
        validation = validate_inputs(self.settings())
        self.assertTrue(validation["valid"], validation["issues"])
        lookup_check = validation["checks"][-1]
        self.assertEqual(lookup_check["known_weight_rows"], 1)
        self.assertEqual(lookup_check["unknown_weight_rows"], 1)
        for mode in ("positive", "negative"):
            with self.subTest(mode=mode):
                result = self.stage("linkers", rows, mode=mode)
                self.assertEqual(result.row_id.tolist(), ["known", "unknown_molar"])
                self.assertEqual(result.linker_1_amount_value.tolist(), ["0.1", "0.1"])

    def test_supplied_linker_table_retains_blank_weights_and_resolves_corrected_alias(self):
        repository = Path(__file__).resolve().parents[1]
        self.pd.DataFrame([self.row()]).to_csv(self.root / "input.csv", index=False)
        settings = self.settings()
        settings["linker_mw_csv"] = repository / "data/lookups/linker_molecular_weights.csv"
        result = validate_inputs(settings)
        self.assertTrue(result["valid"], result["issues"])
        lookup_check = result["checks"][-1]
        self.assertEqual(lookup_check["entries"], 591)
        self.assertEqual(lookup_check["known_weight_rows"], 217)
        self.assertEqual(lookup_check["unknown_weight_rows"], 374)
        self.assertEqual(lookup_check["known_weight_names"], 210)
        self.assertEqual(lookup_check["unknown_weight_names"], 372)
        self.lookup = settings["linker_mw_csv"]
        for mode in ("positive", "negative"):
            result = self.stage("linkers", [self.row(linker_1="H3BTB", linker_1_amount_value="43.84")], mode=mode)
            self.assertEqual(result.loc[0, "linker_1_amount_value"], "0.1")

    def test_lookup_validation_rejects_invalid_weights_and_conflicting_duplicates(self):
        self.pd.DataFrame([self.row()]).to_csv(self.root / "input.csv", index=False)
        for value in ("-1", "0", "inf", "nan", "unknown"):
            with self.subTest(value=value):
                self.lookup.write_text(f"unknown ligand,{value}\nterephthalic acid,166.13\n")
                self.assertFalse(validate_inputs(self.settings())["valid"])
        self.lookup.write_text("terephthalic acid,166.13\nTerephthalic acid,438.4\n")
        self.assertFalse(validate_inputs(self.settings())["valid"])

    def test_solvent_alias_and_density_inference(self):
        rows = [self.row(solvent_main="ethanol (absolute)", solvent_main_abbr="EtOH", solvent_main_ml="", solvent_main_amount_text="ethanol 789 mg"),
                self.row(solvent_main="water", solvent_main_abbr="H2O", solvent_main_ml="", solvent_main_amount_text="H2O 2 mL")]
        frame = self.stage("solvents", rows)
        self.assertEqual(frame.solvent_main.tolist(), ["ethanol", "water"])
        self.assertEqual([float(v) for v in frame.solvent_main_ml], [1.0, 2.0])

    def test_solvent_mapping_handles_missing_names_and_abbreviations(self):
        rows = [
            self.row(row_id="name_only", solvent_main="ethanol", solvent_main_abbr=None,
                     solvent_main_ml="", solvent_main_amount_text="ethanol 789 mg",
                     solvent_secondary=None, solvent_secondary_abbr=None),
            self.row(row_id="abbr_only", solvent_main=None, solvent_main_abbr="EtOH",
                     solvent_main_ml="", solvent_main_amount_text="ethanol 789 mg",
                     solvent_secondary=None, solvent_secondary_abbr="H2O"),
            self.row(row_id="unknown", solvent_main="unmapped solvent", solvent_main_abbr=None,
                     solvent_main_ml="5", solvent_main_amount_text="",
                     solvent_secondary="water", solvent_secondary_abbr=None),
            self.row(row_id="empty", solvent_main=None, solvent_main_abbr=None,
                     solvent_main_ml=None, solvent_main_amount_text=None),
        ]
        frame = self.stage("solvents", rows)
        self.assertEqual(frame.row_id.tolist(), ["name_only", "abbr_only", "unknown"])
        self.assertEqual(frame.solvent_main.tolist(), ["ethanol", "ethanol", "unmapped solvent"])
        self.assertEqual(frame.solvent_main_abbr.tolist(), ["EtOH", "EtOH", ""])
        self.assertEqual([float(v) for v in frame.solvent_main_ml], [1.0, 1.0, 5.0])
        self.assertEqual(frame.solvent_secondary.tolist(), ["", "water", "water"])
        self.assertEqual(frame.solvent_secondary_abbr.tolist(), ["", "H2O", "H2O"])

    def test_ratio_and_concentration_unit_gate_and_text_fallback(self):
        rows = [self.row(linker_1_amount_value="0.05", linker_1_amount_unit="mmol"),
                self.row(linker_1_amount_value="1", linker_1_amount_unit="eq", metal_1_amount_text="metal to ligand 1:1"),
                self.row(linker_1_amount_unit="mmol", solvent_main_ml="0")]
        frame = self.stage("features", rows)
        self.assertEqual(frame.M_L_ratio.tolist()[:2], ["2.00", "1.00"])
        self.assertEqual(frame.metel_concnertation.tolist(), ["10", "10", ""])
        self.assertLess(frame.columns.get_loc("M_L_ratio"), frame.columns.get_loc("temperature_c"))

    def test_descriptions_use_classified_positive_and_raw_negative_connectivity(self):
        rows = [self.row(metal_cluster_connectivity="tetrahedral Zn4O core", metal_cluster_connectivity_classified="tetramer cluster SBU")]
        positive = self.stage("descriptions", rows).loc[0, "mof_description"]
        negative = self.stage("descriptions", rows, mode="negative").loc[0, "mof_description"]
        self.assertIn("tetramer cluster SBU", positive)
        self.assertIn("tetrahedral Zn4O core", negative)
        self.assertNotIn("tetrahedral Zn4O core", positive)

    def test_trimming_protects_yes_and_mixed_dois_and_preserves_order(self):
        raw = self.pd.DataFrame([
            self.row(doi="10.1234/mixed", article_trial_or_failure="no", vessel_type="", row_id="mixed_no"),
            self.row(doi="10.1234/pure", article_trial_or_failure="no", vessel_type="", row_id="drop"),
            self.row(doi="https://doi.org/10.1234/mixed", article_trial_or_failure="yes", vessel_type="", row_id="yes"),
        ])
        result = self.modules["trimming"].apply_p_trimming(raw, top_n=0, verbose=False)
        self.assertEqual(result.row_id.tolist(), ["mixed_no", "yes"])
        self.pd.testing.assert_frame_equal(result, raw.iloc[[0, 2]])

    def test_trimming_vessel_majority_is_strict_and_yield_cut_includes_ties(self):
        rows = [self.row(doi="10.1234/half", article_trial_or_failure="no", vessel_type=v, row_id=f"half{i}") for i, v in enumerate(("vial", ""))]
        rows += [self.row(doi=f"10.1234/p{i}", article_trial_or_failure="no", row_id=f"p{i}", yield_percent=value) for i, value in enumerate(("10", "10", "20", "unknown"))]
        result = self.modules["trimming"].apply_p_trimming(self.pd.DataFrame(rows), top_n=0, verbose=False)
        self.assertEqual(result.row_id.tolist(), ["p2", "p3"])

    def test_trimming_rejects_unusable_doi_and_invalid_flags(self):
        for changes in ({"doi": "unknown"}, {"article_trial_or_failure": "unknown"}):
            with self.assertRaises(ValueError):
                self.modules["trimming"].apply_p_trimming(self.pd.DataFrame([self.row(**changes)]), verbose=False)

    def test_validation_requires_explicit_well_formed_mw_and_does_not_write(self):
        self.pd.DataFrame([self.row()]).to_csv(self.root / "input.csv", index=False)
        settings = self.settings()
        self.lookup.unlink()
        before = set(self.root.rglob("*"))
        result = validate_inputs(settings)
        self.assertFalse(result["valid"])
        self.assertIn("revised", " ".join(result["issues"]))
        self.assertEqual(before, set(self.root.rglob("*")))
        self.lookup.write_text("linker_name,mw\nterephthalic acid,0\n")
        self.assertFalse(validate_inputs(settings)["valid"])

    def test_full_pipeline_keeps_source_and_writes_both_stage6_and_optional_stage7(self):
        source = self.root / "input.csv"
        source_note = "Cu(NO3)2·1H2O; 25 °C; μmol; source notation ??"
        self.pd.DataFrame([self.row(time_h="", time_text="24–48 h", article_trial_or_failure_notes=source_note),
                           self.row(article_trial_or_failure_notes=source_note)]).to_csv(source, index=False)
        original = source.read_bytes()
        result = run_pipeline(self.settings(), reports=False)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(result["positive"]["output_csv"].endswith("_6_7.csv"))
        self.assertTrue(result["negative"]["output_csv"].endswith("_5_6.csv"))
        self.assertTrue((self.root / "positive/mof_extraction_1_2_3_4_5_6.csv").exists())
        positive = self.pd.read_csv(result["positive"]["output_csv"], dtype=str, keep_default_na=False)
        self.assertEqual(positive.linker_1_amount_value.tolist(), ["0.1", "0.1"])
        self.assertEqual(positive.metel_concnertation.tolist(), ["10", "10"])
        self.assertEqual(positive.time_h.tolist(), ["48", "24"])
        negative = self.pd.read_csv(result["negative"]["output_csv"], dtype=str, keep_default_na=False)
        self.assertEqual(negative.time_h.tolist(), ["48", "24"])
        for branch in result.values():
            for stage in branch["stages"]:
                output = Path(stage["output_csv"])
                self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"), output)
                frame = self.pd.read_csv(output, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                self.assertEqual(frame.article_trial_or_failure_notes.tolist(), [source_note, source_note])
        self.assertEqual(result["positive"]["time_parser"], "duration-phrases-v1")
        self.assertEqual(len(result["positive"]["input_sha256"]), 64)

    def test_config_paths_resolve_from_config_location(self):
        directory = self.root / "configs"
        directory.mkdir()
        config = directory / "curation.json"
        config.write_text(json.dumps({"project_root": "..", "linker_mw_csv": "mw.csv",
            "positive": {"input_csv": "positive.csv", "output_dir": "out/positive"},
            "negative": {"input_csv": "negative.csv", "output_dir": "out/negative"}}))
        settings = load_config(config)
        self.assertEqual(settings["linker_mw_csv"], self.lookup.resolve())
        self.assertEqual(settings["positive"]["output_dir"], (self.root / "out/positive").resolve())


if __name__ == "__main__":
    unittest.main()
