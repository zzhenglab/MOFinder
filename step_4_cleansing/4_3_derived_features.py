from __future__ import annotations

import argparse
from pathlib import Path

from utils.common import FULL_BRANCHES, branch_paths, configure_utf8_stdio
from utils.derived_features import build_mof_description, classify_connectivity, compute_ratio_and_concentration


def run(branch: str, input_path: str | Path | None = None, output_5: str | Path | None = None, output_6: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    if branch not in FULL_BRANCHES:
        raise ValueError("Step 4.3 is only defined for positive and negative-plans branches; negative-basic stops after Step 4.1.")
    paths = branch_paths(branch)
    s4 = Path(input_path) if input_path else paths["s4"]
    s5 = Path(output_5) if output_5 else paths["s5"]
    s6 = Path(output_6) if output_6 else paths["s6"]
    compute_ratio_and_concentration(s4, s5)
    classify_connectivity(s5, s5)
    return build_mof_description(s5, s6)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 4.3: ratio, concentration, connectivity class, and MOF description.")
    parser.add_argument("--branch", choices=sorted(FULL_BRANCHES), default="positive")
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--output-5", default=None)
    parser.add_argument("--output-6", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.input_path, args.output_5, args.output_6)


if __name__ == "__main__":
    main()
