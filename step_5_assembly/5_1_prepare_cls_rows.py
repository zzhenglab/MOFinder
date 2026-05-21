"""Step 5.1: read/filter PN rows and build leakage-aware cluster keys."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    prepared_csv_path,
    prepared_stats_path,
    print_config,
    write_json,
    write_stage_csv,
    work_dir,
)
from utils.common import (
    LINKER_COLS,
    clean_str,
    collect_linkers,
    collect_modulators,
    collect_solvents,
    configure_utf8_stdio,
    non_empty,
    norm_for_key,
    parse_ml_ratio,
    primary_metal_precursor,
    row_to_classifier_conditions,
    to_float,
)


FULL_FAMILY_REGEX = [
    (r"\b(bpdc)\b|biphenyl.*dicarboxyl", "bpdc"),
    (r"\b(bdc)\b|terephthal.*acid|1[, -]?4.*benzenedicarboxyl", "bdc"),
    (r"\b(ipc|ipa)\b|isophthal.*acid|1[, -]?3.*benzenedicarboxyl", "isophthalate"),
    (r"\b(ndc)\b|naphthal.*dicarboxyl", "ndc"),
    (r"\b(btc)\b|trimesic|1[, -]?3[, -]?5.*tricarboxyl", "btc"),
    (r"\b(tcpp)\b|porphyrin.*tetrakis|tetrakis.*porphyrin|porphyrin.*carboxyl", "tcpp"),
    (r"\b(bpy|bipy)\b|bipyridin", "bpy"),
    (r"pyrazin|(\bpyz\b)", "pyz"),
    (r"imidazol|(\bmim\b)", "imidazole"),
    (r"triazine|hexa.*carboxyl|(\bhat\b)", "triazine_hexacarboxyl"),
    (r"carbazol|(\bczdc\b)", "carbazole"),
]

SIMPLE_FAMILY_REGEX = [
    (r"\b(bpdc)\b|biphenyl.*dicarboxyl", "bpdc"),
    (r"\b(bdc)\b|terephthal", "bdc"),
    (r"\b(btc)\b|trimesic", "btc"),
    (r"\b(ndc)\b", "ndc"),
    (r"\b(bpy|bipy)\b", "bpy"),
    (r"imidazol|(\bmim\b)", "imidazole"),
]

YEAR_FAMILY_REGEX = [
    (r"\b(bpdc)\b|biphenyl.*dicarboxyl", "bpdc"),
    (r"\b(bdc)\b|terephthal", "bdc"),
    (r"\b(ipc|ipa)\b|isophthal", "isophthalate"),
    (r"\b(ndc)\b|naphthal", "ndc"),
    (r"\b(btc)\b|trimesic", "btc"),
    (r"\b(tcpp)\b|porphyrin", "tcpp"),
    (r"\b(bpy|bipy)\b", "bpy"),
    (r"\bpyz\b|pyrazin", "pyz"),
    (r"\bmim\b|imidazol", "imidazole"),
]

SOLVENT_NAME_COLS = ["solvent_main", "solvent_secondary"]
SOLVENT_ABBR_COLS = ["solvent_main_abbr", "solvent_secondary_abbr"]

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
    "rhodium": "Rh", "iridium": "Ir", "osmium": "Os",
}


def read_labeled_inputs(pos_path: Path, neg_path: Path) -> tuple[pd.DataFrame, int]:
    missing = missing_paths([pos_path, neg_path])
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(f"Missing Step-5 input file(s):\n{lines}")
    pos_df = pd.read_csv(pos_path, low_memory=False)
    neg_df = pd.read_csv(neg_path, low_memory=False)
    pos_df["is_success"] = True
    neg_df["is_success"] = False
    full_df = pd.concat([pos_df, neg_df], ignore_index=True)
    return full_df, len(full_df)


def get_primary_linker_and_abbr(row: pd.Series) -> tuple[str | None, str | None]:
    for i in [1, 2, 3]:
        linker_col = f"linker_{i}"
        if linker_col in row.index:
            linker_val = clean_str(row.get(linker_col))
            if linker_val:
                abbr_col = f"linker_{i}_abbr"
                linker_abbr = clean_str(row.get(abbr_col)) if abbr_col in row.index else None
                return linker_val, linker_abbr
    return None, None


def extract_metal_element(row: pd.Series) -> str:
    abbr = clean_str(row.get("metal_1_abbr"))
    if abbr:
        m = re.search(r"\b([A-Z][a-z]?)\b", abbr)
        if m:
            return m.group(1).lower()
    metal1 = clean_str(row.get("metal_1"))
    if not metal1:
        return "me_unknown"
    m = re.match(r"\s*([A-Z][a-z]?)", metal1)
    return m.group(1).lower() if m else "me_unknown"


def extract_primary_metal_element(row: pd.Series) -> str:
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
        if re.search(rf"\b{re.escape(name)}\b", low):
            return sym

    text = re.sub(r"^[^A-Za-z]+", "", text)
    m = re.match(r"([A-Z][a-z]?)", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]?)\b", text)
    return m.group(1) if m else "Me_unknown"


def canonical_set_key(values: Sequence[Any]) -> str:
    vals = sorted({v for v in (norm_for_key(value) for value in values) if v})
    return " + ".join(vals) if vals else "unknown"


def canonical_condition_key(
    row: pd.Series,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
) -> str:
    cond = row_to_classifier_conditions(
        row,
        multi_linker=multi_linker,
        include_secondary_solvent=include_secondary_solvent,
    )
    key: dict[str, Any] = {}
    for k, v in cond.items():
        if isinstance(v, (float, int, np.floating, np.integer)):
            key[k] = None if pd.isna(v) else round(float(v), 8)
        elif v is None:
            key[k] = None
        else:
            key[k] = norm_for_key(v)
    return json.dumps(key, sort_keys=True, ensure_ascii=False)


def linker_family_from_abbr_full(abbr: str) -> str | None:
    a = abbr.lower()
    if "bpdc" in a:
        return "bpdc"
    if "bdc" in a:
        return "bdc"
    if "btc" in a:
        return "btc"
    if "ndc" in a:
        return "ndc"
    if "bpy" in a or "bipy" in a:
        return "bpy"
    if "mim" in a:
        return "imidazole"
    if "pyz" in a:
        return "pyz"
    if "tcpp" in a:
        return "tcpp"
    if "ipa" in a or "ipc" in a:
        return "isophthalate"
    return None


def linker_family_from_abbr_simple(abbr: str) -> str | None:
    a = abbr.lower()
    for k in ["bpdc", "bdc", "btc", "ndc", "bpy", "mim"]:
        if k in a:
            return "imidazole" if k == "mim" else k
    return None


def linker_family_from_abbr_year(abbr: str) -> str | None:
    a = abbr.lower()
    for k in ["bpdc", "bdc", "btc", "ndc", "bpy", "tcpp"]:
        if k in a:
            return k
    if "ipa" in a or "ipc" in a:
        return "isophthalate"
    return None


def infer_linker_family(linker_text: str | None, linker_abbr: str | None, *, mode: str) -> str:
    if mode == "simple":
        if linker_abbr:
            fam = linker_family_from_abbr_simple(linker_abbr)
            if fam:
                return fam
        if not linker_text:
            return "linker_other"
        t = linker_text.lower()
        for pat, fam in SIMPLE_FAMILY_REGEX:
            if re.search(pat, t):
                return fam
        return "linker_other"

    if mode == "year":
        if linker_abbr:
            fam = linker_family_from_abbr_year(linker_abbr)
            if fam:
                return fam
        if not linker_text:
            return "linker_other"
        t = linker_text.lower()
        for pat, fam in YEAR_FAMILY_REGEX:
            if re.search(pat, t):
                return fam
        return "linker_other"

    if linker_abbr:
        fam = linker_family_from_abbr_full(linker_abbr)
        if fam:
            return fam
    if not linker_text:
        return "linker_other"
    t = linker_text.lower()
    t = re.sub(r"\b\d+(\.\d+)?\b", " ", t)
    t = t.replace("'", " ")
    t = re.sub(r"\s+", " ", t)
    for pat, fam in FULL_FAMILY_REGEX:
        if re.search(pat, t):
            return fam
    if "carboxyl" in t or "carboxylic" in t or "acid" in t:
        return "aromatic_carboxylate"
    if "pyridine" in t:
        return "pyridine_family"
    return "linker_other"


def build_cluster_key(
    row: pd.Series,
    *,
    family_mode: str,
    cluster_metal_mode: str = "element",
    include_modulator_in_cluster: bool = False,
) -> str:
    if family_mode == "condition_set":
        if cluster_metal_mode == "element":
            metal_key = norm_for_key(extract_primary_metal_element(row))
        elif cluster_metal_mode == "precursor":
            metal_key = norm_for_key(primary_metal_precursor(row))
        else:
            raise ValueError("cluster_metal_mode must be 'precursor' or 'element'.")

        parts = [
            f"metal={metal_key or 'unknown'}",
            f"linker={canonical_set_key(collect_linkers(row))}",
            f"solvent={canonical_set_key(collect_solvents(row))}",
        ]
        if include_modulator_in_cluster:
            parts.append(f"modulator={canonical_set_key(collect_modulators(row))}")
        return "|".join(parts)

    metal = extract_metal_element(row)
    primary_linker, primary_abbr = get_primary_linker_and_abbr(row)
    fam = infer_linker_family(primary_linker, primary_abbr, mode=family_mode)
    return f"{metal}|{fam}"


def validate_required_columns(
    df: pd.DataFrame,
    required_cols: Sequence[str],
    *,
    require_any_linker: bool,
    require_any_metal: bool,
    require_any_solvent: bool,
) -> None:
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"Missing required column: {c}")
    if require_any_linker and not any(c in df.columns for c in LINKER_COLS):
        raise ValueError(f"None of linker columns found in CSV: {LINKER_COLS}")
    if require_any_metal and not any(c in df.columns for c in ["metal_1", "metal_1_abbr"]):
        raise ValueError("None of metal columns found in CSV: ['metal_1', 'metal_1_abbr']")
    solvent_cols = [*SOLVENT_NAME_COLS, *SOLVENT_ABBR_COLS]
    if require_any_solvent and not any(c in df.columns for c in solvent_cols):
        raise ValueError(f"None of solvent columns found in CSV: {solvent_cols}")


def has_any_clean(row: pd.Series, cols: Sequence[str]) -> bool:
    return any(clean_str(row.get(c)) is not None for c in cols)


def required_mask(
    df: pd.DataFrame,
    required_cols: Sequence[str],
    *,
    require_any_linker: bool,
    require_any_metal: bool,
    require_any_solvent: bool,
) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for c in required_cols:
        mask &= non_empty(df[c])

    if require_any_linker:
        linker_cols = []
        for linker_col in LINKER_COLS:
            linker_cols.append(linker_col)
            linker_cols.append(f"{linker_col}_abbr")
        mask &= df.apply(lambda row: has_any_clean(row, linker_cols), axis=1)

    if require_any_metal:
        mask &= df.apply(lambda row: has_any_clean(row, ["metal_1", "metal_1_abbr"]), axis=1)

    if require_any_solvent:
        solvent_cols = [*SOLVENT_NAME_COLS, *SOLVENT_ABBR_COLS]
        mask &= df.apply(lambda row: has_any_clean(row, solvent_cols), axis=1)

    mask &= pd.Series([to_float(x) is not None for x in df["metal_concentration"]], index=df.index)
    mask &= pd.Series([parse_ml_ratio(x) is not None for x in df["M_L_ratio"]], index=df.index)
    return mask


def load_filter_and_cluster(
    pos_path: Path,
    neg_path: Path,
    *,
    required_cols: Sequence[str],
    require_any_linker: bool,
    require_any_metal: bool,
    require_any_solvent: bool,
    family_mode: str,
    cluster_metal_mode: str = "element",
    include_modulator_in_cluster: bool = False,
    multi_linker: bool = False,
    include_secondary_solvent: bool = True,
    drop_input_label_conflicts: bool = False,
    dedupe_exact_input_within_label: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    full_df, n_raw = read_labeled_inputs(pos_path, neg_path)
    validate_required_columns(
        full_df,
        required_cols,
        require_any_linker=require_any_linker,
        require_any_metal=require_any_metal,
        require_any_solvent=require_any_solvent,
    )
    mask = required_mask(
        full_df,
        required_cols,
        require_any_linker=require_any_linker,
        require_any_metal=require_any_metal,
        require_any_solvent=require_any_solvent,
    )
    filtered_df = full_df[mask].copy()
    n_after_required = len(filtered_df)

    filtered_df["condition_key"] = filtered_df.apply(
        lambda row: canonical_condition_key(
            row,
            multi_linker=multi_linker,
            include_secondary_solvent=include_secondary_solvent,
        ),
        axis=1,
    )
    label_nunique = filtered_df.groupby("condition_key")["is_success"].nunique()
    conflict_keys = set(label_nunique[label_nunique > 1].index)
    n_conflict_rows = int(filtered_df["condition_key"].isin(conflict_keys).sum())
    if drop_input_label_conflicts and conflict_keys:
        filtered_df = filtered_df[~filtered_df["condition_key"].isin(conflict_keys)].copy()
    n_after_conflict = len(filtered_df)

    n_deduped_rows = 0
    if dedupe_exact_input_within_label:
        before = len(filtered_df)
        filtered_df = filtered_df.drop_duplicates(subset=["condition_key", "is_success"]).copy()
        n_deduped_rows = before - len(filtered_df)

    filtered_df["cluster_key"] = filtered_df.apply(
        lambda row: build_cluster_key(
            row,
            family_mode=family_mode,
            cluster_metal_mode=cluster_metal_mode,
            include_modulator_in_cluster=include_modulator_in_cluster,
        ),
        axis=1,
    )
    stats = {
        "n_raw": n_raw,
        "n_after_required": n_after_required,
        "n_conflict_rows": n_conflict_rows,
        "n_after_conflict": n_after_conflict,
        "n_deduped_rows": n_deduped_rows,
        "n_after_filter": len(filtered_df),
        "n_skipped": n_raw - n_after_required,
        "n_clusters": int(filtered_df["cluster_key"].nunique()),
    }
    return filtered_df, stats


def main() -> None:
    args = build_parser(default_option="d").parse_args()
    cfg = config_from_args(args)
    if args.dry_run:
        print_config(cfg)
        print("Stage:           5.1 prepare filtered+clustered rows")
        print(f"Work dir:        {work_dir(cfg)}")
        missing = missing_paths([cfg.pos_path, cfg.neg_path])
        if missing:
            print("Missing inputs:")
            for path in missing:
                print(f"  - {path}")
        return

    configure_utf8_stdio()
    spec = cfg.spec
    filtered_df, stats = load_filter_and_cluster(
        cfg.pos_path,
        cfg.neg_path,
        required_cols=spec.required_cols,
        require_any_linker=spec.require_any_linker,
        require_any_metal=spec.require_any_metal,
        require_any_solvent=spec.require_any_solvent,
        family_mode=spec.family_mode,
        cluster_metal_mode=spec.cluster_metal_mode,
        include_modulator_in_cluster=spec.include_modulator_in_cluster,
        multi_linker=spec.multi_linker,
        include_secondary_solvent=spec.include_secondary_solvent,
        drop_input_label_conflicts=spec.drop_input_label_conflicts,
        dedupe_exact_input_within_label=spec.dedupe_exact_input_within_label,
    )
    write_stage_csv(filtered_df, prepared_csv_path(cfg))
    write_json(prepared_stats_path(cfg), dict(stats))

    print("=== Step 5.1 Prepared Rows ===")
    print(f"Option: {spec.option} ({spec.title})")
    print(f"Input rows total: {stats['n_raw']}")
    print(f"Rows kept after required field checks: {stats['n_after_required']}")
    print(f"Rows skipped: {stats['n_skipped']}")
    print(f"Rows with same input JSON but both P and N: {stats['n_conflict_rows']}")
    if spec.drop_input_label_conflicts:
        print(f"Rows after conflict drop: {stats['n_after_conflict']}")
    if spec.dedupe_exact_input_within_label:
        print(f"Rows deduped within label: {stats['n_deduped_rows']}")
    print(f"Rows final: {stats['n_after_filter']}")
    print(f"Coarse unique clusters: {stats['n_clusters']}")
    print(f"Wrote: {prepared_csv_path(cfg)}")
    print(f"Wrote: {prepared_stats_path(cfg)}")


if __name__ == "__main__":
    main()
