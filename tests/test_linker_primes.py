"""Exact linker glyph restoration and corrected derivative provenance."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from mofinder.curation.linker_primes import correct_csv, correct_frame, correct_record, load_corrections

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "data/organic_linker_info/linker_prime_corrections.json"


class LinkerPrimeTests(unittest.TestCase):
    def test_exact_doi_and_complete_field_matching(self):
        lookup = load_corrections(LOOKUP)
        original = {
            "doi": "10.1021/ic901133k", "linker_1": "2,2?-bipyrimidine",
            "linker_2": "unresolved?", "metal_1": "Cu(NO3)2??1H2O",
            "mof_description": "2,2?-bipyrimidine", "time_text": "overnight?",
        }
        corrected, count = correct_record(original, lookup)
        self.assertEqual(count, 1)
        self.assertEqual(corrected["linker_1"], "2,2′-bipyrimidine")
        for key in original.keys() - {"linker_1"}:
            self.assertEqual(corrected[key], original[key])
        for change in ({"doi": "10.1234/other"}, {"linker_1": "2,2?-bipyrimidine (ligand)"}):
            record = original | change
            self.assertEqual(correct_record(record, lookup), (record, 0))

    def test_distinct_prime_glyphs_and_nonprime_symbols(self):
        lookup = load_corrections(LOOKUP)
        old = "4?,4?,4??,4??-(ethene-1,1,2,2-tetrayl)tetrakis([1,1?-biphenyl]-4-carboxylic acid)"
        result, count = correct_record({"doi": "10.1021/acs.cgd.6b00622", "linker_1": old}, lookup)
        self.assertEqual(count, 1)
        self.assertTrue(result["linker_1"].startswith("4′,4‴,4⁗′,4⁗‴-"))
        record = {"doi": "10.1002/ejic.201601100", "linker_1": "1,3,5-tris[2,6-dimethyl-4-(?-carboxy)methoxyphenyl]benzene"}
        self.assertEqual(correct_record(record, lookup), (record, 0))

    @unittest.skipUnless(importlib.util.find_spec("pandas"), "Install the curation extra for curation tests.")
    def test_frame_index_and_both_curation_branches(self):
        import pandas as pd
        from mofinder.curation import linkers
        row = {"doi": "10.1021/ic901133k", "linker_1": "2,2?-bipyrimidine",
               "linker_1_amount_text": "0.1 mmol", "linker_1_amount_value": "0.1", "linker_1_amount_unit": "mmol"}
        frame = pd.DataFrame([row], index=[17])
        corrected = correct_frame(frame, LOOKUP)
        self.assertEqual(corrected.index.tolist(), [17])
        self.assertEqual(frame.loc[17, "linker_1"], row["linker_1"])
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.csv", Path(directory) / "output.csv"
            frame.to_csv(source, index=False)
            for mode in ("positive", "negative"):
                with self.subTest(mode=mode), redirect_stdout(StringIO()):
                    result = getattr(linkers, f"clean_{mode}")(
                        source, output, linker_mw_path=ROOT / "data/organic_linker_info/linker_molecular_weights.csv",
                        linker_prime_corrections=LOOKUP,
                    )
                    self.assertEqual(result.linker_1.tolist(), ["2,2′-bipyrimidine"])

    def test_corrected_derivative_and_recorded_provenance(self):
        source = ROOT / "data/processed_data/processed_negative.csv"
        corrected_dir = ROOT / "data/processed_data/linker_corrected"
        manifest = json.loads((corrected_dir / "manifest.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corrected.csv"
            result = correct_csv(source, output, LOOKUP)
            self.assertEqual(result["changed_rows"], 1458)
            self.assertEqual(result["changed_cells"], 1551)
            self.assertEqual(output.read_bytes(), (corrected_dir / "processed_negative.csv").read_bytes())
            self.assertEqual(result["output_sha256"], manifest["output_sha256"])
            self.assertEqual(result["input_sha256"], manifest["input_sha256"])
        with self.assertRaisesRegex(ValueError, "separate"):
            correct_csv(source, source, LOOKUP)


if __name__ == "__main__":
    unittest.main()
