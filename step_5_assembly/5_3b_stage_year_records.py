"""Step 5.3b: stage year-wise F/G/H/I record tables before JSONL writing.

Used by options:
    c  year-wise without interleave
    d  year-wise with 11/17 interleave
"""
from __future__ import annotations

import re
from typing import Any, Sequence

import numpy as np
import pandas as pd

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    print_config,
    read_stage_csv,
    staged_holdout_all_path,
    staged_holdout_year_all_path,
    staged_holdout_year_path,
    staged_train_all_path,
    staged_train_year_path,
    split_holdout_path,
    split_train_path,
    write_stage_csv,
)
from utils.common import (
    configure_utf8_stdio,
    count_labels,
    interleave_by_ratio,
)


def normalize_doi_lower(x: Any) -> str | None:
    if pd.isna(x):
        return None
    s = str(x).strip().lower()
    return None if s in {"", "na", "n/a", "nan"} else s


def normalize_doi_keep_case(x: Any) -> str | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "":
        return None
    if s.lower() in {"nan", "na", "none", "n/a"}:
        return None
    return s


def parse_year(x: Any) -> int | None:
    if pd.isna(x):
        return None
    m = re.search(r"\d{4}", str(x))
    if not m:
        return None
    y = int(m.group(0))
    return y if 1800 <= y <= 2100 else None


def load_metadata_years(full_metadata_path, *, keep_case_doi: bool) -> pd.DataFrame:
    missing = missing_paths([full_metadata_path])
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(f"Missing Step-5 metadata file(s):\n{lines}")

    full_meta = pd.read_excel(full_metadata_path)
    if "DOI" not in full_meta.columns or "Publication Year" not in full_meta.columns:
        raise ValueError(f"{full_metadata_path} must contain columns: 'DOI' and 'Publication Year'")

    normalizer = normalize_doi_keep_case if keep_case_doi else normalize_doi_lower
    full_meta["norm_doi"] = full_meta["DOI"].apply(normalizer)
    full_meta["pub_year"] = full_meta["Publication Year"].apply(parse_year)
    return (
        full_meta.dropna(subset=["norm_doi"])
        .sort_values("pub_year", na_position="last")
        .drop_duplicates(subset="norm_doi", keep="first")[["norm_doi", "pub_year"]]
    )


def make_year_splits(
    df: pd.DataFrame,
    meta_year: pd.DataFrame,
    split_names: Sequence[str],
    *,
    keep_case_doi: bool,
    tolerate_missing_doi_column: bool,
) -> dict[str, pd.DataFrame]:
    working = df.copy()
    normalizer = normalize_doi_keep_case if keep_case_doi else normalize_doi_lower

    if "doi" in working.columns:
        working["norm_doi"] = working["doi"].apply(normalizer)
    elif tolerate_missing_doi_column:
        working["norm_doi"] = None
    else:
        working["norm_doi"] = working["doi"].apply(normalizer)

    has_doi = working["norm_doi"].notna()
    working["doi_group"] = None
    working.loc[has_doi, "doi_group"] = working.loc[has_doi, "norm_doi"]
    working.loc[~has_doi, "doi_group"] = "missing_doi_" + working.index[~has_doi].astype(str)

    working = working.merge(meta_year, on="norm_doi", how="left")

    group_stats = (
        working.groupby("doi_group", dropna=False)
        .agg(
            n_rows=("is_success", "size"),
            pub_year=("pub_year", lambda x: x.dropna().iloc[0] if x.dropna().size else np.nan),
        )
        .reset_index()
    )

    groups_missing = group_stats[group_stats["pub_year"].isna()]
    groups_known = group_stats[group_stats["pub_year"].notna()].sort_values("pub_year")
    total_rows = group_stats["n_rows"].sum()
    if total_rows == 0:
        return {name: working.iloc[0:0].copy() for name in split_names}

    target = total_rows / len(split_names)
    split_keys: dict[int, list[Any]] = {i: [] for i in range(len(split_names))}
    split_counts = [0] * len(split_names)

    for _, row in groups_missing.iterrows():
        split_keys[0].append(row["doi_group"])
        split_counts[0] += row["n_rows"]

    cur = 0
    for _, row in groups_known.iterrows():
        if cur < len(split_names) - 1 and split_counts[cur] >= target:
            cur += 1
        split_keys[cur].append(row["doi_group"])
        split_counts[cur] += row["n_rows"]

    return {
        name: working[working["doi_group"].isin(split_keys[i])].copy()
        for i, name in enumerate(split_names)
    }


