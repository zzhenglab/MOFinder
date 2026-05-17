from __future__ import annotations

import argparse
from pathlib import Path

from utils.common import ALL_BRANCHES, branch_paths, configure_utf8_stdio
from utils.initial_cleaning import clean_initial_dataset
from utils.metal_basic import normalize_metals_basic
from utils.metal_full import normalize_metals_full


def run(branch: str, input_path: str | Path | None = None, output_1: str | Path | None = None, output_2: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    paths = branch_paths(branch)
    raw = Path(input_path) if input_path else paths["raw"]
    s1 = Path(output_1) if output_1 else paths["s1"]
    s2 = Path(output_2) if output_2 else paths["s2"]

    if branch == "negative-basic":
        clean_initial_dataset(raw, s1, apply_linker_synonym_merge=False, reset_after_filters=False, strict_slow_temperature_filter=False)
        return normalize_metals_basic(s1, s2)

    clean_initial_dataset(
        raw,
        s1,
        apply_linker_synonym_merge=True,
        reset_after_filters=(branch == "negative-plans"),
        strict_slow_temperature_filter=(branch == "negative-plans"),
    )
    return normalize_metals_full(s1, s2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 4.1: initial row filtering plus metal precursor cleaning.")
    parser.add_argument("--branch", choices=sorted(ALL_BRANCHES), default="positive")
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--output-1", default=None, help="CSV written after the initial cleaning stage.")
    parser.add_argument("--output-2", default=None, help="CSV written after the metal cleaning stage.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.input_path, args.output_1, args.output_2)


if __name__ == "__main__":
    main()
