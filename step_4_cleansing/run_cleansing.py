"""Run Step 4 cleansing scripts in order.

CSV suffix flow for full branches:
  raw -> _1 -> _1_2 -> _1_2_3 -> _1_2_3_4 -> _1_2_3_4_5 -> _1_2_3_4_5_6

For reuse from an existing ``_1_2_3.csv``:
  - Step 4.2 solvent cleanup writes ``_1_2_3_4.csv``.
  - Step 4.3 derived features writes ``_1_2_3_4_5.csv`` with
    ``metal_concentration`` and ``M_L_ratio``.
  - Step 4.3 then writes ``_1_2_3_4_5_6.csv`` with ``mof_description``.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from utils import ALL_BRANCHES, DATA_DIR, branch_paths, configure_utf8_stdio

SCRIPT_DIR = Path(__file__).resolve().parent


def call_step(script_name: str, args: list[str], *, dry_run: bool = False) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    print("\n" + "=" * 80, flush=True)
    print("Running", " ".join(cmd), flush=True)
    print("=" * 80, flush=True)
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def run(branch: str, data_dir: str | Path | None = None, *, dry_run: bool = False) -> None:
    configure_utf8_stdio()
    paths = branch_paths(branch, data_dir)

    # 4.1: raw -> _1 and _1_2.
    call_step(
        "4_1_filter_and_metals.py",
        [
            "--branch", branch,
            "--input", str(paths["raw"]),
            "--output-1", str(paths["s1"]),
            "--output-2", str(paths["s2"]),
        ],
        dry_run=dry_run,
    )
    if branch == "negative-basic":
        print("negative-basic branch stops after Step 4.1 and writes the _2 output.")
        return
    if branch == "positive":
        step_4_2_script = "4_2a_positive.py"
    elif branch == "negative-plans":
        step_4_2_script = "4_2b_negative_plans.py"
    else:
        raise ValueError(f"Step 4.2 is not defined for branch: {branch}")

    # 4.2: _1_2 -> _1_2_3 and _1_2_3_4.
    call_step(
        step_4_2_script,
        [
            "--input", str(paths["s2"]),
            "--output-3", str(paths["s3"]),
            "--output-4", str(paths["s4"]),
        ],
        dry_run=dry_run,
    )
    # 4.3: _1_2_3_4 -> _1_2_3_4_5 and _1_2_3_4_5_6.
    call_step(
        "4_3_derived_features.py",
        [
            "--branch", branch,
            "--input", str(paths["s4"]),
            "--output-5", str(paths["s5"]),
            "--output-6", str(paths["s6"]),
        ],
        dry_run=dry_run,
    )
    # 4.4: _1_2_3_4_5_6 -> printed report.
    call_step("4_4_report.py", ["--branch", branch, "--input", str(paths["s6"])], dry_run=dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Step 4 cleansing end to end.")
    parser.add_argument("--branch", choices=sorted(ALL_BRANCHES), default="positive")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Directory containing the Step-4 CSV chain.")
    parser.add_argument("--dry-run", action="store_true", help="Print the substep commands without executing them.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
