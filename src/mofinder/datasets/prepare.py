"""Prepare condition classification JSONL and cluster-disjoint holdout datasets."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from mofinder.display import display_path, display_paths

LABEL_POS = "P"
LABEL_NEG = "N"

# --------------------------
# Helpers: cleaning/parsing
# --------------------------
EMPTY_TOKENS = {
    "", "nan", "none", "null", "na", "n/a", "not_reported",
    "not reported", "not-report", "unknown"
}

ELEMENT_NAMES = {
    "lithium": "Li", "sodium": "Na", "potassium": "K", "rubidium": "Rb", "cesium": "Cs",
    "magnesium": "Mg", "calcium": "Ca", "strontium": "Sr", "barium": "Ba",
    "scandium": "Sc", "yttrium": "Y", "lanthanum": "La", "cerium": "Ce",
    "praseodymium": "Pr", "neodymium": "Nd", "samarium": "Sm", "europium": "Eu",
    "gadolinium": "Gd", "terbium": "Tb", "dysprosium": "Dy", "holmium": "Ho",
    "erbium": "Er", "thulium": "Tm", "ytterbium": "Yb", "lutetium": "Lu",
    "titanium": "Ti", "zirconium": "Zr", "hafnium": "Hf", "vanadium": "V",
    "niobium": "Nb", "tantalum": "Ta", "chromium": "Cr", "molybdenum": "Mo",
    "tungsten": "W", "manganese": "Mn", "iron": "Fe", "cobalt": "Co", "nickel": "Ni",
    "copper": "Cu", "zinc": "Zn", "cadmium": "Cd", "mercury": "Hg", "aluminum": "Al",
    "gallium": "Ga", "indium": "In", "tin": "Sn", "lead": "Pb", "bismuth": "Bi",
    "silver": "Ag", "gold": "Au", "palladium": "Pd", "platinum": "Pt", "ruthenium": "Ru",
    "rhodium": "Rh", "iridium": "Ir", "osmium": "Os"
}

def clean_str(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = (
        s.replace("′", "'")
         .replace("’", "'")
         .replace("‘", "'")
         .replace("“", '"')
         .replace("”", '"')
         .replace("–", "-")
         .replace("—", "-")
    )
    s = s.strip('"').strip("'")
    s = re.sub(r"\s+", " ", s).strip()
    if s.lower() in EMPTY_TOKENS:
        return None
    return s

def norm_for_key(x):
    s = clean_str(x)
    if s is None:
        return None
    s = s.lower()
    s = s.replace("·", ".")
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    return s if s else None

def to_float(x):
    if pd.isna(x):
        return None
    s = str(x)
    m = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not m:
        return None
    try:
        return float(m[0])
    except Exception:
        return None

def parse_ml_ratio(val):
    """
    Parse M_L_ratio into one float.
      - Numeric like 1.5 -> 1.5
      - Ratio like '1:2' -> 1 / 2
      - Ratio like '1:1:1' -> 1 / (1 + 1)
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    if clean_str(s) is None:
        return None
    try:
        return float(s)
    except Exception:
        pass

    parts = re.split(r"[:/]", s)
    nums = []
    for p in parts:
        n = to_float(p)
        if n is None:
            return None
        nums.append(n)

    if len(nums) == 1:
        return nums[0]
    metal = nums[0]
    linker_sum = sum(nums[1:])
    if linker_sum == 0:
        return None
    return metal / linker_sum

def parse_year(x):
    y = to_float(x)
    if y is None:
        return None
    y = int(round(y))
    if 1800 <= y <= 2100:
        return y
    return None

def normalize_doi(x):
    s = clean_str(x)
    if s is None:
        return None
    s = s.lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    # Accept canonical DOIs and PDF filenames under any parent directory.
    # Example: ...\10.1021_jacs.7b09983_SI.pdf -> 10.1021/jacs.7b09983
    if s.endswith(".pdf"):
        s = re.split(r"[\\/]", s)[-1]
    match = re.search(r"10\.\d{4,9}[/_][^\s\\]+", s)
    if not match:
        return None
    s = re.sub(r"(?:_si)?\.pdf$", "", match.group(0))
    s = re.sub(r"^(10\.\d{4,9})_", r"\1/", s)
    return s or None

def display_value(name, abbr=None, include_abbr=False):
    """
    Use full chemical name/formula if available; fall back to abbreviation.
    If include_abbr=True, output 'name (abbr)' when both are available.
    """
    name = clean_str(name)
    abbr = clean_str(abbr)
    if name and abbr and include_abbr and abbr.lower() not in name.lower():
        return f"{name} ({abbr})"
    return name or abbr

def unique_preserve_order(values):
    out = []
    seen = set()
    for v in values:
        v = clean_str(v)
        if not v:
            continue
        k = norm_for_key(v)
        if k not in seen:
            out.append(v)
            seen.add(k)
    return out

def join_with_and(values):
    vals = unique_preserve_order(values)
    if not vals:
        return None
    return " and ".join(vals)

def collect_numbered_reagents(row, stem, max_n=3, include_abbr=False):
    vals = []
    for i in range(1, max_n + 1):
        vals.append(display_value(
            row.get(f"{stem}_{i}"),
            row.get(f"{stem}_{i}_abbr"),
            include_abbr=include_abbr
        ))
    return unique_preserve_order(vals)

def collect_linkers(row):
    return collect_numbered_reagents(row, "linker", max_n=3)

def collect_modulators(row):
    return collect_numbered_reagents(row, "modulator", max_n=2)

