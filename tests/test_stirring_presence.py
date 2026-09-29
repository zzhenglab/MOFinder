"""Regressions for the three-state stirring control's reporting boundaries."""
import unittest

from mofinder.curation.stirring_presence import classify_stirring
from mofinder.datasets.process_enrich_9field import extend_prompt
from mofinder.training.records import REACTION_PROMPT_FILE


class StirringPresenceTests(unittest.TestCase):
    def check_cases(self, expected, cases):
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(classify_stirring(raw)["stirring"], expected)

    def test_static_stage_overrides_preparation_and_workup_stirring(self):
        self.check_cases("no", (
            "static", "without stirring", "undisturbed", "no stirring, air atmosphere",
            "stirred 30 min, then static", "static (after pre-stir/sonication)",
            "stirred 30 min before heating; then static hydrothermal; stirred after cooling",
            "stirred during reflux; static during diffusion", "mixed, then static",
            "RPB 1500 rpm, then static", "sonicated before static heating",
            "Mixed 10 min under stirring, then left standing at RT for 20 days",
        ))

    def test_preparation_without_explicit_static_is_yes(self):
        self.check_cases("yes", (
            "stirred", "STIRRING", "stirred before heating", "stirred during preparation",
            "stirred during mixing; aged overnight", "stirred during synthesis",
            "rotation (30 rpm); 30 min pre-stir before capping",
            "gentle stirring, tube rotator 20 rpm", "stirred and sonicated",
        ))

    def test_other_methods_and_unresolved_descriptions_are_not_negative_evidence(self):
        self.check_cases("not reported", (
            None, "", "not_reported", "sonicated", "shaken", "vortexed", "mixed",
            "rotated", "agitated", "centrifuged at 10,000 rpm", "dropwise addition under Ar",
            "reflux", "microwave irradiation", "with or without stirring", "not static",
            "static at first, then stirred during heating", "500 rpm",
        ))

    def test_doi_scoped_reviews_preserved(self):
        cases = (
            ("vigorous 5 min before heating", "10.1039/c4ta02568g", "yes"),
            ("500 rpm", "10.1039/d4gc01350f", "yes"),
            ("500 rpm", "10.1234/unrelated", "not reported"),
            ("ultrasonically stirred 15 min before heating", "10.1039/c4ce00158c", "not reported"),
            ("agitated 30 min, then static", "10.1021/acssuschemeng.4c00730", "no"),
            ("agitated", "10.1002/adma.201901570", "yes"),
        )
        for raw, doi, expected in cases:
            with self.subTest(raw=raw, doi=doi):
                self.assertEqual(classify_stirring(raw, doi)["stirring"], expected)

    def test_canonical_prompt_describes_exact_new_field_and_meanings(self):
        prompt = REACTION_PROMPT_FILE.with_name("reaction_prediction_process_enrich_9field.txt").read_text(encoding="utf-8")
        self.assertEqual(extend_prompt(REACTION_PROMPT_FILE.read_text(encoding="utf-8")), prompt)
        for field in ("vessel_type", "vessel_volume_mL", "agitation"):
            self.assertNotIn(field, prompt)
        for value in ("'yes'", "'no'", "'not reported'"):
            self.assertIn(value, prompt)
        self.assertIn("does not imply continuous stirring", prompt)
        with self.assertRaises(ValueError):
            extend_prompt("Unrecognized system prompt")


if __name__ == "__main__":
    unittest.main()
