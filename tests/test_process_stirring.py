"""Stage and ambiguity regressions drawn from the complete raw-value audit."""
import unittest

from mofinder.curation.process_stirring import normalize_stirring


class ProcessStirringTests(unittest.TestCase):
    def assertClass(self, raw, expected):
        result = normalize_stirring(raw)
        self.assertEqual(result["value"], expected, (raw, result))
        self.assertEqual(result["review_reason"], "")

    def test_unqualified_stirring_does_not_imply_continuous_reaction_stirring(self):
        for raw in ("stirred", "STIRRING", "continuous stirring", "constant stirring",
                    "stirred (300 r s\u22121)", "stirred (~800 RPM)", "stirred vigorously 15 min at RT"):
            with self.subTest(raw=raw):
                self.assertClass(raw, "Stirred; stage not reported")

    def test_explicit_stirring_during_synthesis(self):
        for raw in ("magnetic stirring under reflux", "stirred (reflux)",
                    "gentle stirring, maintained to end",
                    "vigorous stirring initially; gentle stirring during conversion"):
            self.assertClass(raw, "Stirred during synthesis")

    def test_static_synthesis_takes_precedence_over_premixing(self):
        for raw in ("stirred 12\u201318 h at RT, then static during solvothermal step",
                    "static (after pre-stir/sonication)", "stirred during reflux; static during diffusion",
                    "static (heated without stirring; initially stirred to dissolve)",
                    "stirred 30 min before heating; then static hydrothermal; stirred after cooling",
                    "Mixed 10 min under stirring, then left standing at RT for 20 days",
                    "vigorous stirring ~30 min, then aged without stirring"):
            self.assertClass(raw, "Stirred before static synthesis")

    def test_sonication_and_other_premixing_before_static(self):
        self.assertClass("ultrasound-assisted dissolution; static during heating", "Sonicated before static synthesis")
        self.assertClass("static; ultrasonically vibrated 10\u201320 min before heating", "Sonicated before static synthesis")
        self.assertClass("shear homogenized at 11,500 rpm for 2 min; then static at 4 \u00b0C",
                         "Other agitation before static synthesis")
        self.assertClass("RPB 1500 rpm, then static", "Other agitation before static synthesis")

    def test_preparation_does_not_imply_a_static_reaction(self):
        for raw in ("stirred 1 h before heating", "stirred (pre-mix)",
                    "stirred 30 min then heated", "stirred during mixing; aged overnight",
                    "stirring described prior to sealing", "stirred 10 min, then sealed and heated"):
            self.assertClass(raw, "Stirred during preparation; later agitation not reported")
        self.assertClass("sonicated (pre-dissolution), then heated",
                         "Sonicated during preparation; later agitation not reported")

    def test_typographical_variants(self):
        first = normalize_stirring("  PRE\u2011STIRRED\u00a030 min; STATIC\t during HEATING ")
        second = normalize_stirring("pre-stirred 30 min; static during heating")
        self.assertEqual(first, second)

    def test_rotation_is_not_lost_behind_prestirring(self):
        self.assertClass("rotation (30 rpm); 30 min pre-stir before capping", "Shaken / rotated; stage not reported")
        self.assertClass("static (no rotation); 30 min pre-stir before capping", "Stirred before static synthesis")
        self.assertClass("rotated (1.1 kHz MAS)", "Shaken / rotated; stage not reported")

    def test_reviewed_rare_descriptions_preserve_uncertainty(self):
        self.assertClass("vigorous 5 min before heating", "Other agitation during preparation; later agitation not reported")
        self.assertClass("stirred 20 min; layered slow diffusion", "Stirred during preparation; later agitation not reported")
        self.assertClass("sonicated 20 min; refluxed", "Sonicated during preparation; later agitation not reported")
        self.assertClass("static during synthesis; stirred after cooling", "Static / no stirring")

    def test_static_does_not_mistake_negative_stirring_for_positive(self):
        for raw in ("static", "no stirring, air atmosphere", "without stirring", "undisturbed"):
            self.assertClass(raw, "Static / no stirring")

    def test_missing_and_nonempty_unresolved_are_distinct(self):
        for raw in (None, "", float("nan"), "not_reported", "Not reported"):
            self.assertClass(raw, "Not reported")
        for raw in ("with or without stirring", "centrifuged at 10,000 rpm", "reflux",
                    "dropwise addition under Ar", "microwave irradiation", "not static", "novel description",
                    "static at first, then stirred during heating"):
            parsed = normalize_stirring(raw)
            self.assertEqual(parsed["value"], "Unclear / ambiguous")
            self.assertTrue(parsed["review_reason"])


if __name__ == "__main__":
    unittest.main()
