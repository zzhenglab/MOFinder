"""Step 5.4: write PN classifier JSONL files from staged Step 5.3 records."""
from __future__ import annotations

import json
from typing import Any, Sequence

import pandas as pd

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    print_config,
    read_stage_csv,
    staged_flat_holdout_path,
    staged_flat_train_path,
    staged_holdout_all_path,
    staged_holdout_year_all_path,
    staged_holdout_year_path,
    staged_train_all_path,
    staged_train_year_path,
)
from utils.common import LINKER_COLS, clean_str, configure_utf8_stdio, parse_ml_ratio, to_float

LABEL_POS = "P"
LABEL_NEG = "N"
CLASS_MAP = {LABEL_POS: "success", LABEL_NEG: "failure"}

SYSTEM_PROMPT = (
    "Act as an expert in reticular chemistry. You will receive reaction conditions as a JSON object "
    "with the fields: metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, "
    "M_L_ratio, temperature_C, and time_h. Based on this, output: "
    "'P' if the conditions are likely to yield a crystalline metal-organic framework under experimental "
    "conditions, or 'N' if not."
)

MODULATOR_COLS = ["modulator_1", "modulator_2"]


def collect_nonempty_fields(row: pd.Series, cols: Sequence[str]) -> list[str]:
    out = []
    for c in cols:
        if c in row.index:
            v = clean_str(row.get(c))
            if v is not None:
                out.append(v)
    return out


def join_fields(values: Sequence[str], sep: str = "; ") -> str | None:
    return sep.join(values) if values else None


def format_solvent(main_s: Any, secondary_s: Any, *, dedupe_secondary: bool = False) -> str | None:
    main = clean_str(main_s)
    secondary = clean_str(secondary_s)
    if main and secondary and (not dedupe_secondary or main != secondary):
        return f"{main} and {secondary}"
    return main if main else None


def row_to_conditions(
    row: pd.Series,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
    dedupe_secondary_solvent: bool = False,
) -> dict[str, Any]:
    if multi_linker:
        organic_linker = join_fields(collect_nonempty_fields(row, LINKER_COLS), sep="; ")
        modulator = join_fields(collect_nonempty_fields(row, MODULATOR_COLS), sep="; ")
    else:
        organic_linker = clean_str(row.get("linker_1"))
        modulator_1 = clean_str(row.get("modulator_1"))
        modulator = modulator_1 if modulator_1 is not None else None

    if include_secondary_solvent:
        solvent = format_solvent(
            row.get("solvent_main"),
            row.get("solvent_secondary"),
            dedupe_secondary=dedupe_secondary_solvent,
        )
    else:
        solvent = clean_str(row.get("solvent_main"))

    return {
        "metal_precursor": clean_str(row.get("metal_1")),
        "organic_linker": organic_linker,
        "modulator": modulator,
        "solvent": solvent,
        "metal_concentration_mM": to_float(row.get("metel_concnertation")),
        "M_L_ratio": parse_ml_ratio(row.get("M_L_ratio")),
        "temperature_C": to_float(row.get("temperature_c")),
        "time_h": to_float(row.get("time_h")),
    }


def to_messages_record(
    row: pd.Series,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
    dedupe_secondary_solvent: bool = False,
    system_prompt: str = SYSTEM_PROMPT,
) -> dict[str, Any]:
    user_json = row_to_conditions(
        row,
        multi_linker=multi_linker,
        include_secondary_solvent=include_secondary_solvent,
        dedupe_secondary_solvent=dedupe_secondary_solvent,
    )
    label = LABEL_POS if bool(row["is_success"]) else LABEL_NEG
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_json, ensure_ascii=False)},
            {"role": "assistant", "content": label},
        ]
    }


