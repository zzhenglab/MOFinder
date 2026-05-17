from __future__ import annotations

import argparse
from pathlib import Path

from utils.common import FULL_BRANCHES, branch_paths, configure_utf8_stdio
from utils.reporting import run_analysis_report


def run(branch: str, input_path: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    if branch not in FULL_BRANCHES:
        raise ValueError("Step 4.4 is only defined for positive and negative-plans branches; negative-basic stops after Step 4.1.")
    paths = branch_paths(branch)
    dataset = Path(input_path) if input_path else paths["s6"]
    return run_analysis_report(dataset)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 4.4: final summary/report tables and metal-linker pair CSV.")
    parser.add_argument("--branch", choices=sorted(FULL_BRANCHES), default="positive")
    parser.add_argument("--input", dest="input_path", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.input_path)


if __name__ == "__main__":
    main()
