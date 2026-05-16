"""
Run one complete cleansing branch.

Branches kept from the notebooks:
    positive        data/mof_extraction.csv -> data/mof_extraction_1_2_3_4_5_6.csv
    negative-basic  data/mof_extraction_failures_enum.csv -> data/mof_extraction_failures_enum_1_2.csv
    negative-plans  data/mof_extraction_failures_enum.csv -> data/mof_extraction_failures_enum_1_2_3_4_5_6.csv

The numbered scripts 4_1 ... 4_4 run merged stages. Each stage still runs the
original notebook cells in order.
"""
from __future__ import annotations

import argparse

from utils import BRANCH_GROUPS, format_group_list, resolve_data_dir, run_branch_groups


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run a complete cleansing branch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Positive branch:\n"
            f"{format_group_list(BRANCH_GROUPS['positive'], 'positive')}\n\n"
            "Negative-basic branch:\n"
            f"{format_group_list(BRANCH_GROUPS['negative-basic'], 'negative-basic')}\n\n"
            "Negative-plans branch:\n"
            f"{format_group_list(BRANCH_GROUPS['negative-plans'], 'negative-plans')}"
        ),
    )
    parser.add_argument(
        "--branch",
        choices=tuple(BRANCH_GROUPS),
        default="positive",
        help="Pipeline branch to run (default: positive)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory that contains the step-4 CSV chain (default: repo data/)",
    )
    parser.add_argument(
        "--include-analysis",
        action="store_true",
        help="After the positive branch, run 4_4 analysis/report generation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print each substep's resolved paths without executing.",
    )
    parser.add_argument(
        "--keep-plots",
        action="store_true",
        help="Use the interactive matplotlib backend instead of noninteractive Agg.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_branch_groups(
        args.branch,
        resolve_data_dir(args.data_dir),
        include_analysis=args.include_analysis,
        dry_run=args.dry_run,
        keep_plots=args.keep_plots,
    )
