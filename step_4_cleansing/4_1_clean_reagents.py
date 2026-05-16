"""
Step 4.1 - Reagent cleanup.

Runs the original notebook substeps for:
    - initial row filters and light cleanup
    - metal normalization and metal amount cleanup
    - linker cleanup and linker amount filtering

Default positive path:
    data/mof_extraction.csv -> data/mof_extraction_1_2_3.csv

Branch options:
    positive        notebook cells 0 + 2 + 4
    negative-basic  notebook cells 0 + 2
    negative-plans  notebook cells 0 + 2 + 3
"""
from __future__ import annotations

from utils import available_branches_for_group, parse_and_run_group


if __name__ == "__main__":
    parse_and_run_group(
        group_key="4_1",
        description="Step 4.1 - reagent cleanup",
        branches=available_branches_for_group("4_1"),
        default_branch="positive",
    )
