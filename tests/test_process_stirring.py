"""Stage and ambiguity regressions drawn from the complete raw-value audit."""
import unittest

from mofinder.curation.process_stirring import normalize_stirring


class ProcessStirringTests(unittest.TestCase):
    def assertClass(self, raw, expected, detailed=None):
        result = normalize_stirring(raw)
        self.assertEqual(result["value"], expected, (raw, result))
        original_label = detailed or {
            "No stirring": "Static / no stirring",
        }.get(expected, expected)
        self.assertEqual(result["detailed_value"], original_label, (raw, result))
        expected_rule = "shorten_agitation_label" if original_label != expected else ""
        self.assertEqual(result["consolidation_rule"], expected_rule)
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
                         "Homogenized before static synthesis")
        self.assertClass("RPB 1500 rpm, then static", "Rotated before static synthesis")

    def test_preparation_does_not_imply_a_static_reaction(self):
        for raw in ("stirred 1 h before heating", "stirred (pre-mix)",
                    "stirred 30 min then heated", "stirred during mixing; aged overnight",
                    "stirring described prior to sealing", "stirred 10 min, then sealed and heated"):
            self.assertClass(raw, "Stirred during preparation")
        self.assertClass("sonicated (pre-dissolution), then heated",
                         "Sonicated during preparation")

    def test_typographical_variants(self):
        first = normalize_stirring("  PRE\u2011STIRRED\u00a030 min; STATIC\t during HEATING ")
        second = normalize_stirring("pre-stirred 30 min; static during heating")
        self.assertEqual(first, second)

    def test_rotation_is_not_lost_behind_prestirring(self):
        self.assertClass("rotation (30 rpm); 30 min pre-stir before capping", "Rotated; stage not reported")
        self.assertClass("static (no rotation); 30 min pre-stir before capping", "Stirred before static synthesis")
        self.assertClass("rotated (1.1 kHz MAS)", "Rotated; stage not reported")

    def test_reviewed_rare_descriptions_preserve_uncertainty(self):
        self.assertEqual(normalize_stirring("vigorous 5 min before heating")["value"], "Not reported")
        self.assertClass("stirred 20 min; layered slow diffusion", "Stirred during preparation")
        self.assertClass("sonicated 20 min; refluxed", "Sonicated during preparation")
        self.assertClass("static during synthesis; stirred after cooling", "No stirring")

    def test_static_does_not_mistake_negative_stirring_for_positive(self):
        for raw in ("static", "no stirring, air atmosphere", "without stirring", "undisturbed"):
            self.assertClass(raw, "No stirring")

    def test_missing_and_nonempty_indeterminate_remain_distinct_in_audit(self):
        for raw in (None, "", float("nan"), "not_reported", "Not reported"):
            self.assertClass(raw, "Not reported")
        for raw in ("with or without stirring", "centrifuged at 10,000 rpm", "reflux",
                    "dropwise addition under Ar", "microwave irradiation", "not static", "novel description",
                    "static at first, then stirred during heating"):
            parsed = normalize_stirring(raw)
            self.assertEqual(parsed["value"], "Not reported")
            self.assertEqual(parsed["detailed_value"], "Unclear / ambiguous")
            self.assertEqual(parsed["consolidation_rule"], "no_unique_supported_agitation_state")
            self.assertTrue(parsed["review_reason"])

    def test_rare_methods_keep_specific_labels(self):
        cases = {
            "mixed, then static": "Mixed before static synthesis",
            "shaken": "Shaken; stage not reported",
            "sonicated": "Sonicated; stage not reported",
            "sonicated before heating": "Sonicated during preparation",
            "mixed": "Mixed; stage not reported",
            "mixed before heating": "Mixed during preparation",
            "stirred throughout the reaction": "Stirred during synthesis",
        }
        for raw, detailed in cases.items():
            with self.subTest(raw=raw):
                self.assertClass(raw, detailed)

    def test_reported_reaction_agitation_is_not_lost_with_heating_or_addition(self):
        self.assertClass("microwave irradiation with stirring during synthesis",
                         "Stirred during synthesis")
        self.assertClass("dropwise addition under Ar with stirring during addition",
                         "Stirred during preparation")
        self.assertClass("centrifuged then stirred", "Stirred; stage not reported")

    def test_source_reviews_are_scoped_by_doi_and_raw_text(self):
        raw = "vigorous 5 min before heating"
        parsed = normalize_stirring(raw, "https://doi.org/10.1039/C4TA02568G")
        self.assertEqual(parsed["value"], "Stirred during preparation")
        self.assertEqual(parsed["consolidation_rule"], "source_verified_method_stage")
        self.assertTrue(parsed["rule"].startswith("source_review:"))
        self.assertEqual(normalize_stirring(raw, "10.1234/unrelated")["value"], "Not reported")
        self.assertEqual(normalize_stirring("agitated", "10.1002/adma.201901570")["value"], "Stirred during preparation")
        self.assertEqual(normalize_stirring("500 rpm")["value"], "Not reported")
        self.assertEqual(normalize_stirring("500 rpm", "10.1039/d4gc01350f")["value"], "Stirred during synthesis")

    def test_ultrasonic_source_review_does_not_imply_mechanical_stirring(self):
        parsed = normalize_stirring("ultrasonically stirred 15 min before heating", "10.1039/c4ce00158c")
        self.assertEqual(parsed["value"], "Sonicated during preparation")

    def test_all_source_reviews_produce_compact_supported_labels(self):
        from mofinder.curation.agitation_source_reviews import SOURCE_REVIEWS
        for review in SOURCE_REVIEWS:
            with self.subTest(doi=review['doi'], raw=review['raw_value']):
                parsed = normalize_stirring(review['raw_value'], review['doi'])
                self.assertNotEqual(parsed['value'], 'Not reported')
                self.assertTrue(2 <= len(parsed['value'].split()) <= 5)
                self.assertFalse(parsed['review_reason'])
                self.assertNotIn('Other', parsed['value'])
                self.assertNotIn('pooled', parsed['value'].lower())


if __name__ == "__main__":
    unittest.main()
