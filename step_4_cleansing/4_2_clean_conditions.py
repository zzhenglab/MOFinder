"""
Step 4.2 - Condition cleanup.

Runs the original notebook substeps for:
    - solvent canonicalization and volume inference
    - M:L ratio and metal concentration

Default positive path:
    data/mof_extraction_1_2_3.csv -> data/mof_extraction_1_2_3_4_5.csv

Branch options:
    positive        notebook cells 5 + 6
    negative-plans  notebook cells 4 + 5

The negative-basic notebook stops after reagent cleanup, so it has no 4.2 branch.
"""
from __future__ import annotations

from utils import available_branches_for_group, parse_and_run_group


if __name__ == "__main__":
    parse_and_run_group(
        group_key="4_2",
        description="Step 4.2 - condition cleanup",
        branches=available_branches_for_group("4_2"),
        default_branch="positive",
    )