def collect_solvents(row):
    vals = [
        display_value(row.get("solvent_main"), row.get("solvent_main_abbr")),
        display_value(row.get("solvent_secondary"), row.get("solvent_secondary_abbr")),
    ]
    return unique_preserve_order(vals)

def canonical_set_key(values):
    vals = [norm_for_key(v) for v in values]
    vals = sorted({v for v in vals if v})
    return " + ".join(vals) if vals else "unknown"

def primary_metal_precursor(row):
    return display_value(row.get("metal_1"), row.get("metal_1_abbr"))

def extract_primary_metal_element(row):
    """
    Extract the metal element from metal_1_abbr or metal_1 when recognizable.
    Used when cluster_metal_mode is 'element'.
    """
    abbr = clean_str(row.get("metal_1_abbr"))
    if abbr:
        m = re.search(r"\b([A-Z][a-z]?)\b", abbr)
        if m:
            return m.group(1)

    text = clean_str(row.get("metal_1"))
    if not text:
        return "Me_unknown"

    low = text.lower()
    for name, sym in ELEMENT_NAMES.items():
        if re.search(rf"\b{name}\b", low):
            return sym

    text2 = re.sub(r"^[^A-Za-z]+", "", text)
    m = re.match(r"([A-Z][a-z]?)", text2)
    if m:
        return m.group(1)

    m = re.search(r"\b([A-Z][a-z]?)\b", text)
    if m:
        return m.group(1)

    return "Me_unknown"

def build_cluster_key(row, cluster_metal_mode="precursor", include_modulator_in_cluster=False):
    """
    Main holdout grouping.
    Default grouping: primary metal precursor + all linkers + all solvents.
    Precursor grouping distinguishes salts such as CdCl2 and Cd(NO3)2 even
    when their linker and solvent sets match. Element grouping merges them.
    """
    if cluster_metal_mode == "element":
        metal_key = norm_for_key(extract_primary_metal_element(row))
    elif cluster_metal_mode == "precursor":
        metal_key = norm_for_key(primary_metal_precursor(row))
    else:
        raise ValueError("CLUSTER_METAL_MODE must be 'precursor' or 'element'.")

    parts = [
        f"metal={metal_key or 'unknown'}",
        f"linker={canonical_set_key(collect_linkers(row))}",
        f"solvent={canonical_set_key(collect_solvents(row))}",
    ]

    if include_modulator_in_cluster:
        parts.append(f"modulator={canonical_set_key(collect_modulators(row))}")

    return "|".join(parts)

def row_to_conditions(row):
    return {
        "metal_precursor": primary_metal_precursor(row),
        "organic_linker": join_with_and(collect_linkers(row)),
        "modulator": join_with_and(collect_modulators(row)),
        "solvent": join_with_and(collect_solvents(row)),
        "metal_concentration_mM": to_float(row.get("metel_concnertation")),
        "M_L_ratio": parse_ml_ratio(row.get("M_L_ratio")),
        "temperature_C": to_float(row.get("temperature_c")),
        "time_h": to_float(row.get("time_h")),
    }

def canonical_condition_key(row):
    cond = row_to_conditions(row)
    key = {}
    for k, v in cond.items():
        if isinstance(v, (float, int, np.floating, np.integer)):
            key[k] = None if pd.isna(v) else round(float(v), 8)
        elif v is None:
            key[k] = None
        else:
            key[k] = norm_for_key(v)
    return json.dumps(key, sort_keys=True, ensure_ascii=False)

def forced_question_condition_key(conditions):
    # Apply canonical_condition_key normalization to benchmark conditions.
    key = {}
    for k, v in conditions.items():
        if isinstance(v, (float, int, np.floating, np.integer)):
            key[k] = None if pd.isna(v) else round(float(v), 8)
        elif v is None:
            key[k] = None
        else:
            key[k] = norm_for_key(v)
    return json.dumps(key, sort_keys=True, ensure_ascii=False)

def to_messages_record(row, system_prompt):
    label = LABEL_POS if bool(row["is_success"]) else LABEL_NEG
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(row_to_conditions(row), ensure_ascii=False)},
            {"role": "assistant", "content": label},
        ]
    }

def count_labels(df):
    p = int(df["is_success"].sum())
    n = int((~df["is_success"]).sum())
    return {LABEL_POS: p, LABEL_NEG: n}

