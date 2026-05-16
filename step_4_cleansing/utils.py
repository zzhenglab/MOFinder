from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"


@dataclass(frozen=True)
class StepSpec:
    key: str
    title: str
    notebook_name: str
    cell_index: int
    input_name: str | None
    output_name: str | None
    notes: str = ""

    @property
    def notebook_path(self) -> Path:
        return SCRIPT_DIR / self.notebook_name

    def input_path(self, data_dir: Path) -> Path | None:
        return data_dir / self.input_name if self.input_name else None

    def output_path(self, data_dir: Path) -> Path | None:
        return data_dir / self.output_name if self.output_name else None


POSITIVE_NOTEBOOK = "step 4 clean data.ipynb"
NEGATIVE_BASIC_NOTEBOOK = "step 4 clean data for negative data.ipynb"
NEGATIVE_PLANS_NOTEBOOK = "step 4 b clean data for negative data plans.ipynb"


STEPS: dict[str, dict[str, StepSpec]] = {
    "4_1": {
        "positive": StepSpec(
            key="4_1",
            title="Initial filters and light cleanup",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=0,
            input_name="mof_extraction.csv",
            output_name="mof_extraction_1.csv",
            notes=(
                "Positive route: keeps the notebook's linker synonym merge, "
                "broad temperature text filter, and 2x-mean pore outlier rule."
            ),
        ),
        "negative-basic": StepSpec(
            key="4_1",
            title="Initial filters and light cleanup",
            notebook_name=NEGATIVE_BASIC_NOTEBOOK,
            cell_index=0,
            input_name="mof_extraction_failures_enum.csv",
            output_name="mof_extraction_failures_enum_1.csv",
            notes=(
                "Original negative-data route: no initial linker synonym merge; "
                "keeps the broad microwave/evaporation/slow temperature filter."
            ),
        ),
        "negative-plans": StepSpec(
            key="4_1",
            title="Initial filters and light cleanup",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=0,
            input_name="mof_extraction_failures_enum.csv",
            output_name="mof_extraction_failures_enum_1.csv",
            notes=(
                "Negative-plan route: preserves the notebook's reset-index guard, "
                "initial linker synonym merge, tighter slow-evaporation/slow-diffusion "
                "temperature filter, and q99 pore outlier guard."
            ),
        ),
    },
    "4_2": {
        "positive": StepSpec(
            key="4_2",
            title="Metal normalization and metal amount cleanup",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=2,
            input_name="mof_extraction_1.csv",
            output_name="mof_extraction_1_2.csv",
            notes="Full positive metal normalization cell.",
        ),
        "negative-basic": StepSpec(
            key="4_2",
            title="Metal normalization and metal amount cleanup",
            notebook_name=NEGATIVE_BASIC_NOTEBOOK,
            cell_index=2,
            input_name="mof_extraction_failures_enum_1.csv",
            output_name="mof_extraction_failures_enum_1_2.csv",
            notes="Original shorter negative metal normalization cell.",
        ),
        "negative-plans": StepSpec(
            key="4_2",
            title="Metal normalization and metal amount cleanup",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=2,
            input_name="mof_extraction_failures_enum_1.csv",
            output_name="mof_extraction_failures_enum_1_2.csv",
            notes="Full negative-plan metal normalization cell.",
        ),
    },
    "4_3": {
        "positive": StepSpec(
            key="4_3",
            title="Linker cleanup and linker amount unit filtering",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=4,
            input_name="mof_extraction_1_2.csv",
            output_name="mof_extraction_1_2_3.csv",
            notes='Uses "linker and mw.csv" from data/ when present, as in the notebook.',
        ),
        "negative-plans": StepSpec(
            key="4_3",
            title="Linker cleanup and linker amount unit filtering",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=3,
            input_name="mof_extraction_failures_enum_1_2.csv",
            output_name="mof_extraction_failures_enum_1_2_3.csv",
            notes='Uses "linker and mw.csv" from data/ when present, as in the notebook.',
        ),
    },
    "4_4": {
        "positive": StepSpec(
            key="4_4",
            title="Solvent canonicalization and volume inference",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=5,
            input_name="mof_extraction_1_2_3.csv",
            output_name="mof_extraction_1_2_3_4.csv",
            notes="Preserves the solvent synonym maps, density table, and parsing order.",
        ),
        "negative-plans": StepSpec(
            key="4_4",
            title="Solvent canonicalization and volume inference",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=4,
            input_name="mof_extraction_failures_enum_1_2_3.csv",
            output_name="mof_extraction_failures_enum_1_2_3_4.csv",
            notes="Preserves the solvent synonym maps, density table, and parsing order.",
        ),
    },
    "4_5": {
        "positive": StepSpec(
            key="4_5",
            title="M:L ratio and metal concentration",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=6,
            input_name="mof_extraction_1_2_3_4.csv",
            output_name="mof_extraction_1_2_3_4_5.csv",
            notes="Preserves the mmol-only ratio logic and concentration insertion point.",
        ),
        "negative-plans": StepSpec(
            key="4_5",
            title="M:L ratio and metal concentration",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=5,
            input_name="mof_extraction_failures_enum_1_2_3_4.csv",
            output_name="mof_extraction_failures_enum_1_2_3_4_5.csv",
            notes="Preserves the mmol-only ratio logic and concentration insertion point.",
        ),
    },
    "4_6": {
        "positive": StepSpec(
            key="4_6",
            title="Metal connectivity classification",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=7,
            input_name="mof_extraction_1_2_3_4_5.csv",
            output_name="mof_extraction_1_2_3_4_5.csv",
            notes="In-place step that inserts metal_cluster_connectivity_classified.",
        ),
        "negative-plans": StepSpec(
            key="4_6",
            title="Metal connectivity classification",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=6,
            input_name="mof_extraction_failures_enum_1_2_3_4_5.csv",
            output_name="mof_extraction_failures_enum_1_2_3_4_5.csv",
            notes="In-place step that inserts metal_cluster_connectivity_classified.",
        ),
    },
    "4_7": {
        "positive": StepSpec(
            key="4_7",
            title="MOF description construction",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=8,
            input_name="mof_extraction_1_2_3_4_5.csv",
            output_name="mof_extraction_1_2_3_4_5_6.csv",
            notes="Inserts mof_description before mof_name.",
        ),
        "negative-plans": StepSpec(
            key="4_7",
            title="MOF description construction",
            notebook_name=NEGATIVE_PLANS_NOTEBOOK,
            cell_index=7,
            input_name="mof_extraction_failures_enum_1_2_3_4_5.csv",
            output_name="mof_extraction_failures_enum_1_2_3_4_5_6.csv",
            notes="Inserts mof_description before mof_name.",
        ),
    },
    "4_8": {
        "positive": StepSpec(
            key="4_8",
            title="Cleaned-data analysis and metal-linker reports",
            notebook_name=POSITIVE_NOTEBOOK,
            cell_index=9,
            input_name="mof_extraction_1_2_3_4_5_6.csv",
            output_name="metal_linker_pairs_report_all.csv",
            notes=(
                "Analysis cell auto-selects the latest mof_extraction*.csv in data/ "
                "and writes metal_linker_pairs_report_all.csv plus missing-pair CSV."
            ),
        ),
    },
}


