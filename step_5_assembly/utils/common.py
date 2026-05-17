"""Small shared helpers for Step 5 PN classifier dataset assembly.

Keep this module limited to values/functions used by multiple numbered
scripts. Step-specific logic lives in the corresponding ``5_x*.py`` file.
"""
from __future__ import annotations

import re
import sys
from math import ceil
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"

POSITIVE_CSV = DATA_DIR / "mof_extraction_1_2_3_4_5_6.csv"
NEGATIVE_CSV = DATA_DIR / "mof_extraction_failures_enum_1_2_3_4_5_6.csv"
FULL_METADATA_XLSX = DATA_DIR / "Full.xlsx"

LINKER_COLS = ["linker_1", "linker_2", "linker_3"]

SINGLE_LINKER_REQUIRED_COLS = [
    "metal_1",
    "linker_1",
    "solvent_main",
    "metel_concnertation",
    "M_L_ratio",
]

MULTI_LINKER_REQUIRED_COLS = [
    "metal_1",
    "solvent_main",
    "metel_concnertation",
    "M_L_ratio",
]


def configure_utf8_stdio() -> None:
    """Keep chemistry symbols printable from Windows terminals."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser()


def missing_paths(paths: Iterable[Path]) -> list[Path]:
    return [Path(p) for p in paths if not Path(p).exists()]


def non_empty(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def clean_str(x: Any) -> str | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = s.replace("กไ", "'").replace("กฏ", "'").replace("กฐ", '"').replace("กฑ", '"')
    s = s.strip('"').strip("'")
    s = re.sub(r"\s+", " ", s)
    return s if len(s) > 0 else None


def to_float(x: Any) -> float | None:
    if pd.isna(x):
        return None
    m = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(x))
    if not m:
        return None
    try:
        return float(m[0])
    except Exception:
        return None


def parse_ml_ratio(val: Any) -> float | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    try:
        return float(s)
    except Exception:
        pass

    parts = re.split(r"[:/]", s)
    nums: list[float] = []
    for part in parts:
        try:
            nums.append(float(part))
        except Exception:
            n = to_float(part)
            if n is None:
                return None
            nums.append(n)
    if len(nums) == 1:
        return nums[0]
    if len(nums) >= 2:
        linkers = sum(nums[1:])
        if linkers == 0:
            return None
        return nums[0] / linkers
    return None


def cluster_holdout_split(
    df: pd.DataFrame,
    *,
    seed: int,
    holdout_frac: float,
    sort_clusters: bool,
    cap_at_n_clusters: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    if sort_clusters:
        unique_clusters = np.array(sorted(df["cluster_key"].unique()))
    else:
        unique_clusters = df["cluster_key"].unique()
    n_clusters = len(unique_clusters)
    n_holdout_clusters = max(1, ceil(holdout_frac * n_clusters))
    if cap_at_n_clusters:
        n_holdout_clusters = min(n_holdout_clusters, n_clusters)

    rng = np.random.default_rng(seed)
    holdout_clusters = set(rng.choice(unique_clusters, size=n_holdout_clusters, replace=False))
    df_seed = df.copy()
    df_seed["is_holdout"] = df_seed["cluster_key"].isin(holdout_clusters)
    train_df = df_seed[~df_seed["is_holdout"]].copy()
    holdout_df = df_seed[df_seed["is_holdout"]].copy()
    return train_df, holdout_df, n_holdout_clusters


def interleave_by_ratio(
    df: pd.DataFrame,
    *,
    n_pos: int = 11,
    n_neg: int = 17,
    rng_seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    pos_idx = df[df["is_success"]].index.to_numpy()
    neg_idx = df[~df["is_success"]].index.to_numpy()
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)

    out_indices: list[Any] = []
    i = j = 0
    while i < len(pos_idx) and j < len(neg_idx):
        out_indices.extend(pos_idx[i:i + n_pos])
        i += n_pos
        out_indices.extend(neg_idx[j:j + n_neg])
        j += n_neg

    out_indices.extend(pos_idx[i:])
    out_indices.extend(neg_idx[j:])
    return df.loc[out_indices].reset_index(drop=True)


def count_labels(df: pd.DataFrame) -> tuple[int, int]:
    p = int(df["is_success"].sum())
    n = int((~df["is_success"]).sum())
    return p, n
