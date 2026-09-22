"""Reaction-time ranges, phrase conventions, and numeric-value precedence."""
import unittest

from mofinder.curation.times import normalize_time_hours, parse_time_hours


class ReactionTimeTests(unittest.TestCase):
    def test_hour_ranges_and_upper_limits(self):
        cases = {
            "48–72 h": 72,
            "48–72 hours": 72,
            "48-72 h": 72,
            "48—72 hours": 72,
            "12–24 h (stirred)": 24,
            "48 h to 72 h": 72,
            "up to 72 hours": 72,
            "to 120 h": 120,
            "0.5–4 h": 4,
            "heated for 12 to 24 hrs at 120 °C": 24,
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_time_hours(phrase), expected)

    def test_day_week_month_ranges(self):
        cases = {
            "2–4 days": 96,
            "2 to 4 days": 96,
            "2–4 d": 96,
            "2–4 weeks": 672,
            "2 to 4 weeks": 672,
            "2—4 months": 2880,
            "2 to 4 months": 2880,
            "48 h to 4 days": 96,
            "4 to 2 weeks": 672,
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_time_hours(phrase), expected)

    def test_overnight_in_sentences(self):
        for phrase in ("overnight", "The mixture was stirred overnight.", "OVERNIGHT (static)"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_time_hours(phrase), 12)

    def test_several_and_serval_conventions(self):
        for spelling in ("several", "serval"):
            for unit, expected in (("days", 144), ("weeks", 432), ("months", 2160)):
                phrase = f"Crystals formed after {spelling} {unit}."
                with self.subTest(phrase=phrase):
                    self.assertEqual(parse_time_hours(phrase), expected)

    def test_immediate_requires_no_number(self):
        for phrase in ("immediate", "precipitation immediately occurs", "An immediate precipitate formed."):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_time_hours(phrase), 0.1)
        for phrase in ("crystals formed immediately (≤5 min)", "immediate at 25 °C", "24 h, filtered immediately"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(parse_time_hours(phrase))

    def test_unrelated_and_unsupported_text_stays_unresolved(self):
        for phrase in (None, "", "not reported", "several hours", "heated to 120 °C", "48–72 °C", "24 h"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(parse_time_hours(phrase))

    def test_explicit_ranges_precede_qualitative_phrases(self):
        self.assertEqual(parse_time_hours("overnight (12–24 h)"), 24)
        self.assertEqual(parse_time_hours("several days, up to 10 days"), 240)

    def test_reported_numeric_hours_are_preserved(self):
        for value, text in (("36", "36 h hydrothermal; stirred overnight before heating"),
                            ("24", "24 h after 2–3 d aging at RT"),
                            ("14", "14 h (overnight)"),
                            (0, "immediate")):
            with self.subTest(value=value, text=text):
                self.assertEqual(normalize_time_hours(value, text), value)

    def test_missing_and_textual_hours_use_supported_phrases(self):
        self.assertEqual(normalize_time_hours("", "overnight"), "12")
        self.assertEqual(normalize_time_hours(float("nan"), "2–4 weeks"), "672")
        self.assertEqual(normalize_time_hours("unknown", "immediate"), "0.1")
        self.assertEqual(normalize_time_hours("48–72 h", ""), "72")
        self.assertEqual(normalize_time_hours("unknown", "24 h"), "unknown")


if __name__ == "__main__":
    unittest.main()