GROUP_TITLES = {
    "4_1": "Reagent cleanup: initial filters, metals, and linkers",
    "4_2": "Condition cleanup: solvents, ratios, and concentration",
    "4_3": "Final fields: connectivity labels and MOF descriptions",
    "4_4": "Cleaned-data analysis and metal-linker reports",
}


GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "4_1": {
        "positive": ("4_1", "4_2", "4_3"),
        "negative-basic": ("4_1", "4_2"),
        "negative-plans": ("4_1", "4_2", "4_3"),
    },
    "4_2": {
        "positive": ("4_4", "4_5"),
        "negative-plans": ("4_4", "4_5"),
    },
    "4_3": {
        "positive": ("4_6", "4_7"),
        "negative-plans": ("4_6", "4_7"),
    },
    "4_4": {
        "positive": ("4_8",),
    },
}


BRANCH_GROUPS = {
    "positive": ("4_1", "4_2", "4_3"),
    "negative-basic": ("4_1",),
    "negative-plans": ("4_1", "4_2", "4_3"),
}


@contextmanager
def pushd(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def resolve_data_dir(path_str: str | None = None) -> Path:
    path = Path(path_str).expanduser() if path_str else DATA_DIR
    return path.resolve()


def get_spec(step_key: str, branch: str) -> StepSpec:
    try:
        return STEPS[step_key][branch]
    except KeyError as exc:
        choices = ", ".join(sorted(STEPS.get(step_key, {}).keys()))
        raise ValueError(
            f"{step_key} does not have branch {branch!r}. Available branches: {choices}"
        ) from exc


def print_spec(spec: StepSpec, data_dir: Path) -> None:
    print(f"  - {spec.title}")
    print(f"    notebook: {spec.notebook_name} / cell {spec.cell_index}")
    if spec.input_name:
        print(f"    input:    {spec.input_path(data_dir)}")
    if spec.output_name:
        print(f"    output:   {spec.output_path(data_dir)}")
    if spec.notes:
        print(f"    notes:    {spec.notes}")


def _load_cell_source(spec: StepSpec) -> str:
    notebook_path = spec.notebook_path
    if notebook_path.exists():
        notebook_text = notebook_path.read_text(encoding="utf-8")
    else:
        git_path = f"step_4_cleansing/{spec.notebook_name}"
        try:
            notebook_text = subprocess.check_output(
                ["git", "show", f"HEAD:{git_path}"],
                cwd=REPO_ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Notebook not found on disk or in git HEAD: {notebook_path}"
            ) from exc

    notebook = json.loads(notebook_text)
    cells = notebook.get("cells", [])
    if spec.cell_index >= len(cells):
        raise IndexError(
            f"{spec.notebook_name} has no cell {spec.cell_index}; total cells: {len(cells)}"
        )
    cell = cells[spec.cell_index]
    if cell.get("cell_type") != "code":
        raise TypeError(f"{spec.notebook_name} cell {spec.cell_index} is not a code cell")
    return _patch_source_for_script_execution(spec, "".join(cell.get("source", [])))


def _patch_source_for_script_execution(spec: StepSpec, source: str) -> str:
    if spec.key != "4_4":
        return source
    return source.replace(
        'a = (abbr or "").strip()',
        'a = ("" if not is_filled(abbr) else str(abbr).strip())',
    ).replace(
        'a = (abbr or "").strip().upper()',
        'a = ("" if not is_filled(abbr) else str(abbr).strip().upper())',
    )


def _configure_matplotlib(keep_plots: bool) -> None:
    if keep_plots:
        return
    try:
        import matplotlib

        matplotlib.use("Agg")
    except Exception:
        pass


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_spec(
    spec: StepSpec,
    data_dir: Path,
    *,
    dry_run: bool = False,
    keep_plots: bool = False,
) -> None:
    data_dir = data_dir.resolve()
    print_spec(spec, data_dir)
    if dry_run:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    input_path = spec.input_path(data_dir)
    if input_path and not input_path.exists():
        raise FileNotFoundError(f"Expected input for {spec.key} not found: {input_path}")

    source = _load_cell_source(spec)
    _configure_stdio()
    _configure_matplotlib(keep_plots)

    namespace = {
        "__name__": "__step4_notebook_cell__",
        "__file__": str(spec.notebook_path),
    }
    with pushd(data_dir):
        exec(compile(source, str(spec.notebook_path), "exec"), namespace)


def run_group(
    group_key: str,
    branch: str,
    data_dir: Path,
    *,
    dry_run: bool = False,
    keep_plots: bool = False,
) -> None:
    if group_key not in GROUPS:
        choices = ", ".join(sorted(GROUPS))
        raise ValueError(f"Unknown group {group_key!r}. Available groups: {choices}")
    if branch not in GROUPS[group_key]:
        choices = ", ".join(sorted(GROUPS[group_key]))
        raise ValueError(
            f"{group_key} does not have branch {branch!r}. Available branches: {choices}"
        )

    print(f"{group_key}: {GROUP_TITLES[group_key]}")
    for step_key in GROUPS[group_key][branch]:
        run_spec(get_spec(step_key, branch), data_dir, dry_run=dry_run, keep_plots=keep_plots)


def run_branch_groups(
    branch: str,
    data_dir: Path,
    *,
    include_analysis: bool = False,
    dry_run: bool = False,
    keep_plots: bool = False,
) -> None:
    if branch not in BRANCH_GROUPS:
        choices = ", ".join(sorted(BRANCH_GROUPS))
        raise ValueError(f"Unknown branch {branch!r}. Available branches: {choices}")

    group_keys = list(BRANCH_GROUPS[branch])
    if include_analysis:
        if branch != "positive":
            raise ValueError("--include-analysis is only defined for the positive branch")
        group_keys.append("4_4")

    for group_key in group_keys:
        run_group(group_key, branch, data_dir, dry_run=dry_run, keep_plots=keep_plots)


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    branches: Sequence[str],
    default_branch: str,
) -> None:
    parser.add_argument(
        "--branch",
        choices=branches,
        default=default_branch,
        help=f"Notebook branch to run (default: {default_branch})",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help=f"Directory that contains the step-4 CSV chain (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved notebook cell and data paths without executing.",
    )
    parser.add_argument(
        "--keep-plots",
        action="store_true",
        help="Use the interactive matplotlib backend instead of the noninteractive Agg backend.",
    )


def parse_and_run_group(
    *,
    group_key: str,
    description: str,
    branches: Sequence[str],
    default_branch: str,
) -> None:
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_args(parser, branches=branches, default_branch=default_branch)
    args = parser.parse_args()
    run_group(
        group_key,
        args.branch,
        resolve_data_dir(args.data_dir),
        dry_run=args.dry_run,
        keep_plots=args.keep_plots,
    )


def available_branches_for_group(group_key: str) -> tuple[str, ...]:
    return tuple(GROUPS[group_key].keys())


def format_group_list(group_keys: Iterable[str], branch: str) -> str:
    rows = []
    for group_key in group_keys:
        n_cells = len(GROUPS[group_key][branch])
        rows.append(f"{group_key}: {GROUP_TITLES[group_key]} ({n_cells} notebook cells)")
    return "\n".join(rows)
