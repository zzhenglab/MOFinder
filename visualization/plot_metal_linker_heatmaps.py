"""Plot metal-linker heatmaps from the cleaned MOF extraction table.

This script refactors the third code cell from ``step 7 plot.ipynb``.
Run it from the repository root:

    python visualization/plot_metal_linker_heatmaps.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, Normalize, PowerNorm


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DROPPED_LINKERS = [
    "HOOCC6H4CH2PO(OH)(OC2H5)",
    "disodium isophthalate",
    "D-(+)-camphoric acid",
]


def resolve_existing_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        if path.exists():
            return path
        raise FileNotFoundError(path)

    candidates = [
        Path.cwd() / path,
        ROOT / path,
        ROOT / "data" / path,
        SCRIPT_DIR / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    searched = "\n  ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Could not find {path_text!r}. Searched:\n  {searched}")


def ensure_columns(df: pd.DataFrame, columns: list[str], csv_path: Path) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} is missing required columns: {missing}")


def extract_metal_from_desc(desc: str) -> str | None:
    if not isinstance(desc, str):
        return None
    match = re.search(r"\b(?:a|an)\s+([a-z]+)\s+metal-organic framework", desc, flags=re.IGNORECASE)
    return match.group(1).lower().strip() if match else None


def prepare_heat_data(
    df: pd.DataFrame,
    linker_col: str = "linker_1",
    top_n_linkers: int = 20,
    top_n_metals: int = 8,
    linker_max_len: int = 35,
    drop_linkers: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    df = df.copy()

    if drop_linkers:
        df = df[~df[linker_col].isin(drop_linkers)]

    sub = df.dropna(subset=[linker_col, "metal_from_desc"]).copy()
    sub[linker_col] = sub[linker_col].astype(str).str.strip()
    sub["metal_from_desc"] = sub["metal_from_desc"].astype(str).str.strip()
    sub = sub[sub[linker_col].str.len() <= linker_max_len]

    top_linkers = sub[linker_col].value_counts().head(top_n_linkers).index.tolist()
    top_metals = sub["metal_from_desc"].value_counts().head(top_n_metals).index.tolist()
    sub = sub[sub[linker_col].isin(top_linkers) & sub["metal_from_desc"].isin(top_metals)]

    heat_data = (
        sub.groupby([linker_col, "metal_from_desc"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=top_linkers, columns=top_metals, fill_value=0)
    )

    return heat_data, top_linkers, top_metals


def parse_cell(value: str) -> tuple[int, int]:
    try:
        row, col = value.split(",", 1)
        return int(row), int(col)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Bad cells must use ROW,COL format, for example 17,8.") from exc


def build_norm(masked: np.ma.MaskedArray, norm_scale: str):
    if masked.count() == 0:
        raise ValueError("No non-zero heatmap cells were found after filtering.")

    data_min = float(masked.min())
    data_max = float(masked.max())
    if norm_scale == "log":
        return LogNorm(vmin=max(data_min, 1.0), vmax=data_max)
    if norm_scale == "sqrt":
        return PowerNorm(gamma=0.5, vmin=data_min, vmax=data_max)
    return Normalize(vmin=data_min, vmax=data_max)


def apply_bad_cells(data: np.ndarray, bad_cells: list[tuple[int, int]] | None, value: float) -> None:
    if not bad_cells:
        return

    for row, col in bad_cells:
        row_index = row - 1
        col_index = col - 1
        if 0 <= row_index < data.shape[0] and 0 <= col_index < data.shape[1]:
            data[row_index, col_index] = value


def plot_vertical_heatmap(
    df: pd.DataFrame,
    output_path: Path,
    top_n_linkers: int,
    top_n_metals: int,
    height: float,
    width: float,
    color_map: str,
    norm_scale: str,
    bad_cells: list[tuple[int, int]] | None,
    bad_value_for_color: float,
    linker_max_len: int,
    drop_linkers: list[str] | None,
    font_size: float,
    show: bool,
) -> None:
    heat_data, top_linkers, top_metals = prepare_heat_data(
        df,
        top_n_linkers=top_n_linkers,
        top_n_metals=top_n_metals,
        linker_max_len=linker_max_len,
        drop_linkers=drop_linkers,
    )

    data = heat_data.to_numpy().astype(float)
    apply_bad_cells(data, bad_cells, bad_value_for_color)
    masked = np.ma.masked_where(data == 0, data)
    norm = build_norm(masked, norm_scale)

    cmap = plt.get_cmap(color_map).copy()
    cmap.set_bad(color="lightgray")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(masked, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(np.arange(len(top_metals)))
    ax.set_yticks(np.arange(len(top_linkers)))
    ax.set_xticklabels(top_metals, rotation=45, ha="right", fontsize=font_size * 0.9)
    ax.set_yticklabels(top_linkers, fontsize=font_size * 0.9)
    ax.set_xlabel("Metal", fontsize=font_size)
    ax.set_ylabel("Linker", fontsize=font_size)
    ax.set_title("Metal-Linker Heatmap (Vertical)", fontsize=font_size + 2)
    ax.tick_params(axis="both", which="both", labelsize=font_size * 0.9)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Protocol Count", fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size * 0.9)

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def plot_horizontal_heatmap(
    df: pd.DataFrame,
    output_path: Path,
    top_n_linkers: int,
    top_n_metals: int,
    height: float,
    width: float,
    color_map: str,
    norm_scale: str,
    bad_cells: list[tuple[int, int]] | None,
    bad_value_for_color: float,
    linker_max_len: int,
    drop_linkers: list[str] | None,
    font_size: float,
    show: bool,
) -> None:
    heat_data, top_linkers, top_metals = prepare_heat_data(
        df,
        top_n_linkers=top_n_linkers,
        top_n_metals=top_n_metals,
        linker_max_len=linker_max_len,
        drop_linkers=drop_linkers,
    )

    data = heat_data.to_numpy().astype(float)
    apply_bad_cells(data, bad_cells, bad_value_for_color)
    masked = np.ma.masked_where(data == 0, data).T
    norm = build_norm(masked, norm_scale)

    cmap = plt.get_cmap(color_map).copy()
    cmap.set_bad(color="lightgray")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(masked, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(np.arange(len(top_linkers)))
    ax.set_yticks(np.arange(len(top_metals)))
    ax.set_xticklabels(top_linkers, rotation=45, ha="right", fontsize=font_size * 0.9)
    ax.set_yticklabels(top_metals, fontsize=font_size * 0.9)
    ax.set_xlabel("Linker", fontsize=font_size)
    ax.set_ylabel("Metal", fontsize=font_size)
    ax.set_title("Metal-Linker Heatmap (Horizontal)", fontsize=font_size + 2)
    ax.tick_params(axis="both", which="both", labelsize=font_size * 0.9)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Protocol Count", fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size * 0.9)

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot vertical and horizontal metal-linker heatmaps.")
    parser.add_argument(
        "--input",
        default="data/mof_extraction_1_2_3_4_5_6.csv",
        help="Cleaned MOF extraction CSV. Relative paths are searched from cwd, repo root, data/, and visualization/.",
    )
    parser.add_argument("--linker-col", default="linker_1", help="Linker column to count.")
    parser.add_argument("--desc-col", default="mof_description", help="MOF description column used to extract metals.")
    parser.add_argument("--linker-max-len", type=int, default=30, help="Drop linker labels longer than this.")
    parser.add_argument("--drop-linker", action="append", default=None, help="Linker to drop. Can be repeated.")
    parser.add_argument("--no-default-drop-linkers", action="store_true", help="Disable the notebook's default dropped linkers.")
    parser.add_argument("--bad-value-for-color", type=float, default=1.0, help="Replacement value for manually marked cells.")

    parser.add_argument("--vertical-output", default=str(SCRIPT_DIR / "figures" / "vertical_heatmap.svg"))
    parser.add_argument("--vertical-top-linkers", type=int, default=100)
    parser.add_argument("--vertical-top-metals", type=int, default=8)
    parser.add_argument("--vertical-height", type=float, default=18)
    parser.add_argument("--vertical-width", type=float, default=3.5)
    parser.add_argument("--vertical-cmap", default="plasma")
    parser.add_argument("--vertical-norm", choices=["linear", "log", "sqrt"], default="log")
    parser.add_argument("--vertical-font-size", type=float, default=7.5)
    parser.add_argument("--vertical-bad-cell", action="append", type=parse_cell, default=[(17, 8), (15, 8), (14, 8)])

    parser.add_argument("--horizontal-output", default=str(SCRIPT_DIR / "figures" / "horizontal_heatmap.svg"))
    parser.add_argument("--horizontal-top-linkers", type=int, default=25)
    parser.add_argument("--horizontal-top-metals", type=int, default=8)
    parser.add_argument("--horizontal-height", type=float, default=2.5)
    parser.add_argument("--horizontal-width", type=float, default=7)
    parser.add_argument("--horizontal-cmap", default="cividis")
    parser.add_argument("--horizontal-norm", choices=["linear", "log", "sqrt"], default="log")
    parser.add_argument("--horizontal-font-size", type=float, default=7.5)
    parser.add_argument("--horizontal-bad-cell", action="append", type=parse_cell, default=[(2, 3), (5, 7)])

    parser.add_argument("--show", action="store_true", help="Show plot windows after saving.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_existing_path(args.input)
    df = pd.read_csv(input_path)
    ensure_columns(df, [args.linker_col, args.desc_col], input_path)
    df["metal_from_desc"] = df[args.desc_col].apply(extract_metal_from_desc)

    drop_linkers: list[str] = []
    if not args.no_default_drop_linkers:
        drop_linkers.extend(DEFAULT_DROPPED_LINKERS)
    if args.drop_linker:
        drop_linkers.extend(args.drop_linker)

    plot_vertical_heatmap(
        df,
        output_path=Path(args.vertical_output),
        top_n_linkers=args.vertical_top_linkers,
        top_n_metals=args.vertical_top_metals,
        height=args.vertical_height,
        width=args.vertical_width,
        color_map=args.vertical_cmap,
        norm_scale=args.vertical_norm,
        bad_cells=args.vertical_bad_cell,
        bad_value_for_color=args.bad_value_for_color,
        linker_max_len=args.linker_max_len,
        drop_linkers=drop_linkers,
        font_size=args.vertical_font_size,
        show=args.show,
    )
    print(f"Saved vertical heatmap: {args.vertical_output}")

    plot_horizontal_heatmap(
        df,
        output_path=Path(args.horizontal_output),
        top_n_linkers=args.horizontal_top_linkers,
        top_n_metals=args.horizontal_top_metals,
        height=args.horizontal_height,
        width=args.horizontal_width,
        color_map=args.horizontal_cmap,
        norm_scale=args.horizontal_norm,
        bad_cells=args.horizontal_bad_cell,
        bad_value_for_color=args.bad_value_for_color,
        linker_max_len=args.linker_max_len,
        drop_linkers=drop_linkers,
        font_size=args.horizontal_font_size,
        show=args.show,
    )
    print(f"Saved horizontal heatmap: {args.horizontal_output}")


if __name__ == "__main__":
    main()
