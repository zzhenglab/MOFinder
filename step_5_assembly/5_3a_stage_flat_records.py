"""Step 5.3a: stage flat train/holdout record tables before JSONL writing.

Used by options:
    a  flat random split
    b  flat split with 11/17 train interleave
"""
from __future__ import annotations

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    print_config,
    read_stage_csv,
    staged_flat_holdout_path,
    staged_flat_train_path,
    split_holdout_path,
    split_train_path,
    write_stage_csv,
)
from utils.common import configure_utf8_stdio, interleave_by_ratio


def main() -> None:
    args = build_parser(default_option="b").parse_args()
    cfg = config_from_args(args)
    if cfg.spec.use_year_splits:
        raise SystemExit(f"Option {cfg.spec.option} is year-wise; run 5_3b_stage_year_records.py.")
    if args.dry_run:
        print_config(cfg)
        print("Stage:           5.3a flat record staging")
        missing = []
        for seed in cfg.resolved_seeds:
            missing.extend(missing_paths([split_train_path(cfg, seed), split_holdout_path(cfg, seed)]))
        if missing:
            print("Missing intermediates:")
            for path in missing:
                print(f"  - {path}")
        return

    configure_utf8_stdio()
    print("=== Step 5.3a Flat Record Staging ===")
    print(f"Option: {cfg.spec.option} ({cfg.spec.title})")
    for seed in cfg.resolved_seeds:
        train_df = read_stage_csv(split_train_path(cfg, seed))
        holdout_df = read_stage_csv(split_holdout_path(cfg, seed))
        if cfg.spec.interleave_train:
            train_df = interleave_by_ratio(
                train_df,
                n_pos=cfg.resolved_p_block,
                n_neg=cfg.resolved_n_block,
                rng_seed=seed,
            )
            print(f"Seed {seed}: applied train interleave {cfg.resolved_p_block}P/{cfg.resolved_n_block}N")
        write_stage_csv(train_df, staged_flat_train_path(cfg, seed))
        write_stage_csv(holdout_df, staged_flat_holdout_path(cfg, seed))
        print(f"Seed {seed}: staged train={len(train_df)}, holdout={len(holdout_df)}")


if __name__ == "__main__":
    main()
