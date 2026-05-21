"""Step 5.4: write PN classifier JSONL files from staged Step 5.3 records."""
from __future__ import annotations

import json
from typing import Any

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
from utils.common import configure_utf8_stdio, row_to_classifier_conditions

LABEL_POS = "P"
LABEL_NEG = "N"
CLASS_MAP = {LABEL_POS: "success", LABEL_NEG: "failure"}

SYSTEM_PROMPT = (
    "Act as an expert in reticular chemistry. You will receive reaction conditions as a JSON object with the fields: \n"
    "    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, and time_h. \n"
    "    Based on these inputs, output exactly one uppercase label: 'P' if the conditions are likely to yield a crystalline \n"
    "    metal-organic framework under experimental conditions, or 'N' if not."
)


def row_to_conditions(
    row: pd.Series,
    *,
    multi_linker: bool,
    include_secondary_solvent: bool,
    dedupe_secondary_solvent: bool = False,
) -> dict[str, Any]:
    return row_to_classifier_conditions(
        row,
        multi_linker=multi_linker,
        include_secondary_solvent=include_secondary_solvent,
        dedupe_secondary_solvent=dedupe_secondary_solvent,
    )


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
    shuffle_output: bool = False,
    seed: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df
    if shuffle_output and len(out) > 1:
        out = out.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    with open(path, "w", encoding=encoding) as f:
        for _, row in out.iterrows():
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


def write_record_jsonl(cfg, df, path, *, seed: int | None = None) -> None:
    write_jsonl(
        df,
        path,
        multi_linker=cfg.spec.multi_linker,
        include_secondary_solvent=cfg.spec.include_secondary_solvent,
        dedupe_secondary_solvent=cfg.spec.dedupe_secondary_solvent,
        encoding=cfg.spec.jsonl_encoding,
        shuffle_output=cfg.spec.shuffle_output,
        seed=seed,
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
            write_record_jsonl(cfg, train_df, train_path, seed=seed + 1)
            write_record_jsonl(cfg, holdout_df, holdout_path, seed=seed + 2)
            written.extend([train_path, holdout_path])
            print(f"Seed {seed}: wrote train={len(train_df)}, holdout={len(holdout_df)}")
            continue

        seed_dir = cfg.resolved_out_dir / f"seed_{seed}"
        for name in cfg.resolved_split_names:
            train_df = read_stage_csv(staged_train_year_path(cfg, seed, name))
            holdout_df = read_stage_csv(staged_holdout_year_path(cfg, seed, name))
            train_path = seed_dir / f"mof_cls_train_year_{name}.jsonl"
            holdout_path = seed_dir / f"mof_cls_holdout_year_{name}.jsonl"
            write_record_jsonl(cfg, train_df, train_path, seed=seed + 1)
            write_record_jsonl(cfg, holdout_df, holdout_path, seed=seed + 2)
            written.extend([train_path, holdout_path])

        if cfg.spec.write_holdout_year_all:
            path = seed_dir / "mof_cls_holdout_year.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_holdout_year_all_path(cfg, seed)), path, seed=seed + 2)
            written.append(path)
        if cfg.spec.write_train_all:
            path = seed_dir / "mof_cls_train_all.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_train_all_path(cfg, seed)), path, seed=seed + 1)
            written.append(path)
        if cfg.spec.write_holdout_all:
            path = seed_dir / "mof_cls_holdout_all.jsonl"
            write_record_jsonl(cfg, read_stage_csv(staged_holdout_all_path(cfg, seed)), path, seed=seed + 2)
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
