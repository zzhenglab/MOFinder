from __future__ import annotations

import argparse
import runpy
from pathlib import Path

from utils import branch_paths, configure_utf8_stdio

SCRIPT_DIR = Path(__file__).resolve().parent
BRANCH = 'positive'


def _step_4_2_run():
    return runpy.run_path(str(SCRIPT_DIR / "4_2_linkers_and_solvents.py"))["run"]


def run(input_path: str | Path | None = None, output_3: str | Path | None = None, output_4: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    paths = branch_paths(BRANCH)
    s2 = Path(input_path) if input_path else paths["s2"]
    s3 = Path(output_3) if output_3 else paths["s3"]
    s4 = Path(output_4) if output_4 else paths["s4"]
    return _step_4_2_run()(BRANCH, s2, s3, s4)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Step 4.2a: positive-branch linker and solvent cleanup.')
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--output-3", default=None)
    parser.add_argument("--output-4", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.input_path, args.output_3, args.output_4)


if __name__ == "__main__":
    main()
