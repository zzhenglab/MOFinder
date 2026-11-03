"""File matching and optional document counts, without network or model calls."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mofinder.literature import match_documents as matching


@unittest.skipUnless(importlib.util.find_spec("pandas"), "Install pandas for document matching tests.")
class DocumentMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        cls.pd = pd

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.articles, self.si = self.root / "articles", self.root / "si"
        self.articles.mkdir()
        self.si.mkdir()

    def touch(self, directory, name):
        path = directory / name
        path.touch()
        return str(path)

    def test_matching_retains_rows_metadata_and_extension_precedence(self):
        self.touch(self.articles, "10.0000_ABC.PDF")
        for extension in ("pdf", "docx", "doc"):
            self.touch(self.si, f"10.0000_abc_SI.{extension}")
        self.touch(self.si, "10.0000_docx_SI.docx")
        self.touch(self.si, "10.0000_doc_SI.doc")
        self.touch(self.articles, "10.0000_main.pdf")
        self.touch(self.si, "10.0000_orphan_SI.pdf")
        frame = self.pd.DataFrame({
            "DOI": ["https://doi.org/10.0000/ABC", "doi: 10.0000/abc", "10.0000/docx",
                    "10.0000/doc", "10.0000/main", "10.0000/absent", ""],
            "Downloaded": ["0"] * 7, "SI Downloaded": ["SKIP"] * 7,
            "note": ["original"] * 7,
        })
        original = frame.copy(deep=True)
        updated, manifest, summary = matching.match_documents(frame, self.articles, self.si)
        self.pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(updated["DOI"].tolist(), frame["DOI"].tolist())
        self.assertEqual(updated["note"].tolist(), ["original"] * 7)
        self.assertEqual(updated["Downloaded"].tolist(), [1, 1, "", "", 1, "", ""])
        self.assertEqual(updated["SI Downloaded"].tolist(), [1, 1, 1, 1, "", "", ""])
        self.assertEqual(updated.at[0, "Found SI Filename"], "10.0000_abc_SI.pdf")
        self.assertEqual(manifest.columns.tolist(), ["DOI", "Main File", "SI File"])
        self.assertEqual([summary[key] for key in ("both_present", "only_main", "only_si", "neither")], [2, 1, 2, 2])
        self.assertEqual(summary["unmatched_si_files"], ["10.0000_orphan_SI.pdf"])
        self.assertEqual(summary["unmatched_main_files"], [])

    def test_required_si_optional_main_and_ambiguous_case(self):
        frame = self.pd.DataFrame({"DOI": ["10.0000/test"]})
        with self.assertWarns(UserWarning):
            _, _, summary = matching.match_documents(frame, self.root / "absent", self.si)
        self.assertFalse(summary["article_dir_exists"])
        with self.assertRaises(FileNotFoundError):
            matching.match_documents(frame, self.articles, self.root / "absent")
        lower = Path(self.touch(self.articles, "10.0000_test.pdf"))
        upper = Path(self.touch(self.articles, "10.0000_TEST.PDF"))
        # Supply both directory entries even on a case-insensitive filesystem.
        with patch.object(Path, "iterdir", return_value=iter([lower, upper])):
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                matching._file_lookup(self.articles, {".pdf"})

    def config(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({
            "project_root": ".", "input_file": "source.csv", "article_dir": "articles", "si_dir": "si",
        }))
        return matching.load_config(config_path)

    def test_output_paths_preserve_source_and_reject_aliases(self):
        config = self.config()
        source = config["input_file"]
        source.write_text("DOI,Downloaded,SI Downloaded\n10.0000/test,0,SKIP\n")
        original = source.read_bytes()
        self.touch(self.articles, "10.0000_test.pdf")
        summary = matching.run_matching(config)
        self.assertEqual(summary["main_present"], 1)
        self.assertEqual(source.read_bytes(), original)
        manifest = matching.read_table(config["manifest_file"])
        self.assertEqual(manifest.at[0, "Main File"], str((self.articles / "10.0000_test.pdf").resolve()))
        config["matched_inventory_file"] = source
        with self.assertRaisesRegex(ValueError, "read-only"):
            matching.run_matching(config)
        self.assertEqual(source.read_bytes(), original)

    def test_counts_preserve_existing_values_and_si_zero_preference(self):
        main = self.touch(self.articles, "main.pdf")
        si = self.touch(self.si, "si.pdf")
        doc = self.touch(self.si, "si.docx")
        missing = str(self.si / "missing.pdf")
        frame = self.pd.DataFrame({
            "DOI": ["a", "b", "c", "d", "e"],
            "Main File": [main] * 5,
            "SI File": [si, doc, missing, "", si],
            "Main Words": ["", 99, "", "", 0],
            "Main Tokens": ["", "", "", "", 0],
            "SI Words": ["", "", "", "", 0],
            "SI Tokens": ["", "", "", "", 0],
        })

        class Encoding:
            def encode(self, text):
                return list(text)

        def extract(path):
            return "one two three" if Path(path).name == "main.pdf" else "one two"

        with patch.object(matching, "read_pdf_text", side_effect=extract) as reader:
            counted, summary = matching.count_documents(frame, encoding=Encoding())
        self.assertEqual(counted["Main Words"].tolist(), [3, 99, 3, 3, 0])
        self.assertEqual(counted["Combined Words"].tolist(), [2, 0, 3, 3, 0])
        self.assertEqual(counted["Combined Tokens"].tolist(), [7, 0, 13, 13, 0])
        self.assertEqual(summary["statistics"]["Combined Words"]["total"], 8)
        self.assertEqual(summary["unsupported_files"], [doc])
        self.assertEqual(summary["missing_files"], [missing])
        self.assertEqual(reader.call_count, 5)

    def test_count_resume_refuses_changed_document_rows(self):
        config = self.config()
        config["matched_inventory_file"].parent.mkdir(parents=True)
        self.pd.DataFrame({"DOI": ["a"], "Main File": [""], "SI File": [""]}).to_csv(
            config["matched_inventory_file"], index=False)
        self.pd.DataFrame({"DOI": ["b"], "Main File": [""], "SI File": [""]}).to_csv(
            config["counts_file"], index=False)
        with self.assertRaisesRegex(ValueError, "Existing count rows differ"):
            matching.run_counting(config)


if __name__ == "__main__":
    unittest.main()
