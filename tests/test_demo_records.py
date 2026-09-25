"""Verify comparison failures and preservation of independent demo run records."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mofinder.demo_records import DemoRun, verify_files


class DemoRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.demo = self.root / "Demo/01_test"
        self.output = self.demo / "outputs"
        self.expected = self.demo / "expected"
        self.output.mkdir(parents=True)
        self.expected.mkdir()

    def test_same_row_count_does_not_hide_changed_chemical_values(self):
        (self.expected / "records.csv").write_text("metal,time_h\nZn,24\n", encoding="utf-8")
        (self.output / "records.csv").write_text("metal,time_h\nCu,24\n", encoding="utf-8")
        result = verify_files(self.output, self.expected, ["records.csv"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][0]["expected_rows"], 1)
        self.assertEqual(result["checks"][0]["actual_rows"], 1)

    def test_missing_output_is_a_failed_check(self):
        result = verify_files(self.output, self.expected, ["absent.jsonl"])
        self.assertFalse(result["passed"])

    def test_jsonl_comparison_preserves_order_and_ignores_line_endings(self):
        expected = b'{"label":"P"}\n{"label":"N"}\n'
        (self.expected / "records.jsonl").write_bytes(expected)
        actual = self.output / "records.jsonl"
        actual.write_bytes(expected.replace(b"\n", b"\r\n"))
        self.assertTrue(verify_files(self.output, self.expected, ["records.jsonl"])["passed"])
        actual.write_bytes(b'{"label":"N"}\n{"label":"P"}\n')
        self.assertFalse(verify_files(self.output, self.expected, ["records.jsonl"])["passed"])

    def test_reruns_and_failed_checks_preserve_previous_artifacts(self):
        output = self.output / "records.csv"
        output.write_text("metal\nZn\n", encoding="utf-8")
        with DemoRun(self.demo, self.output, {"source": output}) as first:
            (first.work_dir / "records.csv").write_bytes(output.read_bytes())
            first.verification = {"passed": True, "checks": []}
            print("first run")
        original = (first.folder / "outputs/records.csv").read_bytes()
        changed = b"metal\nCu\n"
        with self.assertRaisesRegex(AssertionError, "does not match"):
            with DemoRun(self.demo, self.output, {"source": output}) as second:
                (second.work_dir / "records.csv").write_bytes(changed)
                second.verification = {"passed": False, "checks": []}
                raise AssertionError("does not match")
        self.assertNotEqual(first.folder, second.folder)
        self.assertEqual((first.folder / "outputs/records.csv").read_bytes(), original)
        self.assertEqual((second.folder / "outputs/records.csv").read_bytes(), changed)
        self.assertEqual(output.read_bytes(), original)  # Failed work does not replace latest successful output.
        first_record = json.loads(first.record_path.read_text())
        self.assertEqual(first_record["artifacts"][0]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertIn("first run", (first.folder / "run.log").read_text())
        self.assertEqual(json.loads(second.record_path.read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
