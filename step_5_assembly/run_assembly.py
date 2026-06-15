"""Run Step 5 assembly end to end.

Default option is ``d``, matching the notebook's best strategy:
year-wise F/G/H/I splits plus 11/17 P/N interleave and duplicate-solvent
avoidance.

Input note:
  Step 5 expects Step 4.3 output, usually ``mof_extraction_1_2_3_4_5.csv``
  or ``mof_extraction_1_2_3_4_5_6.csv``. Do not feed ``_1_2_3_4.csv``
  directly: it does not yet contain ``metal_concentration`` or ``M_L_ratio``.

Output note:
  Step 5 writes classifier artifacts such as ``mof_cls_train.jsonl``,
  ``mof_cls_holdout.jsonl``, and ``mof_cls_class_map.json``. The ``_5_6.csv``
  file is produced by Step 4.3, not by Step 5.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from utils.cls_dataset import (
    build_parser,
    config_from_args,
    missing_paths,
    print_config,
    required_input_paths,
    work_dir,
)

SCRIPT_DIR = Path(__file__).resolve().parent

def forwarded_args(cfg) -> list[str]:
    args = [
        "--option", cfg.spec.option,
        "--positive-csv", str(cfg.pos_path),
        "--negative-csv", str(cfg.neg_path),
        "--full-metadata", str(cfg.full_metadata_path),
        "--out-dir", str(cfg.resolved_out_dir),
        "--holdout-frac", str(cfg.resolved_holdout_frac),
        "--p-block", str(cfg.resolved_p_block),
        "--n-block", str(cfg.resolved_n_block),
        "--seeds", *[str(seed) for seed in cfg.resolved_seeds],
        "--split-names", *cfg.resolved_split_names,
    ]
    return args


def run_script(script_name: str, args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    print("\n" + "=" * 80, flush=True)
    print("Running", " ".join(cmd), flush=True)
    print("=" * 80, flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    args = build_parser(default_option="d", description="Run Step 5 PN dataset assembly end to end.").parse_args()
    cfg = config_from_args(args)

    if args.dry_run:
        print_config(cfg)
        print("Pipeline:")
        print("  5.1  prepare filtered+clustered rows")
        print(f"  5.2{'b' if cfg.spec.sort_clusters else 'a'}  cluster holdout split")
        print(f"  5.3{'b' if cfg.spec.use_year_splits else 'a'}  stage records")
        print("  5.4  write JSONL")
        print(f"Work dir: {work_dir(cfg)}")
        missing = missing_paths(required_input_paths(cfg))
        if missing:
            print("Missing inputs:")
            for path in missing:
                print(f"  - {path}")
        return

    shared_args = forwarded_args(cfg)
    run_script("5_1_prepare_cls_rows.py", shared_args)
    run_script("5_2b_split_sorted_clusters.py" if cfg.spec.sort_clusters else "5_2a_split_random_clusters.py", shared_args)
    run_script("5_3b_stage_year_records.py" if cfg.spec.use_year_splits else "5_3a_stage_flat_records.py", shared_args)
    run_script("5_4_write_cls_jsonl.py", shared_args)


if __name__ == "__main__":
    main()