def write_jsonl(df, path, seed=None, *, system_prompt, shuffle_output=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df
    if shuffle_output and len(out) > 1:
        out = out.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for _, row in out.iterrows():
            f.write(json.dumps(to_messages_record(row, system_prompt), ensure_ascii=False) + "\n")

# --------------------------
# Metadata
# --------------------------
def load_publication_years(path):
    meta = (pd.read_csv(path, low_memory=False) if Path(path).suffix.lower() == ".csv"
            else pd.read_excel(path))
    if "DOI" not in meta.columns or "Publication Year" not in meta.columns:
        raise ValueError("Publication metadata must contain columns 'DOI' and 'Publication Year'.")

    meta = meta.copy()
    meta["doi_norm"] = meta["DOI"].map(normalize_doi)
    meta["publication_year"] = meta["Publication Year"].map(parse_year)
    meta = meta[meta["doi_norm"].notna() & meta["publication_year"].notna()].copy()

    def choose_year(s):
        vals = [int(x) for x in s.dropna().tolist()]
        if not vals:
            return np.nan
        mode = pd.Series(vals).mode()
        return int(mode.iloc[0])

    return (
        meta.groupby("doi_norm", as_index=False)["publication_year"]
            .agg(choose_year)
    )

# --------------------------
# Holdout cluster choice
# --------------------------
def pn_ratio_from_counts(pos: int, neg: int) -> float:
    return float(pos) / float(neg) if neg else math.inf


def rel_ratio_difference(value: float, reference: float) -> float:
    if not np.isfinite(value) or not np.isfinite(reference) or reference == 0:
        return math.inf
    return abs(value / reference - 1.0)


def cluster_cost(
    hold_rows: int,
    hold_pos: int,
    hold_neg: int,
    hold_clusters: int,
    total_rows: int,
    total_pos: int,
    total_neg: int,
    total_clusters: int,
    target_rows: int,
    target_clusters: int,
    pn_mode: str,
    raw_pn_ratio: float,
    raw_pn_relative_tolerance: float = 0.10,
) -> float:
    def rel(value: int, target: int) -> float:
        return abs(value - target) / max(1, target)

    train_pos = total_pos - hold_pos
    train_neg = total_neg - hold_neg
    if min(hold_pos, hold_neg, train_pos, train_neg) <= 0:
        return 1e9

    hold_ratio = pn_ratio_from_counts(hold_pos, hold_neg)
    train_ratio = pn_ratio_from_counts(train_pos, train_neg)
    row_weight = 4.0 if pn_mode == "equal" else 1.0
    cost = row_weight * rel(hold_rows, target_rows)
    cost += 0.65 * rel(hold_clusters, target_clusters)

    if pn_mode == "equal":
        cost += 0.5 * abs(math.log(hold_ratio / train_ratio))
    elif pn_mode == "raw10":
        hold_diff = rel_ratio_difference(hold_ratio, raw_pn_ratio)
        train_diff = rel_ratio_difference(train_ratio, raw_pn_ratio)
        cost += 40.0 * max(0.0, hold_diff - raw_pn_relative_tolerance) ** 2
        cost += 40.0 * max(0.0, train_diff - raw_pn_relative_tolerance) ** 2
        cost += 0.25 * (hold_diff + train_diff)
    else:
        raise ValueError(f"Unknown P:N mode: {pn_mode}")
    return cost


def choose_holdout_clusters(
    df: pd.DataFrame,
    holdout_frac: float,
    pn_mode: str,
    raw_pn_ratio: float,
    *,
    settings=None,
) -> set[str]:
    settings = settings or {}
    HOLDOUT_CLUSTER_FRAC = settings.get("holdout_cluster_frac", 0.10)
    RNG_SEED = settings.get("rng_seed", 42)
    HOLDOUT_SEARCH_TRIALS = settings.get("holdout_search_trials", 64)
    HOLDOUT_SEARCH_SWAPS = settings.get("holdout_search_swaps", 1200)
    tolerance = settings.get("raw_pn_relative_tolerance", 0.10)
    stats = (
        df.groupby("cluster_key", sort=True)
        .agg(
            n_rows=("cluster_key", "size"),
            n_pos=("is_success", "sum"),
            is_forced=("is_forced_cluster", "max"),
        )
        .reset_index()
    )
    stats["n_pos"] = stats["n_pos"].astype(int)
    stats["n_neg"] = stats["n_rows"] - stats["n_pos"]

    rows = stats["n_rows"].to_numpy(dtype=np.int64)
    pos = stats["n_pos"].to_numpy(dtype=np.int64)
    neg = stats["n_neg"].to_numpy(dtype=np.int64)
    forced = stats["is_forced"].to_numpy(dtype=bool)
    optional_idx = np.flatnonzero(~forced)

    total_rows = int(rows.sum())
    total_pos = int(pos.sum())
    total_neg = int(neg.sum())
    total_clusters = int(len(stats))
    target_rows = max(1, int(round(total_rows * holdout_frac)))
    target_clusters = max(int(forced.sum()), int(round(total_clusters * HOLDOUT_CLUSTER_FRAC)))
    optional_k = target_clusters - int(forced.sum())
    if optional_k < 0 or optional_k >= len(optional_idx):
        raise ValueError("Forced clusters leave no valid train/holdout cluster split.")

    forced_rows = int(rows[forced].sum())
    forced_pos = int(pos[forced].sum())
    forced_neg = int(neg[forced].sum())
    weights = 1.0 / np.sqrt(rows[optional_idx].astype(float))
    weights /= weights.sum()
    rng = np.random.default_rng(RNG_SEED)

    best_selected = None
    best_cost = math.inf
    for _ in range(HOLDOUT_SEARCH_TRIALS):
        chosen = rng.choice(optional_idx, size=optional_k, replace=False, p=weights)
        selected = np.zeros(total_clusters, dtype=bool)
        selected[forced] = True
        selected[chosen] = True
        selected_optional = chosen.copy()
        unselected_optional = np.setdiff1d(optional_idx, chosen, assume_unique=False)

        hold_rows = forced_rows + int(rows[chosen].sum())
        hold_pos = forced_pos + int(pos[chosen].sum())
        hold_neg = forced_neg + int(neg[chosen].sum())
        current_cost = cluster_cost(
            hold_rows, hold_pos, hold_neg, target_clusters,
            total_rows, total_pos, total_neg, total_clusters,
            target_rows, target_clusters, pn_mode, raw_pn_ratio, tolerance,
        )

        # With no optional holdout clusters, the forced set is the only candidate.
        if not len(selected_optional):
            best_selected = selected.copy()
            best_cost = current_cost
            break

        for _ in range(HOLDOUT_SEARCH_SWAPS):
            selected_pos = int(rng.integers(len(selected_optional)))
            unselected_pos = int(rng.integers(len(unselected_optional)))
            remove_idx = int(selected_optional[selected_pos])
            add_idx = int(unselected_optional[unselected_pos])
            trial_rows = hold_rows - int(rows[remove_idx]) + int(rows[add_idx])
            trial_pos = hold_pos - int(pos[remove_idx]) + int(pos[add_idx])
            trial_neg = hold_neg - int(neg[remove_idx]) + int(neg[add_idx])
            trial_cost = cluster_cost(
                trial_rows, trial_pos, trial_neg, target_clusters,
                total_rows, total_pos, total_neg, total_clusters,
                target_rows, target_clusters, pn_mode, raw_pn_ratio, tolerance,
            )
            if trial_cost < current_cost or rng.random() < 0.002:
                selected[remove_idx] = False
                selected[add_idx] = True
                selected_optional[selected_pos] = add_idx
                unselected_optional[unselected_pos] = remove_idx
                hold_rows, hold_pos, hold_neg = trial_rows, trial_pos, trial_neg
                current_cost = trial_cost

            if current_cost < best_cost:
                best_cost = current_cost
                best_selected = selected.copy()

    if best_selected is None or best_cost >= 1e9:
        raise ValueError("No split contains both labels in both partitions; adjust the holdout fraction or input data.")
    return set(stats.loc[best_selected, "cluster_key"])


def choose_common_exact_ratio(
    train_counts: dict[str, int],
    holdout_counts: dict[str, int],
    protected_holdout_counts: dict[str, int],
    raw_pn_ratio: float,
    max_component: int = 200,
) -> tuple[int, int, dict[str, int]]:
    best = None
    for p_unit in range(1, max_component + 1):
        for n_unit in range(1, max_component + 1):
            if math.gcd(p_unit, n_unit) != 1:
                continue
            train_multiple = min(
                train_counts[LABEL_POS] // p_unit,
                train_counts[LABEL_NEG] // n_unit,
            )
            holdout_multiple = min(
                holdout_counts[LABEL_POS] // p_unit,
                holdout_counts[LABEL_NEG] // n_unit,
            )
            if min(train_multiple, holdout_multiple) <= 0:
                continue
            keep = {
                "train_p": p_unit * train_multiple,
                "train_n": n_unit * train_multiple,
                "holdout_p": p_unit * holdout_multiple,
                "holdout_n": n_unit * holdout_multiple,
            }
            if keep["holdout_p"] < protected_holdout_counts[LABEL_POS]:
                continue
            if keep["holdout_n"] < protected_holdout_counts[LABEL_NEG]:
                continue
            retained = sum(keep.values())
            ratio_distance = abs(math.log((p_unit / n_unit) / raw_pn_ratio))
            candidate = (retained, -ratio_distance, -(p_unit + n_unit), p_unit, n_unit, keep)
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    if best is None:
        raise RuntimeError("Could not find a common exact P:N ratio.")
    return int(best[3]), int(best[4]), best[5]


def sample_to_label_counts(
    df: pd.DataFrame,
    keep_pos: int,
    keep_neg: int,
    seed: int,
    protect_representatives: bool,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    kept_parts = []
    for is_success, keep_n in [(True, keep_pos), (False, keep_neg)]:
        label_df = df[df["is_success"].eq(is_success)]
        if protect_representatives:
            protected = label_df[label_df["is_forced_representative"]]
            candidates = label_df[~label_df["is_forced_representative"]]
        else:
            protected = label_df.iloc[0:0]
            candidates = label_df
        needed = keep_n - len(protected)
        if needed < 0 or needed > len(candidates):
            raise ValueError("Requested balance would remove a forced benchmark condition.")
        if needed == len(candidates):
            sampled = candidates
        elif needed == 0:
            sampled = candidates.iloc[0:0]
        else:
            positions = np.sort(rng.choice(len(candidates), size=needed, replace=False))
            sampled = candidates.iloc[positions]
        kept_parts.extend([protected, sampled])
    return pd.concat(kept_parts).sort_values("source_row_id").copy()


def enforce_equal_pn_ratio(
    train_df: pd.DataFrame,
    holdout_df: pd.DataFrame,
    raw_pn_ratio: float,
    rng_seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    train_counts = count_labels(train_df)
    holdout_counts = count_labels(holdout_df)
    protected_counts = count_labels(
        holdout_df[holdout_df["is_forced_representative"]]
    )
    p_unit, n_unit, keep = choose_common_exact_ratio(
        train_counts, holdout_counts, protected_counts, raw_pn_ratio
    )
    balanced_train = sample_to_label_counts(
        train_df, keep["train_p"], keep["train_n"], rng_seed + 301, False
    )
    balanced_holdout = sample_to_label_counts(
        holdout_df,
        keep["holdout_p"],
        keep["holdout_n"],
        rng_seed + 302,
        True,
    )
    return balanced_train, balanced_holdout, {
        "exact_ratio_units": {LABEL_POS: p_unit, LABEL_NEG: n_unit},
        "rows_removed_from_train_for_exact_ratio": int(len(train_df) - len(balanced_train)),
        "rows_removed_from_holdout_for_exact_ratio": int(
            len(holdout_df) - len(balanced_holdout)
        ),
    }

# --------------------------
# Year bins inside train
# --------------------------
def make_contiguous_year_bins(train_df, n_bins):
    ydf = train_df[train_df["publication_year"].notna()].copy()
    if ydf.empty:
        return []

    ydf["publication_year"] = ydf["publication_year"].astype(int)
    counts = ydf.groupby("publication_year").size().sort_index()

    years = list(counts.index)
    n_bins = min(n_bins, len(years))
    if n_bins <= 0:
        return []

    total = int(counts.sum())
    cum = counts.cumsum().to_numpy()

    cut_positions = []
    last_cut = -1
    for i in range(1, n_bins):
        target = total * i / n_bins
        min_idx = last_cut + 1
        max_idx = len(years) - (n_bins - i) - 1  # leave at least one year per remaining bin
        idxs = np.arange(min_idx, max_idx + 1)
        chosen = int(idxs[np.argmin(np.abs(cum[idxs] - target))])
        cut_positions.append(chosen)
        last_cut = chosen

    cut_positions.append(len(years) - 1)

    bins = []
    start_idx = 0
    for bin_i, cut_idx in enumerate(cut_positions, start=1):
        start_year = int(years[start_idx])
        end_year = int(years[cut_idx])
        bdf = ydf[
            (ydf["publication_year"] >= start_year)
            & (ydf["publication_year"] <= end_year)
        ].copy()
        bins.append({
            "bin": bin_i,
            "start_year": start_year,
            "end_year": end_year,
            "df": bdf,
        })
        start_idx = cut_idx + 1

    return bins

def year_range_name(start_year, end_year):
    return f"{start_year}" if start_year == end_year else f"{start_year}to{end_year}"


def load_settings(config_file):
    """Resolve dataset inputs relative to project_root in a JSON configuration."""
    config_file = Path(config_file).expanduser().resolve()
    settings = json.loads(config_file.read_text(encoding="utf-8"))
    root = (config_file.parent / settings.get("project_root", "..")).resolve()
    for key in ("positive_csv", "negative_csv", "metadata_file", "output_dir", "prompt_file", "forced_questions_file"):
        if not settings.get(key):
            raise ValueError(f"Missing configuration field: {key}")
        settings[key] = (root / Path(settings[key]).expanduser()).resolve()
    settings["config_file"] = config_file
    settings["project_root"] = root
    for key in ("holdout_frac", "holdout_cluster_frac"):
        value = settings.get(key)
        if type(value) not in (int, float) or not 0 < value < 1:
            raise ValueError(f"{key} must be between zero and one.")
    for key in ("holdout_search_trials", "holdout_search_swaps", "year_bins", "year_bins_5"):
        if type(settings.get(key)) is not int or settings[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    if type(settings.get("rng_seed")) is not int or settings["rng_seed"] < 0:
        raise ValueError("rng_seed must be a nonnegative integer.")
    if settings.get("pn_mode") not in {"equal", "raw10"}:
        raise ValueError("pn_mode must be equal or raw10.")
    if settings.get("cluster_metal_mode") not in {"precursor", "element"}:
        raise ValueError("cluster_metal_mode must be precursor or element.")
    tolerance = settings.get("raw_pn_relative_tolerance")
    if type(tolerance) not in (int, float) or not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("raw_pn_relative_tolerance must be nonnegative and finite.")
    for key in ("include_modulator_in_cluster", "drop_input_label_conflicts", "dedup_exact_input_within_label", "shuffle_output"):
        if type(settings.get(key)) is not bool:
            raise ValueError(f"{key} must be true or false.")
    return settings


def validate_inputs(settings):
    """Check inputs and report provenance without preparing or writing datasets."""
    errors = []
    rows = {}
    for key in ("positive_csv", "negative_csv", "metadata_file", "prompt_file", "forced_questions_file"):
        path = Path(settings[key])
        if not path.is_file():
            errors.append(f"Missing {key}: {path}")
    for key in ("positive_csv", "negative_csv"):
        if Path(settings[key]).is_file():
            frame = pd.read_csv(settings[key], low_memory=False)
            rows[key] = len(frame)
            missing = {"M_L_ratio", "metel_concnertation", "temperature_c"} - set(frame.columns)
            if missing:
                errors.append(f"{key} lacks required columns: {', '.join(sorted(missing))}")
    if Path(settings["metadata_file"]).is_file():
        try:
            rows["metadata_dois"] = len(load_publication_years(settings["metadata_file"]))
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    if Path(settings["forced_questions_file"]).is_file():
        questions = json.loads(Path(settings["forced_questions_file"]).read_text(encoding="utf-8"))
        required = {"metal_precursor", "organic_linker", "modulator", "solvent", "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h"}
        if not isinstance(questions, list) or any(not isinstance(q, dict) or not {"question", "label", "conditions"} <= set(q) or not isinstance(q["conditions"], dict) or set(q["conditions"]) != required for q in questions):
            errors.append("Forced questions must contain question, label, and all eight condition fields.")
        elif len({q["question"] for q in questions}) != len(questions):
            errors.append("Forced question identifiers must be unique.")
    return {"valid": not errors, "errors": errors, "rows": rows,
            "input_provenance": settings.get("input_provenance", {})}


def input_provenance(settings):
    """Record exact source files, parameters, and prompt used by a preparation run."""
    provenance = {"notes": settings.get("input_provenance", {}), "files": {},
                  "versions": {"pandas": pd.__version__, "numpy": np.__version__}}
    for key in ("positive_csv", "negative_csv", "metadata_file", "prompt_file", "forced_questions_file", "config_file"):
        path = Path(settings[key])
        provenance["files"][key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    provenance["effective_settings"] = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in settings.items()
    }
    return provenance


def validate_split(train_df, holdout_df, forced_keys):
    """Reject overlapping clusters or exact inputs and forced conditions in training."""
    if set(train_df["cluster_key"]) & set(holdout_df["cluster_key"]):
        raise ValueError("Training and holdout clusters overlap.")
    if set(train_df["condition_key"]) & set(holdout_df["condition_key"]):
        raise ValueError("Training and holdout condition inputs overlap.")
    if set(train_df["condition_key"]) & set(forced_keys):
        raise ValueError("A forced benchmark condition entered training.")
    for name, frame in (("train", train_df), ("holdout", holdout_df)):
        if not frame["is_success"].any() or frame["is_success"].all():
            raise ValueError(f"{name} must contain both P and N records.")


def prepare(settings):
    """Create JSONL, year subsets, split assignments, and a provenance summary."""
    validation = validate_inputs(settings)
    if not validation["valid"]:
        raise ValueError("\n".join(validation["errors"]))
    POS_PATH = settings["positive_csv"]
    NEG_PATH = settings["negative_csv"]
    FULL_METADATA_PATH = settings["metadata_file"]
    OUT_DIR = Path(settings["output_dir"])
    TRAIN_OUT = OUT_DIR / "mof_ft_train.jsonl"
    HOLDOUT_OUT = OUT_DIR / "mof_ft_holdout.jsonl"
    CLASS_MAP_OUT = OUT_DIR / "mof_ft_class_map.json"
    SUMMARY_OUT = OUT_DIR / "mof_ft_split_summary.json"
    SYSTEM_PROMPT = Path(settings["prompt_file"]).read_text(encoding="utf-8")
    FORCED_TEST_QUESTIONS = json.loads(Path(settings["forced_questions_file"]).read_text(encoding="utf-8"))
    RNG_SEED = settings["rng_seed"]
    HOLDOUT_FRAC = settings["holdout_frac"]
    HOLDOUT_CLUSTER_FRAC = settings["holdout_cluster_frac"]
    PN_MODE = settings["pn_mode"]
    CLUSTER_METAL_MODE = settings["cluster_metal_mode"]
    INCLUDE_MODULATOR_IN_CLUSTER = settings["include_modulator_in_cluster"]
    YEAR_BINS = settings["year_bins"]
    YEAR_BINS_5 = settings["year_bins_5"]
    DROP_INPUT_LABEL_CONFLICTS = settings["drop_input_label_conflicts"]
    DEDUP_EXACT_INPUT_WITHIN_LABEL = settings["dedup_exact_input_within_label"]
    HOLDOUT_SEARCH_TRIALS = settings["holdout_search_trials"]
    HOLDOUT_SEARCH_SWAPS = settings["holdout_search_swaps"]
    RAW_PN_REL_TOLERANCE = settings["raw_pn_relative_tolerance"]

    def _write_jsonl(frame, path, seed):
        write_jsonl(frame, path, seed=seed, system_prompt=SYSTEM_PROMPT, shuffle_output=settings["shuffle_output"])

    pos_df = pd.read_csv(POS_PATH, low_memory=False)
    neg_df = pd.read_csv(NEG_PATH, low_memory=False)

    pos_df["is_success"] = True
    neg_df["is_success"] = False

    full_df = pd.concat([pos_df, neg_df], ignore_index=True)
    full_df["source_row_id"] = np.arange(len(full_df), dtype=np.int64)
    n_raw = len(full_df)
    labels_raw = count_labels(full_df)

    # Link DOI to publication year.
    year_map = load_publication_years(FULL_METADATA_PATH)
    full_df["doi_norm"] = pd.Series(None, index=full_df.index, dtype=object)
    for doi_col in ["doi", "DOI", "main_pdf", "si_pdf"]:
        if doi_col in full_df.columns:
            full_df["doi_norm"] = full_df["doi_norm"].fillna(full_df[doi_col].map(normalize_doi))
    full_df = full_df.merge(year_map, on="doi_norm", how="left")

    # Required information for this exact classifier input.
    def has_any(row, cols):
        return any(clean_str(row.get(c)) is not None for c in cols)

    mask = pd.Series(True, index=full_df.index)
    mask &= full_df.apply(lambda r: has_any(r, ["metal_1", "metal_1_abbr"]), axis=1)
    mask &= full_df.apply(
        lambda r: has_any(r, ["linker_1", "linker_1_abbr", "linker_2", "linker_2_abbr", "linker_3", "linker_3_abbr"]),
        axis=1
    )
    mask &= full_df.apply(
        lambda r: has_any(r, ["solvent_main", "solvent_main_abbr", "solvent_secondary", "solvent_secondary_abbr"]),
        axis=1
    )
    # Keep rows with at least two of M/L ratio, metal concentration, and temperature.
    # Drop when more than one of these numeric fields are missing/unparseable.
    numeric_present = pd.DataFrame({
        "M_L_ratio": full_df["M_L_ratio"].map(lambda x: parse_ml_ratio(x) is not None),
        "metal_concentration_mM": full_df["metel_concnertation"].map(lambda x: to_float(x) is not None),
        "temperature_C": full_df["temperature_c"].map(lambda x: to_float(x) is not None),
    })
    mask &= numeric_present.sum(axis=1) >= 2

    filtered_df = full_df[mask].copy()
    n_after_required = len(filtered_df)
    if not n_after_required:
        raise ValueError("No records remain after required-field filtering.")
    labels_after_required = count_labels(filtered_df)

    # Drop N rows from contradictions: same model input, both labels. Keep P rows.
    filtered_df["condition_key"] = filtered_df.apply(canonical_condition_key, axis=1)
    filtered_df["cluster_key"] = filtered_df.apply(lambda row: build_cluster_key(row, CLUSTER_METAL_MODE, INCLUDE_MODULATOR_IN_CLUSTER), axis=1)
    forced_keys = {
        forced_question_condition_key(q["conditions"]) for q in FORCED_TEST_QUESTIONS
    }
    filtered_df["is_forced_condition"] = filtered_df["condition_key"].isin(forced_keys)
    forced_clusters = set(filtered_df.loc[filtered_df["is_forced_condition"], "cluster_key"])
    filtered_df["is_forced_cluster"] = filtered_df["cluster_key"].isin(forced_clusters)

    label_nunique = filtered_df.groupby("condition_key")["is_success"].nunique()
    conflict_keys = set(label_nunique[label_nunique > 1].index)
    n_conflict_rows = int(filtered_df["condition_key"].isin(conflict_keys).sum())

    if DROP_INPUT_LABEL_CONFLICTS and conflict_keys:
        filtered_df = filtered_df[~(
            filtered_df["condition_key"].isin(conflict_keys) & ~filtered_df["is_success"]
        )].copy()
    
    n_after_conflict = len(filtered_df)
    labels_after_conflict = count_labels(filtered_df)

    n_deduped_rows = 0
    if DEDUP_EXACT_INPUT_WITHIN_LABEL:
        before = len(filtered_df)
        filtered_df = filtered_df.drop_duplicates(subset=["condition_key", "is_success"]).copy()
        n_deduped_rows = before - len(filtered_df)

    # Main split by primary metal + all linkers + all solvents.
    # Protect one surviving record per matched question during P/N balancing.
    representative_ids = set(
        filtered_df[filtered_df["is_forced_condition"]]
        .sort_values("source_row_id")
        .drop_duplicates("condition_key")["source_row_id"]
    )
    filtered_df["is_forced_representative"] = filtered_df["source_row_id"].isin(representative_ids)

    # Match benchmark questions by the eight input fields after quality filtering.
    forced_question_mask = pd.Series(False, index=filtered_df.index)
    forced_question_matches = []
    missing_forced_questions = []
    for question in FORCED_TEST_QUESTIONS:
        condition_key = forced_question_condition_key(question["conditions"])
        matched = filtered_df["condition_key"].eq(condition_key)
        forced_question_mask |= matched
        forced_question_matches.append({
            "question": question["question"],
            "reference_label": question["label"],
            "matched_rows": int(matched.sum()),
        })
        if not matched.any():
            missing_forced_questions.append(question["question"])

    raw_pn_ratio = pn_ratio_from_counts(
        labels_after_required[LABEL_POS], labels_after_required[LABEL_NEG]
    )
    holdout_clusters = choose_holdout_clusters(
        filtered_df, HOLDOUT_FRAC, PN_MODE, raw_pn_ratio, settings=settings
    )

    # Keep whole clusters together, including all forced question clusters.
    filtered_df["is_holdout"] = filtered_df["cluster_key"].isin(holdout_clusters)
    train_df = filtered_df[~filtered_df["is_holdout"]].copy()
    holdout_df = filtered_df[filtered_df["is_holdout"]].copy()

    counts_before_pn_enforcement = {
        "train": count_labels(train_df), "holdout": count_labels(holdout_df)
    }
    balance_details = {}
    if PN_MODE == "equal":
        train_df, holdout_df, balance_details = enforce_equal_pn_ratio(
            train_df, holdout_df, raw_pn_ratio, rng_seed=RNG_SEED
        )
        kept_ids = set(train_df["source_row_id"]) | set(holdout_df["source_row_id"])
        filtered_df = filtered_df[filtered_df["source_row_id"].isin(kept_ids)].copy()
        forced_question_mask = forced_question_mask.reindex(filtered_df.index, fill_value=False)

    # Check leakage before creating any output files.
    validate_split(train_df, holdout_df, forced_keys)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write main split.
    _write_jsonl(train_df, TRAIN_OUT, seed=RNG_SEED + 1)
    _write_jsonl(holdout_df, HOLDOUT_OUT, seed=RNG_SEED + 2)

    with open(CLASS_MAP_OUT, "w", encoding="utf-8") as f:
        json.dump({"P": "success", "N": "failure"}, f, ensure_ascii=False, indent=2)

    # Write year bins and cumulative year files within train only.
    year_outputs = []
    bins = make_contiguous_year_bins(train_df, YEAR_BINS)

    for b in bins:
        name = year_range_name(b["start_year"], b["end_year"])
        path = OUT_DIR / f"mof_cls_train_{name}.jsonl"
        _write_jsonl(b["df"], path, seed=RNG_SEED + 100 + b["bin"])
        year_outputs.append({
            "type": "single_bin",
            "bin": int(b["bin"]),
            "path": str(path),
            "start_year": int(b["start_year"]),
            "end_year": int(b["end_year"]),
            "rows": int(len(b["df"])),
            "labels": count_labels(b["df"]),
        })

    # Cumulative 1+2 and 1+2+3 only. No 1 because it is the first bin;
    # no 1+2+3+4 because it is essentially full train for rows with known year.
    for upto in [2, 3]:
        if len(bins) >= upto:
            cum_df = pd.concat([b["df"] for b in bins[:upto]], ignore_index=False)
            start_year = int(bins[0]["start_year"])
            end_year = int(bins[upto - 1]["end_year"])
            name = year_range_name(start_year, end_year)
            path = OUT_DIR / f"mof_cls_train_{name}.jsonl"
            _write_jsonl(cum_df, path, seed=RNG_SEED + 200 + upto)
            year_outputs.append({
                "type": f"cumulative_1to{upto}",
                "path": str(path),
                "start_year": start_year,
                "end_year": end_year,
                "rows": int(len(cum_df)),
                "labels": count_labels(cum_df),
            })

    # Also write five-period year bins and cumulative files within train only.
    year_outputs_5periods = []
    bins_5periods = make_contiguous_year_bins(train_df, YEAR_BINS_5)

    for b in bins_5periods:
        name = year_range_name(b["start_year"], b["end_year"])
        path = OUT_DIR / f"mof_cls_train_5periods_{name}.jsonl"
        _write_jsonl(b["df"], path, seed=RNG_SEED + 100 + b["bin"])
        year_outputs_5periods.append({
            "type": "single_bin",
            "bin": int(b["bin"]),
            "path": str(path),
            "start_year": int(b["start_year"]),
            "end_year": int(b["end_year"]),
            "rows": int(len(b["df"])),
            "labels": count_labels(b["df"]),
        })

    # Cumulative 1+2, 1+2+3, and 1+2+3+4 for the five-period version.
    for upto in [2, 3, 4]:
        if len(bins_5periods) >= upto:
            cum_df = pd.concat([b["df"] for b in bins_5periods[:upto]], ignore_index=False)
            start_year = int(bins_5periods[0]["start_year"])
            end_year = int(bins_5periods[upto - 1]["end_year"])
            name = year_range_name(start_year, end_year)
            path = OUT_DIR / f"mof_cls_train_5periods_{name}.jsonl"
            _write_jsonl(cum_df, path, seed=RNG_SEED + 200 + upto)
            year_outputs_5periods.append({
                "type": f"cumulative_1to{upto}",
                "path": str(path),
                "start_year": start_year,
                "end_year": end_year,
                "rows": int(len(cum_df)),
                "labels": count_labels(cum_df),
            })

    summary = {
        "counts_before_pn_enforcement": counts_before_pn_enforcement,
        "balance": balance_details,
        "forced_holdout": {
            "questions": forced_question_matches,
            "rows_matching_forced_questions": int(forced_question_mask.sum()),
            "questions_not_found_after_filters": missing_forced_questions,
        },
        "config": {
            "rng_seed": RNG_SEED,
            "holdout_frac": HOLDOUT_FRAC,
            "holdout_cluster_frac": HOLDOUT_CLUSTER_FRAC,
            "pn_mode": PN_MODE,
            "raw_pn_relative_tolerance": RAW_PN_REL_TOLERANCE if PN_MODE == "raw10" else None,
            "holdout_search_trials": HOLDOUT_SEARCH_TRIALS,
            "holdout_search_swaps": HOLDOUT_SEARCH_SWAPS,
            "cluster_metal_mode": CLUSTER_METAL_MODE,
            "cluster_definition": "primary metal + all linkers + all solvents"
                                  + (" + all modulators" if INCLUDE_MODULATOR_IN_CLUSTER else ""),
            "drop_input_label_conflicts": DROP_INPUT_LABEL_CONFLICTS,
            "dedup_exact_input_within_label": DEDUP_EXACT_INPUT_WITHIN_LABEL,
        },
        "counts": {
            "input_rows_total": int(n_raw),
            "rows_after_required_field_checks": int(n_after_required),
            "rows_skipped_required": int(n_raw - n_after_required),
            "rows_with_conflicting_input_labels": int(n_conflict_rows),
            "rows_after_conflict_filter": int(n_after_conflict),
            "rows_deduped_exact_input_within_label": int(n_deduped_rows),
            "rows_final": int(len(filtered_df)),
            "rows_with_publication_year_final": int(filtered_df["publication_year"].notna().sum()),
            "train_rows": int(len(train_df)),
            "holdout_rows": int(len(holdout_df)),
            "train_missing_publication_year_rows": int(train_df["publication_year"].isna().sum()),
            "holdout_missing_publication_year_rows": int(holdout_df["publication_year"].isna().sum()),
        },
        "labels": {
            "input": labels_raw,
            "after_required_field_checks": labels_after_required,
            "after_conflict_filter": labels_after_conflict,
            "after_all_drops": count_labels(filtered_df),
            "train": count_labels(train_df),
            "holdout": count_labels(holdout_df),
        },
        "clusters": {
            "unique_clusters_final": int(filtered_df["cluster_key"].nunique()),
            "holdout_clusters": int(holdout_df["cluster_key"].nunique()),
            "train_clusters": int(train_df["cluster_key"].nunique()),
        },
        "outputs": {
            "train": str(TRAIN_OUT),
            "holdout": str(HOLDOUT_OUT),
            "class_map": str(CLASS_MAP_OUT),
            "year_outputs": year_outputs,
            "year_outputs_5periods": year_outputs_5periods,
        },
    }

    summary["provenance"] = input_provenance(settings)
    assignments = pd.concat([train_df.assign(split="train"), holdout_df.assign(split="holdout")])
    assignments = assignments.sort_values("source_row_id")
    assignment_path = OUT_DIR / "mof_ft_split_assignments.csv"
    assignments[["source_row_id", "doi_norm", "publication_year", "condition_key", "cluster_key", "is_success", "is_forced_condition", "is_forced_representative", "split"]].to_csv(assignment_path, index=False, encoding="utf-8-sig")
    summary["outputs"]["split_assignments"] = str(assignment_path)
    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


    return {"summary": summary, "train": train_df, "holdout": holdout_df}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "prepare"))
    parser.add_argument("--config", default="configs/dataset_preparation.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.output_dir is not None:
            settings["output_dir"] = args.output_dir.expanduser().resolve()
        if args.command == "validate":
            result = validate_inputs(settings)
            print(json.dumps(display_paths(result), indent=2))
            return 0 if result["valid"] else 1
        for key, note in settings.get("input_provenance", {}).items():
            print(f"Input provenance ({key}): {display_path(note)}")
        result = prepare(settings)
        print(json.dumps(display_paths(result["summary"]), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Dataset preparation failed: {display_path(exc)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
