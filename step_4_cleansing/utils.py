"""Shared paths and small helpers for Step 4 cleansing scripts."""
from __future__ import annotations

import math
from pathlib import Path
import sys
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"

POSITIVE_RAW = DATA_DIR / "mof_extraction.csv"
POSITIVE_1 = DATA_DIR / "mof_extraction_1.csv"
POSITIVE_2 = DATA_DIR / "mof_extraction_1_2.csv"
POSITIVE_3 = DATA_DIR / "mof_extraction_1_2_3.csv"
POSITIVE_4 = DATA_DIR / "mof_extraction_1_2_3_4.csv"
POSITIVE_5 = DATA_DIR / "mof_extraction_1_2_3_4_5.csv"
POSITIVE_6 = DATA_DIR / "mof_extraction_1_2_3_4_5_6.csv"

NEGATIVE_RAW = DATA_DIR / "mof_extraction_failures_enum.csv"
NEGATIVE_1 = DATA_DIR / "mof_extraction_failures_enum_1.csv"
NEGATIVE_2 = DATA_DIR / "mof_extraction_failures_enum_1_2.csv"
NEGATIVE_3 = DATA_DIR / "mof_extraction_failures_enum_1_2_3.csv"
NEGATIVE_4 = DATA_DIR / "mof_extraction_failures_enum_1_2_3_4.csv"
NEGATIVE_5 = DATA_DIR / "mof_extraction_failures_enum_1_2_3_4_5.csv"
NEGATIVE_6 = DATA_DIR / "mof_extraction_failures_enum_1_2_3_4_5_6.csv"

FULL_BRANCHES = {"positive", "negative-plans"}
ALL_BRANCHES = {"positive", "negative-plans", "negative-basic"}

def is_filled(x) -> bool:
    if x is None:
        return False
    if isinstance(x, float) and math.isnan(x):
        return False
    s = str(x).strip()
    return s != "" and s.lower() not in {"nan", "none"}

def filled_series(s):
    return s.apply(is_filled)

def count_changes(before, after) -> int:
    return int((before.astype(str) != after.astype(str)).sum())

def print_header(msg: str) -> None:
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)

def safe_lower(x) -> str:
    try:
        return str(x).strip().lower()
    except Exception:
        return ""

def reset_index(df, why: str):
    import pandas as pd

    df = df.reset_index(drop=True)
    assert df.index.equals(pd.RangeIndex(len(df))), f"Index is not contiguous after: {why}"
    return df

def branch_paths(branch: str, data_dir: str | Path | None = None) -> dict[str, Path]:
    base = Path(data_dir) if data_dir is not None else DATA_DIR
    if branch == "positive":
        return {
            "raw": base / "mof_extraction.csv",
            "s1": base / "mof_extraction_1.csv",
            "s2": base / "mof_extraction_1_2.csv",
            "s3": base / "mof_extraction_1_2_3.csv",
            "s4": base / "mof_extraction_1_2_3_4.csv",
            "s5": base / "mof_extraction_1_2_3_4_5.csv",
            "s6": base / "mof_extraction_1_2_3_4_5_6.csv",
        }
    if branch in {"negative-plans", "negative-basic"}:
        return {
            "raw": base / "mof_extraction_failures_enum.csv",
            "s1": base / "mof_extraction_failures_enum_1.csv",
            "s2": base / "mof_extraction_failures_enum_1_2.csv",
            "s3": base / "mof_extraction_failures_enum_1_2_3.csv",
            "s4": base / "mof_extraction_failures_enum_1_2_3_4.csv",
            "s5": base / "mof_extraction_failures_enum_1_2_3_4_5.csv",
            "s6": base / "mof_extraction_failures_enum_1_2_3_4_5_6.csv",
        }
    raise ValueError(f"Unknown branch: {branch}")

def first_existing(paths: Iterable[Path]) -> Path | None:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None

def configure_utf8_stdio() -> None:
    """Keep chemistry symbols printable from Windows terminals."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
