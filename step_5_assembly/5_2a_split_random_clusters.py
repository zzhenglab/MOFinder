"""Step 5.2a: cluster holdout split using input-order clusters.

Used by options:
    a  random split
    c  year-wise without interleave
"""
from __future__ import annotations

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    prepared_csv_path,
    prepared_stats_path,
    print_config,
    read_json,
    read_stage_csv,
    split_holdout_path,
    split_stats_path,
    split_train_path,
    write_json,
    write_stage_csv,
)
from utils.common import cluster_holdout_split, configure_utf8_stdio, count_labels


def main() -> None:
    args = build_parser(default_option="a").parse_args()
    cfg = config_from_args(args)
    if cfg.spec.sort_clusters:
        raise SystemExit(f"Option {cfg.spec.option} uses sorted clusters; run 5_2b_split_sorted_clusters.py.")
    if args.dry_run:
        print_config(cfg)
        print("Stage:           5.2a input-order cluster split")
        missing = missing_paths([prepared_csv_path(cfg)])
        if missing:
            print("Missing intermediates:")
            for path in missing:
                print(f"  - {path}")
        return

    configure_utf8_stdio()
    filtered_df = read_stage_csv(prepared_csv_path(cfg))
    stats = read_json(prepared_stats_path(cfg)) if prepared_stats_path(cfg).exists() else {}

    print("=== Step 5.2a Cluster Holdout Split ===")
    print(f"Option: {cfg.spec.option} ({cfg.spec.title})")
    print("Cluster order: input order")
    if stats:
        print(f"Prepared rows: {stats.get('n_after_filter')}")
        print(f"Coarse unique clusters: {stats.get('n_clusters')}")

    for seed in cfg.resolved_seeds:
        train_df, holdout_df, n_holdout_clusters = cluster_holdout_split(
            filtered_df,
            seed=seed,
            holdout_frac=cfg.resolved_holdout_frac,
            sort_clusters=False,
            cap_at_n_clusters=cfg.spec.cap_holdout_clusters,
            holdout_cluster_frac=cfg.spec.holdout_cluster_frac,
            target_mode=cfg.spec.holdout_target_mode,
            search_trials=cfg.spec.holdout_search_trials,
        )
        write_stage_csv(train_df, split_train_path(cfg, seed))
        write_stage_csv(holdout_df, split_holdout_path(cfg, seed))
        train_pos, train_neg = count_labels(train_df)
        holdout_pos, holdout_neg = count_labels(holdout_df)
        write_json(
            split_stats_path(cfg, seed),
            {
                "seed": seed,
                "n_holdout_clusters": n_holdout_clusters,
                "holdout_frac": cfg.resolved_holdout_frac,
                "train_rows": len(train_df),
                "holdout_rows": len(holdout_df),
                "train_P": train_pos,
                "train_N": train_neg,
                "holdout_P": holdout_pos,
                "holdout_N": holdout_neg,
            },
        )
        print(
            f"Seed {seed}: holdout_clusters={n_holdout_clusters}, "
            f"train={len(train_df)} (P={train_pos}, N={train_neg}), "
            f"holdout={len(holdout_df)} (P={holdout_pos}, N={holdout_neg})"
        )


if __name__ == "__main__":
    main()
