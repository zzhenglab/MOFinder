"""
Step 3.1 — Match main articles with SI files and count words / tokens
======================================================================
What it does
    Reads an Excel workbook containing a DOI column, then scans two local
    folders — one for main-article PDFs and one for supplementary-information
    (SI) files — and marks which files are present.  In a second pass it
    counts words (regex) and OpenAI-compatible tokens (tiktoken) for every
    matched file, then writes histograms.

        Input Excel column  →  matched filename convention
        DOI 10.1002/x       →  main: 10.1002_x.pdf
                            →  SI  : 10.1002_x_SI.{pdf,docx,doc}

Input
    ``<data>/SELECTED 7000 SI - Copy.xlsx``  — workbook with at least a
    ``DOI`` column (default; override with ``--excel``).

    ``<data>/SI downloaded/``   — folder of SI files (``--si-folder``).
    ``<data>/downloaded/``      — folder of main-article PDFs (``--main-folder``).

Output
    Two workbooks written next to the input file:
        ``<stem> - updated.xlsx``  — full workbook with all columns added.
        ``<stem> - simple.xlsx``   — 3-column file: DOI, Main File, SI File.
                                     This is the input expected by Step 3.2.

    The updated workbook also receives word/token counts when the
    ``--no-count`` flag is NOT given.

File layout (numbered sections below)
    1. Script paths / defaults    3. File matching
    2. DOI normalisation          4. Word / token counting
                                  5. CLI

Usage
-----
  python 3_1_match_and_count.py [options]

Examples:
  # Default — uses SELECTED 7000 SI - Copy.xlsx in <repo>/data/
  python 3_1_match_and_count.py

  # Custom Excel, skip counting
  python 3_1_match_and_count.py --excel /path/to/sheet.xlsx --no-count

Requirements
------------
  pip install pandas openpyxl pypdf pdfminer.six tiktoken matplotlib
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ===========================================================================
# 1. Script paths / defaults
# ===========================================================================
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _SCRIPT_DIR.parent
_DATA_DIR   = _REPO_ROOT / "data"

DEFAULT_EXCEL_PATH  = str(_DATA_DIR / "SELECTED 7000 SI - Copy.xlsx")
DEFAULT_SI_FOLDER   = str(_DATA_DIR / "SI downloaded")
DEFAULT_MAIN_FOLDER = str(_DATA_DIR / "downloaded")


# ===========================================================================
# 2. DOI normalisation
# ===========================================================================

def doi_to_base(doi_raw: str) -> str:
    """
    Normalise a DOI string to the base used in download filenames.

    Example: ``10.1002/adma.202210613``  →  ``10.1002_adma.202210613``
    """
    doi = str(doi_raw).strip()
    doi = re.sub(r'^(?:https?://)?(?:dx\.)?doi\.org/', "", doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', "", doi, flags=re.IGNORECASE)
    doi = doi.strip()
    return doi.replace("/", "_")


def is_empty(x) -> bool:
    if pd.isna(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() in {"nan", "none"}


def is_one(x) -> bool:
    try:
        return str(int(float(x))).strip() == "1"
    except Exception:
        return str(x).strip() == "1"


# ===========================================================================
# 3. File matching — mark SI and main article presence, write simple output
# ===========================================================================

def match_files(
    excel_path: Path,
    si_dir: Path,
    main_dir: Path,
) -> pd.DataFrame:
    """
    Update the workbook with SI Downloaded / Downloaded / filename columns.

    Returns the modified DataFrame (also saves two xlsx files next to input).
    """
    # Collect SI files (case-insensitive lookup)
    allowed_exts = {".pdf", ".docx", ".doc"}
    file_lookup: dict[str, str] = {}
    if si_dir.is_dir():
        for p in si_dir.iterdir():
            if p.is_file() and p.suffix.lower() in allowed_exts:
                file_lookup[p.name.lower()] = p.name
    else:
        print(f'Warning: SI folder not found at: {si_dir.resolve()}')

    # Collect main-article PDFs (pdf only)
    main_lookup: dict[str, str] = {}
    if main_dir.is_dir():
        for p in main_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".pdf":
                main_lookup[p.name.lower()] = p.name
    else:
        print(f'Warning: main "downloaded" folder not found at: {main_dir.resolve()}')
        print("Main article matching will be skipped.\n")

    # Load Excel
    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip() for c in df.columns]
    if "DOI" not in df.columns:
        raise KeyError('Column "DOI" not found in the sheet.')

    for col in ["SI Downloaded", "Downloaded", "Found SI Filename",
                "Matched Main Filename", "SI File", "Main File"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)

    updated_si = 0
    updated_main = 0

    for idx in df.index:
        doi_val = df.at[idx, "DOI"]
        if is_empty(doi_val):
            for col in ["SI Downloaded", "Downloaded", "Found SI Filename",
                        "Matched Main Filename", "SI File", "Main File"]:
                df.at[idx, col] = ""
            continue

        base = doi_to_base(doi_val)

        # SI candidates in priority order
        si_matched = None
        for cand in [f"{base}_SI.pdf", f"{base}_SI.docx", f"{base}_SI.doc"]:
            if cand.lower() in file_lookup:
                si_matched = file_lookup[cand.lower()]
                break

        if si_matched:
            df.at[idx, "SI Downloaded"]      = 1
            df.at[idx, "Found SI Filename"]  = si_matched
            df.at[idx, "SI File"]            = str(si_dir / si_matched)
            updated_si += 1
        else:
            df.at[idx, "SI Downloaded"]     = ""
            df.at[idx, "Found SI Filename"] = ""
            df.at[idx, "SI File"]           = ""

        # Main article (PDF only)
        main_matched = None
        if main_dir.is_dir():
            cand = f"{base}.pdf"
            if cand.lower() in main_lookup:
                main_matched = main_lookup[cand.lower()]

        if main_matched:
            df.at[idx, "Downloaded"]           = 1
            df.at[idx, "Matched Main Filename"] = main_matched
            df.at[idx, "Main File"]             = str(main_dir / main_matched)
            updated_main += 1
        else:
            df.at[idx, "Downloaded"]            = ""
            df.at[idx, "Matched Main Filename"] = ""
            df.at[idx, "Main File"]             = ""

    # Save full workbook
    out_path        = excel_path.with_name(f"{excel_path.stem} - updated{excel_path.suffix}")
    simple_out_path = excel_path.with_name(f"{excel_path.stem} - simple{excel_path.suffix}")
    df.to_excel(out_path, index=False)

    # Stats
    si_true   = df["SI Downloaded"].apply(is_one)
    main_true = df["Downloaded"].apply(is_one)
    print("Done.")
    print(f"Workbook saved to: {out_path.name}")
    print(f"Total rows: {len(df)}")
    print(f"SI updated to 1: {updated_si}")
    print(f"Main updated to 1: {updated_main}")
    print("\nSummary:")
    print(f"Both main and SI present: {int((si_true & main_true).sum())}")
    print(f"Only main article present: {int((~si_true & main_true).sum())}")
    print(f"Only SI present: {int((si_true & ~main_true).sum())}")
    print(f"Neither present: {int((~si_true & ~main_true).sum())}")

    # Report unmatched files
    doi_bases = set()
    for v in df["DOI"]:
        if not is_empty(v):
            doi_bases.add(doi_to_base(v))

    si_unmatched = []
    for fname_lower, fname_orig in file_lookup.items():
        stem = Path(fname_lower).stem
        base_candidate = stem[:-3] if stem.lower().endswith("_si") else stem
        if base_candidate not in doi_bases:
            si_unmatched.append(fname_orig)

    main_unmatched = []
    for fname_lower, fname_orig in main_lookup.items():
        stem = Path(fname_lower).stem
        if stem not in doi_bases:
            main_unmatched.append(fname_orig)

    print(f"\nUnmatched SI files: {len(si_unmatched)}")
    for x in si_unmatched:
        print(f"  SI unmatched: {x}")
    print(f"Unmatched main files: {len(main_unmatched)}")
    for x in main_unmatched:
        print(f"  Main unmatched: {x}")

    # Simple 3-column output (DOI, Main File, SI File) — Step 3.2 input
    simple_df = df[["DOI", "Main File", "SI File"]].copy()
    simple_df.to_excel(simple_out_path, index=False)
    print(f"\nSimple file saved to: {simple_out_path.name} (columns: DOI, Main File, SI File)")

    return df


# ===========================================================================
# 4. Word / token counting  (resume-safe: only fills blank cells)
# ===========================================================================

def _try_pdfminer(path: Path) -> str:
    try:
        import pdfminer.high_level as pdfminer_high
        return pdfminer_high.extract_text(str(path)) or ""
    except Exception:
        return ""


def _try_pypdf2(path: Path) -> str:
    try:
        import PyPDF2
        parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    parts.append("")
        return "\n".join(parts)
    except Exception:
        return ""


def _read_pdf_for_count(path: Path) -> str:
    """Try pdfminer first (more accurate), fall back to PyPDF2."""
    text = _try_pdfminer(path)
    if not text:
        text = _try_pypdf2(path)
    return text


_word_re = re.compile(r"\b\w+\b", flags=re.UNICODE)


def _count_words(text: str) -> int:
    return len(_word_re.findall(text)) if text else 0


def _make_encoding():
    try:
        import tiktoken
        try:
            return tiktoken.encoding_for_model("gpt-4o")
        except Exception:
            return tiktoken.get_encoding("cl100k_base")
    except ImportError:
        return None


def _count_tokens(text: str, encoding) -> int:
    if not text or encoding is None:
        return 0
    return len(encoding.encode(text))


def _needs_value(v) -> bool:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return True
    return str(v).strip() in {"", "nan", "none"}


def _safe_path(x) -> Optional[Path]:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    p = Path(s)
    return p if p.is_file() else None


def count_words_and_tokens(xlsx_path: Path) -> None:
    """
    Fill word and token count columns in the updated workbook.

    Skips rows that already have values (resume-safe).
    Plots histograms of the distributions when done.
    """
    import matplotlib.pyplot as plt

    MAIN_FILE_COL = "Main File"
    SI_FILE_COL   = "SI File"
    MAIN_WORDS    = "Main Words"
    SI_WORDS      = "SI Words"
    COMBINED_WORDS  = "Combined Words"
    MAIN_TOKENS   = "Main Tokens"
    SI_TOKENS     = "SI Tokens"
    COMBINED_TOKENS = "Combined Tokens"

    encoding = _make_encoding()
    if encoding is None:
        print("[WARN] tiktoken not installed; token counts will be 0.")

    df2 = pd.read_excel(xlsx_path)
    for col in [MAIN_FILE_COL, SI_FILE_COL]:
        if col not in df2.columns:
            df2[col] = ""
    for col in [MAIN_WORDS, SI_WORDS, COMBINED_WORDS,
                MAIN_TOKENS, SI_TOKENS, COMBINED_TOKENS]:
        if col not in df2.columns:
            df2[col] = np.nan

    # Count pending
    pending = 0
    for _, row in df2.iterrows():
        if _safe_path(row.get(MAIN_FILE_COL, "")) and (
            _needs_value(row.get(MAIN_WORDS)) or _needs_value(row.get(MAIN_TOKENS))
        ):
            pending += 1
        if _safe_path(row.get(SI_FILE_COL, "")) and (
            _needs_value(row.get(SI_WORDS)) or _needs_value(row.get(SI_TOKENS))
        ):
            pending += 1
    print(f"PDFs to process (missing counts): {pending}")

    processed = 0
    t0 = time.time()

    for idx in df2.index:
        row = df2.loc[idx]

        main_path = _safe_path(row.get(MAIN_FILE_COL, ""))
        if main_path and (
            _needs_value(row.get(MAIN_WORDS)) or _needs_value(row.get(MAIN_TOKENS))
        ):
            text = _read_pdf_for_count(main_path)
            if _needs_value(row.get(MAIN_WORDS)):
                df2.at[idx, MAIN_WORDS]  = int(_count_words(text))
            if _needs_value(row.get(MAIN_TOKENS)):
                df2.at[idx, MAIN_TOKENS] = int(_count_tokens(text, encoding))
            processed += 1

        si_path = _safe_path(row.get(SI_FILE_COL, ""))
        if si_path and (
            _needs_value(row.get(SI_WORDS)) or _needs_value(row.get(SI_TOKENS))
        ):
            text = _read_pdf_for_count(si_path)
            if _needs_value(row.get(SI_WORDS)):
                df2.at[idx, SI_WORDS]  = int(_count_words(text))
            if _needs_value(row.get(SI_TOKENS)):
                df2.at[idx, SI_TOKENS] = int(_count_tokens(text, encoding))
            processed += 1

        if processed and processed % 100 == 0:
            print(f"Processed {processed}/{pending} PDFs in {time.time()-t0:.1f}s")

    # Combined = SI if present, else Main
    def _coalesce(pref, alt):
        return pref if not pd.isna(pref) else alt

    df2[COMBINED_WORDS]  = df2[[SI_WORDS, MAIN_WORDS]].apply(
        lambda r: _coalesce(r[SI_WORDS], r[MAIN_WORDS]), axis=1
    )
    df2[COMBINED_TOKENS] = df2[[SI_TOKENS, MAIN_TOKENS]].apply(
        lambda r: _coalesce(r[SI_TOKENS], r[MAIN_TOKENS]), axis=1
    )

    df2.to_excel(xlsx_path, index=False)
    print(f"Counts saved to: {xlsx_path.name}")

    def _finite(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()

    def _avg_and_total(s: pd.Series):
        fs = _finite(s)
        return (float(fs.mean()) if len(fs) else 0.0, int(fs.sum()) if len(fs) else 0)

    for label, col in [
        ("Main words", MAIN_WORDS), ("SI words", SI_WORDS),
        ("Combined words", COMBINED_WORDS),
        ("Main tokens", MAIN_TOKENS), ("SI tokens", SI_TOKENS),
        ("Combined tokens", COMBINED_TOKENS),
    ]:
        plt.figure()
        plt.hist(_finite(df2[col]), bins=50)
        plt.title(f"{label} distribution")
        plt.xlabel(label.split()[-1].capitalize())
        plt.ylabel("Count")
        plt.show()

    mw_avg, mw_sum = _avg_and_total(df2[MAIN_WORDS])
    sw_avg, sw_sum = _avg_and_total(df2[SI_WORDS])
    cw_avg, cw_sum = _avg_and_total(df2[COMBINED_WORDS])
    mt_avg, mt_sum = _avg_and_total(df2[MAIN_TOKENS])
    st_avg, st_sum = _avg_and_total(df2[SI_TOKENS])
    ct_avg, ct_sum = _avg_and_total(df2[COMBINED_TOKENS])

    print("\nWords summary:")
    print(f"Average Main: {mw_avg:.2f}, Total Main: {mw_sum}")
    print(f"Average SI: {sw_avg:.2f}, Total SI: {sw_sum}")
    print(f"Average Combined: {cw_avg:.2f}, Total Combined: {cw_sum}")
    print("\nTokens summary:")
    print(f"Average Main: {mt_avg:.2f}, Total Main: {mt_sum}")
    print(f"Average SI: {st_avg:.2f}, Total SI: {st_sum}")
    print(f"Average Combined: {ct_avg:.2f}, Total Combined: {ct_sum}")
    print(f"\nAll done. Elapsed: {time.time()-t0:.1f}s")


# ===========================================================================
# 5. CLI
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Step 3.1 — Match main+SI files and count words/tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--excel", default=DEFAULT_EXCEL_PATH,
        help=f"Input Excel workbook with DOI column (default: {DEFAULT_EXCEL_PATH})",
    )
    parser.add_argument(
        "--si-folder", default=DEFAULT_SI_FOLDER,
        help=f"Folder containing SI files (default: {DEFAULT_SI_FOLDER})",
    )
    parser.add_argument(
        "--main-folder", default=DEFAULT_MAIN_FOLDER,
        help=f"Folder containing main-article PDFs (default: {DEFAULT_MAIN_FOLDER})",
    )
    parser.add_argument(
        "--no-count", action="store_true",
        help="Skip the word/token counting step (only run file matching)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    excel_path = Path(args.excel)
    si_dir     = Path(args.si_folder)
    main_dir   = Path(args.main_folder)

    if not excel_path.is_file():
        raise FileNotFoundError(f"Excel not found: {excel_path}")

    match_files(excel_path, si_dir, main_dir)

    if not args.no_count:
        updated_xlsx = excel_path.with_name(f"{excel_path.stem} - updated{excel_path.suffix}")
        count_words_and_tokens(updated_xlsx)
