"""Protect saved results when allocating numbered runs."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from mofinder.run_paths import create_run_directory


class RunDirectoryTests(unittest.TestCase):
    def test_numbering_preserves_gaps_legacy_runs_and_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            (parent / "run_001").mkdir()
            (parent / "run_999").write_text("preserve me", encoding="utf-8")
            (parent / "20260925T211347_05684043").mkdir()
            result = create_run_directory(parent)
            self.assertEqual(result.name, "run_1000")
            self.assertTrue(result.is_dir())
            self.assertEqual((parent / "run_999").read_text(), "preserve me")
            self.assertEqual(create_run_directory(parent, prefix="analysis").name, "analysis_001")

    def test_concurrent_runs_receive_independent_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "new_runs"
            with ThreadPoolExecutor(max_workers=8) as executor:
                folders = list(executor.map(lambda _: create_run_directory(parent), range(24)))
            self.assertEqual({folder.name for folder in folders},
                             {f"run_{number:03d}" for number in range(1, 25)})
            self.assertTrue(all(folder.is_dir() for folder in folders))


if __name__ == "__main__":
    unittest.main()
