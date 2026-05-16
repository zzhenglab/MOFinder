"""
Step 4.4 - Cleaned-data analysis and metal-linker reports.

Default positive path:
    reads the latest data/mof_extraction*.csv, preferring
    data/mof_extraction_1_2_3_4_5_6.csv

Outputs:
    data/metal_linker_pairs_report_all.csv
    data/metal_linker_pairs_report_all_missing.csv

This analysis stage exists only in the positive notebook.
"""
from __future__ import annotations

from utils import available_branches_for_group, parse_and_run_group


if __name__ == "__main__":
    parse_and_run_group(
        group_key="4_4",
        description="Step 4.4 - cleaned-data analysis and metal-linker reports",
        branches=available_branches_for_group("4_4"),
        default_branch="positive",
    )
