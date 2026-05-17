"""
CSV I/O and path utilities for step_3_mining.

Exports
-------
sanitize_for_path, ensure_dir, to_oneline, read_csv_header, append_rows
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Unicode normalisation regexes (re handles \u/\x escapes in raw strings)
# ---------------------------------------------------------------------------
_HARD_BREAKS = re.compile(r"[\r\n\x85\u2028\u2029]")
_CTRL        = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_ZERO_WIDTH  = re.compile(r"[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def sanitize_for_path(name: str) -> str:
    """Make a filesystem-safe slug for folder and file names."""
    if not name:
        return "unknown"
    s = name.strip()
    s = s.replace("/", "_").replace("\\", "_").replace(":", "_")
    s = re.sub(r"[^A-Za-z0-9._\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_.")
    return s[:160] or "item"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# String sanitisation
# ---------------------------------------------------------------------------

def to_oneline(val) -> str:
    """Normalise a value to a single-line string safe for CSV cells."""
    if val is None:
        return ""
    s = val if isinstance(val, str) else str(val)
    s = unicodedata.normalize("NFC", s)
    # PDF artifact: middle-dot encoded as NUL + b7
    s = s.replace("\x00b7", "\u00B7").replace("\\u0000b7", "\u00B7")
    s = _HARD_BREAKS.sub("\n", s)
    s = _CTRL.sub(" ", s)
    s = _ZERO_WIDTH.sub("", s)
    s = s.replace("\u00A0", " ").replace("\t", " ")
    s = re.sub(r"[ ]{2,}", " ", s)
    s = re.sub(r"\n+", "\n", s).replace("\n", "\\n")
    return s


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def read_csv_header(csv_path: str) -> Optional[List[str]]:
    """Return column names from an existing CSV, or None if absent/empty."""
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return None
    try:
        hdr_df = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=0)
        return list(hdr_df.columns)
    except Exception:
        return None


def append_rows(csv_path: str, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Append rows to a CSV file with strict column-count checks.

    Returns (written_count, skipped_count).
    The first write establishes the header; subsequent writes must match it exactly.
    """
    if not rows:
        return (0, 0)

    existing_header = read_csv_header(csv_path)

    if existing_header is None:
        expected_header = list(rows[0].keys())
        header_needed = True
    else:
        expected_header = existing_header
        header_needed = False

    cleaned: List[Dict[str, Any]] = []
    skipped = 0
    expected_set = set(expected_header)

    for r in rows:
        keys = set(r.keys())
        if keys != expected_set:
            print(
                f"[ROW SKIPPED] DOI {r.get('doi', '?')} invalid column set. "
                f"expected={len(expected_set)} got={len(keys)} "
                f"extra={sorted(keys - expected_set)} missing={sorted(expected_set - keys)}"
            )
            skipped += 1
            continue
        cleaned.append({k: r.get(k, "") for k in expected_header})

    if not cleaned:
        return (0, skipped)

    df = pd.DataFrame(cleaned).fillna("")
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].map(to_oneline)

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        try:
            df.to_csv(
                f, index=False, header=header_needed,
                sep=",", quoting=csv.QUOTE_ALL, doublequote=True,
                line_terminator="\n",
            )
        except Exception:
            df.to_csv(
                f, index=False, header=header_needed,
                sep=",", quoting=csv.QUOTE_ALL, doublequote=True,
                lineterminator="\n",
            )

    return (len(df), skipped)