def year_range_desc(df: pd.DataFrame) -> str:
    if "pub_year" not in df.columns:
        return "no known publication year"
    years = df["pub_year"].dropna()
    if years.empty:
        return "no known publication year"
    years = years.astype(int)
    mn, mx = int(years.min()), int(years.max())
    return f"{mn}" if mn == mx else f"{mn}-{mx}"


def main() -> None:
    args = build_parser(default_option="d").parse_args()
    cfg = config_from_args(args)
    if not cfg.spec.use_year_splits:
        raise SystemExit(f"Option {cfg.spec.option} is flat; run 5_3a_stage_flat_records.py.")
    if args.dry_run:
        print_config(cfg)
        print("Stage:           5.3b year-wise record staging")
        missing = missing_paths([cfg.full_metadata_path])
        for seed in cfg.resolved_seeds:
            missing.extend(missing_paths([split_train_path(cfg, seed), split_holdout_path(cfg, seed)]))
        if missing:
            print("Missing inputs/intermediates:")
            for path in missing:
                print(f"  - {path}")
        return

    configure_utf8_stdio()
    meta_year = load_metadata_years(cfg.full_metadata_path, keep_case_doi=cfg.spec.keep_case_doi)
    print("=== Step 5.3b Year-Wise Record Staging ===")
    print(f"Option: {cfg.spec.option} ({cfg.spec.title})")

    for seed in cfg.resolved_seeds:
        train_df = read_stage_csv(split_train_path(cfg, seed))
        holdout_df = read_stage_csv(split_holdout_path(cfg, seed))
        train_splits = make_year_splits(
            train_df,
            meta_year,
            cfg.resolved_split_names,
            keep_case_doi=cfg.spec.keep_case_doi,
            tolerate_missing_doi_column=cfg.spec.tolerate_missing_doi_column,
        )
        holdout_splits = make_year_splits(
            holdout_df,
            meta_year,
            cfg.resolved_split_names,
            keep_case_doi=cfg.spec.keep_case_doi,
            tolerate_missing_doi_column=cfg.spec.tolerate_missing_doi_column,
        )

        for name in cfg.resolved_split_names:
            if cfg.spec.interleave_train_splits:
                train_splits[name] = interleave_by_ratio(
                    train_splits[name],
                    n_pos=cfg.resolved_p_block,
                    n_neg=cfg.resolved_n_block,
                    rng_seed=seed,
                )
            if cfg.spec.interleave_holdout_splits:
                holdout_splits[name] = interleave_by_ratio(
                    holdout_splits[name],
                    n_pos=cfg.resolved_p_block,
                    n_neg=cfg.resolved_n_block,
                    rng_seed=seed,
                )
            write_stage_csv(train_splits[name], staged_train_year_path(cfg, seed, name))
            write_stage_csv(holdout_splits[name], staged_holdout_year_path(cfg, seed, name))

        if cfg.spec.write_train_all:
            write_stage_csv(train_df, staged_train_all_path(cfg, seed))
        if cfg.spec.write_holdout_all:
            write_stage_csv(holdout_df, staged_holdout_all_path(cfg, seed))
        if cfg.spec.write_holdout_year_all:
            write_stage_csv(holdout_df, staged_holdout_year_all_path(cfg, seed))

        print(f"Seed {seed}:")
        print("  Train year splits:")
        for name in cfg.resolved_split_names:
            p_count, n_count = count_labels(train_splits[name])
            print(f"    {name}: size={len(train_splits[name])}, P={p_count}, N={n_count}, years={year_range_desc(train_splits[name])}")
        print("  Holdout year splits:")
        for name in cfg.resolved_split_names:
            p_count, n_count = count_labels(holdout_splits[name])
            print(f"    {name}: size={len(holdout_splits[name])}, P={p_count}, N={n_count}, years={year_range_desc(holdout_splits[name])}")


if __name__ == "__main__":
    main()
