"""Helpers for Step 5 PN classifier dataset assembly."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from utils.common import (
    DATA_DIR,
    FULL_METADATA_XLSX,
    MULTI_LINKER_REQUIRED_COLS,
    NEGATIVE_CSV,
    POSITIVE_CSV,
    SINGLE_LINKER_REQUIRED_COLS,
    missing_paths,
    resolve_path,
)


@dataclass(frozen=True)
class OptionSpec:
    option: str
    title: str
    notebook_branch: str
    out_dir: Path
    seeds: tuple[int, ...]
    holdout_frac: float

    required_cols: tuple[str, ...]
    require_any_linker: bool
    family_mode: str
    sort_clusters: bool
    cap_holdout_clusters: bool

    multi_linker: bool
    include_secondary_solvent: bool
    dedupe_secondary_solvent: bool
    jsonl_encoding: str
    class_map_encoding: str
    class_map_ensure_ascii: bool

    use_year_splits: bool = False
    split_names: tuple[str, ...] = ("F", "G", "H", "I")
    keep_case_doi: bool = False
    tolerate_missing_doi_column: bool = False

    interleave_train: bool = False
    interleave_train_splits: bool = False
    interleave_holdout_splits: bool = False
    p_block: int = 11
    n_block: int = 17

    layout: str = "flat"
    write_train_all: bool = False
    write_holdout_all: bool = False
    write_holdout_year_all: bool = False
    print_sample_records: bool = False


@dataclass
class RunConfig:
    spec: OptionSpec
    pos_path: Path = POSITIVE_CSV
    neg_path: Path = NEGATIVE_CSV
    full_metadata_path: Path = FULL_METADATA_XLSX
    out_dir: Path | None = None
    seeds: tuple[int, ...] | None = None
    holdout_frac: float | None = None
    split_names: tuple[str, ...] | None = None
    p_block: int | None = None
    n_block: int | None = None

    @property
    def resolved_out_dir(self) -> Path:
        return self.out_dir if self.out_dir is not None else self.spec.out_dir

    @property
    def resolved_seeds(self) -> tuple[int, ...]:
        return self.seeds if self.seeds is not None else self.spec.seeds

    @property
    def resolved_holdout_frac(self) -> float:
        return self.holdout_frac if self.holdout_frac is not None else self.spec.holdout_frac

    @property
    def resolved_split_names(self) -> tuple[str, ...]:
        return self.split_names if self.split_names is not None else self.spec.split_names

    @property
    def resolved_p_block(self) -> int:
        return self.p_block if self.p_block is not None else self.spec.p_block

    @property
    def resolved_n_block(self) -> int:
        return self.n_block if self.n_block is not None else self.spec.n_block


OPTION_SPECS: dict[str, OptionSpec] = {
    "a": OptionSpec(
        option="a",
        title="random cluster holdout",
        notebook_branch="Ablation 1: random split",
        out_dir=DATA_DIR / "out",
        seeds=(42,),
        holdout_frac=0.10,
        required_cols=tuple(SINGLE_LINKER_REQUIRED_COLS),
        require_any_linker=False,
        family_mode="full",
        sort_clusters=False,
        cap_holdout_clusters=False,
        multi_linker=False,
        include_secondary_solvent=True,
        dedupe_secondary_solvent=False,
        jsonl_encoding="utf-8",
        class_map_encoding="utf-8",
        class_map_ensure_ascii=False,
        layout="flat",
        print_sample_records=True,
    ),
    "b": OptionSpec(
        option="b",
        title="random holdout plus 11/17 train interleave",
        notebook_branch="Ablation 2: 17/11 interleave + Random Pub Year",
        out_dir=DATA_DIR / "out2",
        seeds=(66,),
        holdout_frac=0.10,
        required_cols=tuple(MULTI_LINKER_REQUIRED_COLS),
        require_any_linker=True,
        family_mode="simple",
        sort_clusters=True,
        cap_holdout_clusters=False,
        multi_linker=True,
        include_secondary_solvent=True,
        dedupe_secondary_solvent=False,
        jsonl_encoding="utf-8",
        class_map_encoding="utf-8",
        class_map_ensure_ascii=True,
        interleave_train=True,
        layout="seed_flat",
    ),
    "c": OptionSpec(
        option="c",
        title="year-wise train/holdout files without interleave",
        notebook_branch="Ablation 3: Year-wise without 17/11",
        out_dir=DATA_DIR / "out3",
        seeds=(42,),
        holdout_frac=0.10,
        required_cols=tuple(MULTI_LINKER_REQUIRED_COLS),
        require_any_linker=True,
        family_mode="year",
        sort_clusters=False,
        cap_holdout_clusters=False,
        multi_linker=True,
        include_secondary_solvent=False,
        dedupe_secondary_solvent=False,
        jsonl_encoding="utf-8",
        class_map_encoding="utf-8",
        class_map_ensure_ascii=True,
        use_year_splits=True,
        keep_case_doi=False,
        tolerate_missing_doi_column=False,
        layout="year",
        write_holdout_year_all=True,
    ),
    "d": OptionSpec(
        option="d",
        title="year-wise 11/17 interleave with duplicate-solvent avoidance",
        notebook_branch="Best Re-ordering Strategy: Year-wise + 17/11 interleave, with avoiding duplicate solvent",
        out_dir=DATA_DIR / "out_seed_year_interleave",
        seeds=(66,),
        holdout_frac=0.10,
        required_cols=tuple(MULTI_LINKER_REQUIRED_COLS),
        require_any_linker=True,
        family_mode="full",
        sort_clusters=True,
        cap_holdout_clusters=True,
        multi_linker=True,
        include_secondary_solvent=True,
        dedupe_secondary_solvent=True,
        jsonl_encoding="utf-8-sig",
        class_map_encoding="utf-8-sig",
        class_map_ensure_ascii=False,
        use_year_splits=True,
        keep_case_doi=True,
        tolerate_missing_doi_column=True,
        interleave_train_splits=True,
        interleave_holdout_splits=True,
        layout="year",
        write_train_all=True,
        write_holdout_all=True,
    ),
}


def get_option_spec(option: str) -> OptionSpec:
    key = option.lower()
    if key not in OPTION_SPECS:
        raise ValueError(f"Unknown Step 5 option: {option}")
    return OPTION_SPECS[key]


def required_input_paths(cfg: RunConfig) -> list[Path]:
    paths = [cfg.pos_path, cfg.neg_path]
    if cfg.spec.use_year_splits:
        paths.append(cfg.full_metadata_path)
    return paths


def work_dir(cfg: RunConfig) -> Path:
    return cfg.resolved_out_dir / "_work"


def prepared_csv_path(cfg: RunConfig) -> Path:
    return work_dir(cfg) / "5_1_filtered_clustered.csv"


def prepared_stats_path(cfg: RunConfig) -> Path:
    return work_dir(cfg) / "5_1_stats.json"


def split_train_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_2_train_split.csv"


def split_holdout_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_2_holdout_split.csv"


def split_stats_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_2_split_stats.json"


def staged_flat_train_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_3_flat_train_records.csv"


def staged_flat_holdout_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_3_flat_holdout_records.csv"


def staged_train_year_path(cfg: RunConfig, seed: int, name: str) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / f"5_3_train_year_{name}.csv"


def staged_holdout_year_path(cfg: RunConfig, seed: int, name: str) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / f"5_3_holdout_year_{name}.csv"


def staged_train_all_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_3_train_all.csv"


def staged_holdout_all_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_3_holdout_all.csv"


def staged_holdout_year_all_path(cfg: RunConfig, seed: int) -> Path:
    return work_dir(cfg) / f"seed_{seed}" / "5_3_holdout_year_all.csv"


def write_stage_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def read_stage_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    if "is_success" in df.columns and df["is_success"].dtype != bool:
        df["is_success"] = df["is_success"].map(
            lambda x: str(x).strip().lower() in {"true", "1", "yes", "p"}
        )
    return df


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_config(cfg: RunConfig) -> None:
    spec = cfg.spec
    print(f"=== Step 5 option {spec.option}: {spec.title} config ===")
    print(f"Notebook branch: {spec.notebook_branch}")
    print(f"Positive CSV:    {cfg.pos_path}")
    print(f"Negative CSV:    {cfg.neg_path}")
    if spec.use_year_splits:
        print(f"Full metadata:   {cfg.full_metadata_path}")
    print(f"Output dir:      {cfg.resolved_out_dir}")
    print(f"SEEDS:           {list(cfg.resolved_seeds)}")
    print(f"HOLDOUT_FRAC:    {cfg.resolved_holdout_frac}")
    if spec.use_year_splits:
        print(f"SPLIT_NAMES:     {list(cfg.resolved_split_names)}")
    if spec.interleave_train or spec.interleave_train_splits or spec.interleave_holdout_splits:
        print(f"P_BLOCK:         {cfg.resolved_p_block}")
        print(f"N_BLOCK:         {cfg.resolved_n_block}")


def build_parser(*, default_option: str = "d", description: str | None = None) -> argparse.ArgumentParser:
    if description is None:
        description = "Step 5 assembly: PN classifier dataset assembly."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--option", choices=sorted(OPTION_SPECS), default=default_option, help="Dataset option to run.")
    parser.add_argument("--positive-csv", default=None)
    parser.add_argument("--negative-csv", default=None)
    parser.add_argument("--full-metadata", default=None)
    parser.add_argument("--out-dir", default=None, help="Default depends on --option.")
    parser.add_argument("--seeds", nargs="+", type=int, default=None, help="Default depends on --option.")
    parser.add_argument("--holdout-frac", type=float, default=None, help="Default depends on --option.")
    parser.add_argument("--split-names", nargs="+", default=None, help="Default: F G H I for year-wise options.")
    parser.add_argument("--p-block", type=int, default=None, help="Default: 11 for interleave options.")
    parser.add_argument("--n-block", type=int, default=None, help="Default: 17 for interleave options.")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved paths and missing inputs without writing.")
    return parser


def config_from_args(args: argparse.Namespace) -> RunConfig:
    spec = get_option_spec(args.option)
    return RunConfig(
        spec=spec,
        pos_path=resolve_path(args.positive_csv) if args.positive_csv else POSITIVE_CSV,
        neg_path=resolve_path(args.negative_csv) if args.negative_csv else NEGATIVE_CSV,
        full_metadata_path=resolve_path(args.full_metadata) if args.full_metadata else FULL_METADATA_XLSX,
        out_dir=resolve_path(args.out_dir) if args.out_dir else None,
        seeds=tuple(args.seeds) if args.seeds is not None else None,
        holdout_frac=args.holdout_frac,
        split_names=tuple(args.split_names) if args.split_names is not None else None,
        p_block=args.p_block,
        n_block=args.n_block,
    )