def write_jsonl(
    df: pd.DataFrame,
    path,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
    dedupe_secondary_solvent: bool = False,
    encoding: str = "utf-8",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        for _, row in df.iterrows():
            rec = to_messages_record(
                row,
                multi_linker=multi_linker,
                include_secondary_solvent=include_secondary_solvent,
                dedupe_secondary_solvent=dedupe_secondary_solvent,
            )
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_class_map(path, *, encoding: str = "utf-8", ensure_ascii: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        json.dump(CLASS_MAP, f, ensure_ascii=ensure_ascii, indent=2)


def write_record_jsonl(cfg, df, path) -> None:
    write_jsonl(
        df,
        path,
        multi_linker=cfg.spec.multi_linker,
        include_secondary_solvent=cfg.spec.include_secondary_solvent,
        dedupe_secondary_solvent=cfg.spec.dedupe_secondary_solvent,
        encoding=cfg.spec.jsonl_encoding,
    )


def main() -> None:
    args = build_parser(default_option="d").parse_args()
    cfg = config_from_args(args)
    if args.dry_run:
        print_config(cfg)
        print("Stage:           5.4 write final JSONL")
        missing = []
        for seed in cfg.resolved_seeds:
            if cfg.spec.use_year_splits:
                for name in cfg.resolved_split_names:
                    missing.extend(missing_paths([staged_train_year_path(cfg, seed, name), staged_holdout_year_path(cfg, seed, name)]))
                if cfg.spec.write_train_all:
                    missing.extend(missing_paths([staged_train_all_path(cfg, seed)]))
                if cfg.spec.write_holdout_all:
                    missing.extend(missing_paths([staged_holdout_all_path(cfg, seed)]))
                if cfg.spec.write_holdout_year_all:
                    missing.extend(missing_paths([staged_holdout_year_all_path(cfg, seed)]))
            else:
                missing.extend(missing_paths([staged_flat_train_path(cfg, seed), staged_flat_holdout_path(cfg, seed)]))
        if missing:
            print("Missing intermediates:")
            for path in missing:
                print(f"  - {path}")
        return

    configure_utf8_stdio()
    cfg.resolved_out_dir.mkdir(parents=True, exist_ok=True)
    class_map_path = cfg.resolved_out_dir / "mof_cls_class_map.json"
    write_class_map(
        class_map_path,
        encoding=cfg.spec.class_map_encoding,
        ensure_ascii=cfg.spec.class_map_ensure_ascii,
    )

    written = [class_map_path]
    print("=== Step 5.4 Write JSONL ===")
    print(f"Option: {cfg.spec.option} ({cfg.spec.title})")
    print(f"Class map: {class_map_path}")

    for seed in cfg.resolved_seeds:
        if not cfg.spec.use_year_splits:
            train_df = read_stage_csv(staged_flat_train_path(cfg, seed))
            holdout_df = read_stage_csv(staged_flat_holdout_path(cfg, seed))
            if cfg.spec.layout == "flat":
                train_path = cfg.resolved_out_dir / "mof_cls_train.jsonl"
                holdout_path = cfg.resolved_out_dir / "mof_cls_holdout.jsonl"
            else:
                seed_dir = cfg.resolved_out_dir / f"seed_{seed}"
                train_path = seed_dir / "mof_cls_train.jsonl"
                holdout_path = seed_dir / "mof_cls_holdout.jsonl"
            write_record_jsonl(cfg, train_df, train_path)
            write_record_jsonl(cfg, holdout_df, holdout_path)
            written.extend([train_path, holdout_path])
            print(f"Seed {seed}: wrote train={len(train_df)}, holdout={len(holdout_df)}")
            continue

        seed_dir = cfg.resolved_out_dir / f"seed_{seed}"
        for name in cfg.resolved_split_names:
            train_df = read_stage_csv(staged_train_year_path(cfg, seed, name))
            holdout_df = read_stage_csv(staged_holdout_year_path(cfg, seed, name))
            train_path = seed_dir / f"mof_cls_train_year_{name}.jsonl"
            holdout_path = seed_dir / f"mof_cls_holdout_year_{name}.jsonl"
            write_record_jsonl(cfg, train_df, train_path)
            write_record_jsonl(cfg, holdout_df, holdout_path)
            written.extend([train_path, holdout_path])

        if cfg.spec.write_holdout_year_all:
            path = seed_dir / "mof_cls_holdout_year.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_holdout_year_all_path(cfg, seed)), path)
            written.append(path)
        if cfg.spec.write_train_all:
            path = seed_dir / "mof_cls_train_all.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_train_all_path(cfg, seed)), path)
            written.append(path)
        if cfg.spec.write_holdout_all:
            path = seed_dir / "mof_cls_holdout_all.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_holdout_all_path(cfg, seed)), path)
            written.append(path)
        print(f"Seed {seed}: wrote year-wise outputs to {seed_dir}")

    print("Wrote files:")
    for path in written:
        print(f"  {path}")

    if cfg.spec.print_sample_records:
        sample_path = cfg.resolved_out_dir / "mof_cls_train.jsonl"
        print("\nSample train records:")
        with open(sample_path, "r", encoding=cfg.spec.jsonl_encoding) as f:
            for i, line in enumerate(f):
                if i >= 2:
                    break
                print(line.strip())


if __name__ == "__main__":
    main()
