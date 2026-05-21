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
    "metal_concentration",
    "M_L_ratio",
]

MULTI_LINKER_REQUIRED_COLS = [
    "metal_1",
    "solvent_main",
    "metal_concentration",
    "M_L_ratio",
]

EMPTY_TOKENS = {
    "",
    "nan",
    "none",
    "null",
    "na",
    "n/a",
    "not_reported",
    "not reported",
    "not-report",
    "unknown",
}


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
    return series.map(clean_str).notna()


def clean_str(x: Any) -> str | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = (
        s.replace("\u0e01\u0e44", "'")
        .replace("\u0e01\u0e0f", "'")
        .replace("\u0e01\u0e10", '"')
        .replace("\u0e01\u0e11", '"')
        .replace("\u2032", "'")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    s = s.strip('"').strip("'")
    s = re.sub(r"\s+", " ", s).strip()
    if s.lower() in EMPTY_TOKENS:
        return None
    return s if len(s) > 0 else None


def norm_for_key(x: Any) -> str | None:
    s = clean_str(x)
    if s is None:
        return None
    s = s.lower().replace("\u00b7", ".")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


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


def display_value(name: Any, abbr: Any = None, *, include_abbr: bool = False) -> str | None:
    name_clean = clean_str(name)
    abbr_clean = clean_str(abbr)
    if name_clean and abbr_clean and include_abbr and abbr_clean.lower() not in name_clean.lower():
        return f"{name_clean} ({abbr_clean})"
    return name_clean or abbr_clean


def unique_preserve_order(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_str(value)
        if not cleaned:
            continue
        key = norm_for_key(cleaned)
        if key and key not in seen:
            out.append(cleaned)
            seen.add(key)
    return out


def join_with_and(values: Iterable[Any]) -> str | None:
    vals = unique_preserve_order(values)
    return " and ".join(vals) if vals else None


def numbered_stem_indices(row: pd.Series, stem: str) -> list[int]:
    indices: set[int] = set()
    pat = re.compile(rf"^{re.escape(stem)}_(\d+)(?:_|$)")
    for col in row.index:
        m = pat.match(str(col))
        if m:
            indices.add(int(m.group(1)))
    return sorted(indices)


def collect_numbered_reagents(
    row: pd.Series,
    stem: str,
    *,
    max_n: int | None = None,
    include_abbr: bool = False,
) -> list[str]:
    indices = numbered_stem_indices(row, stem)
    if max_n is not None:
        indices = [i for i in indices if i <= max_n]
    if not indices and max_n is not None:
        indices = list(range(1, max_n + 1))
    vals = [
        display_value(row.get(f"{stem}_{i}"), row.get(f"{stem}_{i}_abbr"), include_abbr=include_abbr)
        for i in indices
    ]
    return unique_preserve_order(vals)


def collect_linkers(row: pd.Series) -> list[str]:
    return collect_numbered_reagents(row, "linker", max_n=3)


def collect_modulators(row: pd.Series) -> list[str]:
    return collect_numbered_reagents(row, "modulator", max_n=2)


def collect_solvents(row: pd.Series, *, include_secondary: bool = True) -> list[str]:
    vals = [display_value(row.get("solvent_main"), row.get("solvent_main_abbr"))]
    if include_secondary:
        vals.append(display_value(row.get("solvent_secondary"), row.get("solvent_secondary_abbr")))
    return unique_preserve_order(vals)


def primary_metal_precursor(row: pd.Series) -> str | None:
    return display_value(row.get("metal_1"), row.get("metal_1_abbr"))


def row_to_classifier_conditions(
    row: pd.Series,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
) -> dict[str, Any]:
    if multi_linker:
        organic_linker = join_with_and(collect_linkers(row))
        modulator = join_with_and(collect_modulators(row))
    else:
        organic_linker = clean_str(row.get("linker_1"))
        modulator = clean_str(row.get("modulator_1"))

    if include_secondary_solvent:
        solvent = join_with_and(collect_solvents(row, include_secondary=True))
    else:
        solvent = display_value(row.get("solvent_main"), row.get("solvent_main_abbr"))

    return {
        "metal_precursor": primary_metal_precursor(row),
        "organic_linker": organic_linker,
        "modulator": modulator,
        "solvent": solvent,
        "metal_concentration_mM": to_float(row.get("metal_concentration")),
        "M_L_ratio": parse_ml_ratio(row.get("M_L_ratio")),
        "temperature_C": to_float(row.get("temperature_c")),
        "time_h": to_float(row.get("time_h")),
    }


def cluster_holdout_split(
    df: pd.DataFrame,
    *,
    seed: int,
    holdout_frac: float,
    sort_clusters: bool,
    cap_at_n_clusters: bool,
    holdout_cluster_frac: float | None = None,
    target_mode: str = "random",
    search_trials: int = 800,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    target_mode = (target_mode or "random").lower()
    if target_mode in {"rows", "clusters", "both"}:
        holdout_clusters = _choose_balanced_holdout_clusters(
            df,
            holdout_frac=holdout_frac,
            cluster_frac=holdout_cluster_frac if holdout_cluster_frac is not None else holdout_frac,
            seed=seed,
            mode=target_mode,
            n_trials=search_trials,
        )
        df_seed = df.copy()
        df_seed["is_holdout"] = df_seed["cluster_key"].isin(holdout_clusters)
        train_df = df_seed[~df_seed["is_holdout"]].copy()
        holdout_df = df_seed[df_seed["is_holdout"]].copy()
        return train_df, holdout_df, len(holdout_clusters)

    unique_clusters = np.array(sorted(df["cluster_key"].unique())) if sort_clusters else df["cluster_key"].unique()
    n_clusters = len(unique_clusters)
    if n_clusters == 0:
        df_seed = df.copy()
        df_seed["is_holdout"] = False
        return df_seed.copy(), df_seed.iloc[0:0].copy(), 0

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


def _choose_balanced_holdout_clusters(
    df: pd.DataFrame,
    *,
    holdout_frac: float,
    cluster_frac: float,
    seed: int,
    mode: str = "both",
    n_trials: int = 800,
) -> set[Any]:
    stats = (
        df.groupby("cluster_key")
        .agg(n_rows=("cluster_key", "size"), n_pos=("is_success", "sum"))
        .reset_index()
    )
    stats["n_pos"] = stats["n_pos"].astype(int)
    stats["n_neg"] = stats["n_rows"] - stats["n_pos"]

    if len(stats) < 2:
        raise ValueError("Need at least 2 clusters to create train/holdout split.")

    total_rows = len(df)
    total_pos = int(df["is_success"].sum())
    total_neg = int((~df["is_success"]).sum())
    total_clusters = len(stats)

    target_rows = max(1, int(round(total_rows * holdout_frac)))
    target_pos = max(1, int(round(total_pos * holdout_frac)))
    target_neg = max(1, int(round(total_neg * holdout_frac)))
    target_clusters = max(1, int(round(total_clusters * cluster_frac)))

    rng = np.random.default_rng(seed)

    def score(sel_idx: set[int]) -> tuple[float, int, int, int, int]:
        sub = stats.iloc[list(sel_idx)] if sel_idx else stats.iloc[[]]
        n_rows = int(sub["n_rows"].sum())
        n_pos = int(sub["n_pos"].sum())
        n_neg = int(sub["n_neg"].sum())
        n_clusters = len(sel_idx)

        def rel(v: int, t: int) -> float:
            return abs(v - t) / max(1, t)

        cost = 0.0
        if mode in {"rows", "both"}:
            cost += 1.00 * rel(n_rows, target_rows)
        if mode in {"clusters", "both"}:
            cost += 0.65 * rel(n_clusters, target_clusters)
        cost += 0.85 * rel(n_pos, target_pos)
        cost += 0.85 * rel(n_neg, target_neg)
        if n_pos == 0 or n_neg == 0:
            cost += 10.0
        return cost, n_rows, n_pos, n_neg, n_clusters

    best_sel: set[int] | None = None
    best_score = None
    n = len(stats)

    for _trial in range(max(1, int(n_trials))):
        if mode == "clusters":
            desired_k = target_clusters
        elif mode == "rows":
            desired_k = None
        else:
            jitter = rng.integers(-max(1, target_clusters // 20), max(2, target_clusters // 20 + 1))
            desired_k = int(np.clip(target_clusters + jitter, 1, n - 1))

        order = rng.permutation(n)
        sel: list[int] = []
        cur_rows = 0

        if desired_k is not None:
            weights = 1.0 / np.sqrt(stats["n_rows"].to_numpy(dtype=float))
            weights = weights / weights.sum()
            sel = rng.choice(np.arange(n), size=desired_k, replace=False, p=weights).tolist()
        else:
            for idx in order:
                row = stats.iloc[int(idx)]
                if cur_rows >= target_rows:
                    break
                sel.append(int(idx))
                cur_rows += int(row["n_rows"])

        sel_set = set(sel)
        not_sel = set(range(n)) - sel_set
        cur_score = score(sel_set)[0]
        for _ in range(300):
            if not sel_set or not not_sel:
                break
            remove_idx = int(rng.choice(list(sel_set)))
            add_idx = int(rng.choice(list(not_sel)))
            trial_set = set(sel_set)
            trial_set.remove(remove_idx)
            trial_set.add(add_idx)
            trial_score = score(trial_set)[0]
            if trial_score < cur_score or rng.random() < 0.003:
                sel_set = trial_set
                not_sel = set(range(n)) - sel_set
                cur_score = trial_score

        candidate_score = score(sel_set)
        if best_score is None or candidate_score[0] < best_score[0]:
            best_score = candidate_score
            best_sel = sel_set

    if best_sel is None:
        return set()
    return set(stats.iloc[list(best_sel)]["cluster_key"].tolist())


def interleave_by_ratio(
    df: pd.DataFrame,
    *,
    n_pos: int = 11,
    n_neg: int = 17,
    rng_seed: int = 42,
) -> pd.DataFrame:
    if n_pos <= 0 or n_neg <= 0:
        raise ValueError(
            f"Interleave block sizes must be positive; got n_pos={n_pos}, n_neg={n_neg}."
        )

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
