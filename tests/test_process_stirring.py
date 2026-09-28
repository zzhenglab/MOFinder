"""Stage and ambiguity regressions drawn from the complete raw-value audit."""
import unittest

from mofinder.curation.process_stirring import STIRRING_CLASSES, normalize_stirring


class ProcessStirringTests(unittest.TestCase):
    def assertClass(self, raw, expected, detailed=None):
        result = normalize_stirring(raw)
        self.assertEqual(result["value"], expected, (raw, result))
        original_label = detailed or {
            "No stirring": "Static / no stirring",
        }.get(expected, expected)
        self.assertEqual(result["detailed_value"], original_label, (raw, result))
        expected_rule = ""
        if original_label == "Static / no stirring":
            expected_rule = "shorten_agitation_label"
        elif original_label != expected:
            expected_rule = "merge_nonsonication_methods_by_stage"
        self.assertEqual(result["consolidation_rule"], expected_rule)
        self.assertEqual(result["review_reason"], "")

    def test_unqualified_stirring_does_not_imply_continuous_reaction_stirring(self):
        for raw in ("stirred", "STIRRING", "continuous stirring", "constant stirring",
                    "stirred (300 r s\u22121)", "stirred (~800 RPM)", "stirred vigorously 15 min at RT"):
            with self.subTest(raw=raw):
                self.assertClass(raw, "Agitated; stage not reported", "Stirred; stage not reported")

    def test_explicit_stirring_during_synthesis(self):
        for raw in ("magnetic stirring under reflux", "stirred (reflux)",
                    "gentle stirring, maintained to end",
                    "vigorous stirring initially; gentle stirring during conversion"):
            self.assertClass(raw, "Agitated during synthesis", "Stirred during synthesis")

    def test_static_synthesis_takes_precedence_over_premixing(self):
        for raw in ("stirred 12\u201318 h at RT, then static during solvothermal step",
                    "static (after pre-stir/sonication)", "stirred during reflux; static during diffusion",
                    "static (heated without stirring; initially stirred to dissolve)",
                    "stirred 30 min before heating; then static hydrothermal; stirred after cooling",
                    "Mixed 10 min under stirring, then left standing at RT for 20 days",
                    "vigorous stirring ~30 min, then aged without stirring"):
            self.assertClass(raw, "Agitated before static synthesis", "Stirred before static synthesis")

    def test_sonication_and_other_premixing_before_static(self):
        self.assertClass("ultrasound-assisted dissolution; static during heating", "Sonicated before static synthesis")
        self.assertClass("static; ultrasonically vibrated 10\u201320 min before heating", "Sonicated before static synthesis")
        self.assertClass("shear homogenized at 11,500 rpm for 2 min; then static at 4 \u00b0C",
                         "Agitated before static synthesis", "Homogenized before static synthesis")
        self.assertClass("RPB 1500 rpm, then static", "Agitated before static synthesis",
                         "Rotated before static synthesis")

    def test_preparation_does_not_imply_a_static_reaction(self):
        for raw in ("stirred 1 h before heating", "stirred (pre-mix)",
                    "stirred 30 min then heated", "stirred during mixing; aged overnight",
                    "stirring described prior to sealing", "stirred 10 min, then sealed and heated"):
            self.assertClass(raw, "Agitated during preparation", "Stirred during preparation")
        self.assertClass("sonicated (pre-dissolution), then heated",
                         "Sonicated during preparation")

    def test_typographical_variants(self):
        first = normalize_stirring("  PRE\u2011STIRRED\u00a030 min; STATIC\t during HEATING ")
        second = normalize_stirring("pre-stirred 30 min; static during heating")
        self.assertEqual(first, second)

    def test_rotation_is_not_lost_behind_prestirring(self):
        self.assertClass("rotation (30 rpm); 30 min pre-stir before capping",
                         "Agitated; stage not reported", "Rotated; stage not reported")
        self.assertClass("static (no rotation); 30 min pre-stir before capping",
                         "Agitated before static synthesis", "Stirred before static synthesis")
        self.assertClass("rotated (1.1 kHz MAS)", "Agitated; stage not reported", "Rotated; stage not reported")

    def test_reviewed_rare_descriptions_preserve_uncertainty(self):
        self.assertEqual(normalize_stirring("vigorous 5 min before heating")["value"], "Not reported")
        self.assertClass("stirred 20 min; layered slow diffusion",
                         "Agitated during preparation", "Stirred during preparation")
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

    def test_methods_merge_by_stage_but_remain_specific_in_audit(self):
        cases = {
            "mixed, then static": ("Agitated before static synthesis", "Mixed before static synthesis"),
            "shaken": ("Agitated; stage not reported", "Shaken; stage not reported"),
            "sonicated": ("Sonicated; stage not reported", "Sonicated; stage not reported"),
            "sonicated before heating": ("Sonicated during preparation", "Sonicated during preparation"),
            "mixed": ("Agitated; stage not reported", "Mixed; stage not reported"),
            "mixed before heating": ("Agitated during preparation", "Mixed during preparation"),
            "stirred throughout the reaction": ("Agitated during synthesis", "Stirred during synthesis"),
            "vortexed": ("Agitated; stage not reported", "Vortexed; stage not reported"),
            "agitated before heating": ("Agitated during preparation", "Agitated during preparation"),
        }
        for raw, (expected, detailed) in cases.items():
            with self.subTest(raw=raw):
                self.assertClass(raw, expected, detailed)

    def test_reported_reaction_agitation_is_not_lost_with_heating_or_addition(self):
        self.assertClass("microwave irradiation with stirring during synthesis",
                         "Agitated during synthesis", "Stirred during synthesis")
        self.assertClass("dropwise addition under Ar with stirring during addition",
                         "Agitated during preparation", "Stirred during preparation")
        self.assertClass("centrifuged then stirred", "Agitated; stage not reported", "Stirred; stage not reported")

    def test_source_reviews_are_scoped_by_doi_and_raw_text(self):
        raw = "vigorous 5 min before heating"
        parsed = normalize_stirring(raw, "https://doi.org/10.1039/C4TA02568G")
        self.assertEqual(parsed["value"], "Agitated during preparation")
        self.assertEqual(parsed["detailed_value"], "Stirred during preparation")
        self.assertEqual(parsed["consolidation_rule"],
                         "source_verified_method_stage;merge_nonsonication_methods_by_stage")
        self.assertTrue(parsed["rule"].startswith("source_review:"))
        self.assertEqual(normalize_stirring(raw, "10.1234/unrelated")["value"], "Not reported")
        reviewed_agitation = normalize_stirring("agitated", "10.1002/adma.201901570")
        self.assertEqual(reviewed_agitation["value"], "Agitated during preparation")
        self.assertEqual(reviewed_agitation["detailed_value"], "Stirred during preparation")
        self.assertEqual(normalize_stirring("500 rpm")["value"], "Not reported")
        reviewed_rate = normalize_stirring("500 rpm", "10.1039/d4gc01350f")
        self.assertEqual(reviewed_rate["value"], "Agitated during synthesis")
        self.assertEqual(reviewed_rate["detailed_value"], "Stirred during synthesis")

    def test_ultrasonic_source_review_does_not_imply_mechanical_stirring(self):
        parsed = normalize_stirring("ultrasonically stirred 15 min before heating", "10.1039/c4ce00158c")
        self.assertEqual(parsed["value"], "Sonicated during preparation")
        self.assertEqual(parsed["detailed_value"], "Sonicated during preparation")
        self.assertEqual(parsed["consolidation_rule"], "source_verified_method_stage")

    def test_all_source_reviews_produce_compact_supported_labels(self):
        from mofinder.curation.agitation_source_reviews import SOURCE_REVIEWS
        self.assertEqual(len(STIRRING_CLASSES), 9)
        for review in SOURCE_REVIEWS:
            with self.subTest(doi=review['doi'], raw=review['raw_value']):
                parsed = normalize_stirring(review['raw_value'], review['doi'])
                self.assertNotEqual(parsed['value'], 'Not reported')
                self.assertIn(parsed['value'], STIRRING_CLASSES)
                self.assertTrue(2 <= len(parsed['value'].split()) <= 5)
                self.assertFalse(parsed['review_reason'])
                self.assertNotIn('Other', parsed['value'])
                self.assertNotIn('pooled', parsed['value'].lower())

    def test_new_sonication_synthesis_state_requires_class_map_review(self):
        with self.assertRaisesRegex(ValueError, "outside the nine-class schema"):
            normalize_stirring("sonicated throughout the reaction")


if __name__ == "__main__":
    unittest.main()
