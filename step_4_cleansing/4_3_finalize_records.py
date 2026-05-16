"""
Step 4.3 - Final record fields.

Runs the original notebook substeps for:
    - metal connectivity classification
    - MOF description construction

Default positive path:
    data/mof_extraction_1_2_3_4_5.csv -> data/mof_extraction_1_2_3_4_5_6.csv

Branch options:
    positive        notebook cells 7 + 8
    negative-plans  notebook cells 6 + 7

The negative-basic notebook stops after reagent cleanup, so it has no 4.3 branch.
"""
from __future__ import annotations

from utils import available_branches_for_group, parse_and_run_group


if __name__ == "__main__":
    parse_and_run_group(
        group_key="4_3",
        description="Step 4.3 - final record fields",
        branches=available_branches_for_group("4_3"),
        default_branch="positive",
    )
