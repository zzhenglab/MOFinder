from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from config import COL_AGENT_ANSWER, REQUIRED_INPUT_COLS


def safe_read_excel(path_str: str) -> Optional[pd.DataFrame]:
    """Read an Excel file, backing it up and returning None if it is unreadable."""
    try:
        return pd.read_excel(path_str, engine="openpyxl")
    except Exception:
        try:
            bak = path_str + ".bak"
            if os.path.exists(path_str):
                os.replace(path_str, bak)
                print(f"[WARN] Existing output file unreadable; backed up to: {bak}")
        finally:
            return None


def load_input_df(path: str) -> pd.DataFrame:
    """Load and validate the input Excel, returning only the required columns."""
    df = pd.read_excel(str(path), engine="openpyxl")
    missing = [c for c in REQUIRED_INPUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in input: {missing}")
    return df[REQUIRED_INPUT_COLS].copy()


def load_or_init_output(input_df: pd.DataFrame, out_path: str) -> pd.DataFrame:
    """
    Load existing output file if present (resume mode), or create a fresh one.

    Always syncs column values from input_df so stale cached data is overwritten.
    Handles mismatched row counts by padding or trimming.
    """
    p        = Path(out_path)
    path_str = str(p)
    out_df   = None

    if p.exists() and p.is_file():
        out_df = safe_read_excel(path_str)

    if out_df is None:
        out_df = input_df.copy()
        out_df[COL_AGENT_ANSWER] = None
        out_df.to_excel(path_str, index=False, engine="openpyxl")
        return out_df

    needed = list(input_df.columns) + [COL_AGENT_ANSWER]
    for c in needed:
        if c not in out_df.columns:
            out_df[c] = None
    out_df = out_df[needed]

    if len(out_df) < len(input_df):
        additional = input_df.iloc[len(out_df):].copy()
        additional[COL_AGENT_ANSWER] = None
        out_df = pd.concat([out_df, additional], ignore_index=True)
    elif len(out_df) > len(input_df):
        out_df = out_df.iloc[: len(input_df)].copy()

    for c in input_df.columns:
        out_df[c] = input_df[c].values

    out_df.to_excel(path_str, index=False, engine="openpyxl")
    return out_df


def rows_to_process_indices(out_df: pd.DataFrame) -> list:
    """Return row indices where Agent_YN is blank (not yet classified)."""
    mask = out_df[COL_AGENT_ANSWER].astype(str).str.strip().isin(["", "nan", "None"])
    return list(out_df[mask].index)
