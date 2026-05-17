"""Plot multi-run classification metrics and ensemble comparison.

This script refactors the second code cell from ``step 7 plot.ipynb``.
Run it from the repository root:

    python visualization/plot_cls_runs_ensemble.py
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_glob(pattern_text: str) -> list[Path]:
    pattern_text = pattern_text.replace("\\", "/")
    pattern = Path(pattern_text)

    if pattern.is_absolute():
        matches = [Path(p) for p in glob.glob(str(pattern))]
    else:
        bases = [Path.cwd(), ROOT, ROOT / "eval", SCRIPT_DIR]
        matches = []
        for base in bases:
            matches.extend(Path(p) for p in glob.glob(str(base / pattern_text)))

    unique = sorted({p.resolve() for p in matches if p.exists()})
    if unique:
        return unique

    raise FileNotFoundError(f"Could not find any files matching {pattern_text!r}.")


def ensure_columns(df: pd.DataFrame, columns: list[str], csv_path: Path) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} is missing required columns: {missing}")


def metrics_vs_threshold(df: pd.DataFrame, thresholds: np.ndarray) -> tuple[np.ndarray, ...]:
    y_true = (df["gold_label"] == "P").astype(int).values
    prob = df["prob_P"].values

    acc, rec, pre, f1 = [], [], [], []
    n = len(y_true)

    for threshold in thresholds:
        y_pred = (prob >= threshold).astype(int)
        tp = ((y_pred == 1) & (y_true == 1)).sum()
        tn = ((y_pred == 0) & (y_true == 0)).sum()
        fp = ((y_pred == 1) & (y_true == 0)).sum()
        fn = ((y_pred == 0) & (y_true == 1)).sum()

        acc_t = (tp + tn) / n
        pre_t = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec_t = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_t = 2 * pre_t * rec_t / (pre_t + rec_t) if (pre_t + rec_t) > 0 else 0.0

        acc.append(acc_t)
        pre.append(pre_t)
        rec.append(rec_t)
        f1.append(f1_t)

    return np.array(acc), np.array(rec), np.array(pre), np.array(f1)


def get_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float, float]:
    y_true = y_true.astype(int)
    y_pred = y_pred.astype(int)
    tp = ((y_pred == 1) & (y_true == 1)).sum()
    tn = ((y_pred == 0) & (y_true == 0)).sum()
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    fn = ((y_pred == 0) & (y_true == 1)).sum()

    acc = (tp + tn) / len(y_true)
    pre = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * pre * rec / (pre + rec) if (pre + rec) > 0 else 0.0
    return acc, pre, rec, f1


def plot_with_bands(ax: plt.Axes, thresholds: np.ndarray, mean: np.ndarray, std: np.ndarray, label: str) -> None:
    ax.plot(thresholds, mean, label=label)
    for multiplier in [1, 2, 5]:
        ax.fill_between(thresholds, mean - multiplier * std, mean + multiplier * std, alpha=0.1)


def plot_threshold_bands(
    dfs: list[pd.DataFrame],
    thresholds: np.ndarray,
    output_path: Path,
    show: bool,
) -> None:
    all_acc, all_rec, all_pre, all_f1 = [], [], [], []
    for df in dfs:
        acc, rec, pre, f1 = metrics_vs_threshold(df, thresholds)
        all_acc.append(acc)
        all_rec.append(rec)
        all_pre.append(pre)
        all_f1.append(f1)

    all_acc = np.vstack(all_acc)
    all_rec = np.vstack(all_rec)
    all_pre = np.vstack(all_pre)
    all_f1 = np.vstack(all_f1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 7))
    plot_with_bands(ax, thresholds, all_acc.mean(0), all_acc.std(0), "Accuracy")
    plot_with_bands(ax, thresholds, all_rec.mean(0), all_rec.std(0), "Recall")
    plot_with_bands(ax, thresholds, all_pre.mean(0), all_pre.std(0), "Precision")
    plot_with_bands(ax, thresholds, all_f1.mean(0), all_f1.std(0), "F1")

    ax.set_xlabel("Threshold on prob_P")
    ax.set_ylabel("Metric value")
    ax.set_title("Metrics vs threshold with +/-1, +/-2, +/-5 std shading")
    ax.grid(True)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")

    if show:
        plt.show()
    plt.close(fig)


def build_ensemble_table(
    dfs: list[pd.DataFrame],
    fixed_threshold: float,
    majority_votes: int | None,
) -> pd.DataFrame:
    merged = dfs[0][["example_index", "gold_label", "prob_P"]].rename(columns={"prob_P": "prob_P_1"})
    for index, df in enumerate(dfs[1:], start=2):
        current = df[["example_index", "prob_P"]].rename(columns={"prob_P": f"prob_P_{index}"})
        merged = merged.merge(current, on="example_index", how="inner")

    prob_cols = [column for column in merged.columns if column.startswith("prob_P_")]
    for column in prob_cols:
        merged[column.replace("prob_P", "pred")] = (merged[column] >= fixed_threshold).astype(int)
    pred_cols = [column for column in merged.columns if column.startswith("pred_")]

    required_votes = majority_votes if majority_votes is not None else (len(pred_cols) // 2 + 1)
    merged["maj_pred"] = (merged[pred_cols].sum(axis=1) >= required_votes).astype(int)
    merged["avg_prob"] = merged[prob_cols].mean(axis=1)
    merged["avg_pred"] = (merged["avg_prob"] >= fixed_threshold).astype(int)

    rows = []
    for index, df in enumerate(dfs, start=1):
        y_true = (df["gold_label"] == "P").astype(int).values
        y_pred = (df["prob_P"] >= fixed_threshold).astype(int).values
        rows.append((f"run_{index}", *get_metrics(y_true, y_pred)))

    y_true_all = (merged["gold_label"] == "P").astype(int).values
    rows.append(("avg_prob", *get_metrics(y_true_all, merged["avg_pred"].values)))
    rows.append(("majority", *get_metrics(y_true_all, merged["maj_pred"].values)))

    return pd.DataFrame(rows, columns=["model", "acc", "pre", "rec", "f1"])


def plot_ensemble_table(table: pd.DataFrame, output_path: Path, show: bool) -> None:
    labels = table["model"].values
    x = np.arange(len(labels))
    width = 0.2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width, table["acc"].values, width, label="Accuracy")
    ax.bar(x, table["pre"].values, width, label="Precision")
    ax.bar(x + width, table["rec"].values, width, label="Recall")
    ax.plot(x, table["f1"].values, marker="o", linewidth=2, label="F1")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45)
    ax.set_ylabel("Metric")
    ax.set_title("Individual runs vs avg_prob vs majority")
    ax.grid(True, axis="y")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")

    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot repeated holdout run metrics and compare average-probability and majority-vote ensembles."
    )
    parser.add_argument(
        "--pattern",
        default="out/mof_cls_holdout_eval_[0-9]*.csv",
        help="Glob for repeated run CSVs. Relative paths are searched from cwd, repo root, eval/, and visualization/.",
    )
    parser.add_argument("--threshold-step", type=float, default=0.05, help="Threshold grid step for the band plot.")
    parser.add_argument("--fixed-threshold", type=float, default=0.5, help="Threshold for individual and ensemble metrics.")
    parser.add_argument(
        "--majority-votes",
        type=int,
        default=None,
        help="Votes required for majority ensemble. Defaults to strict majority of loaded runs.",
    )
    parser.add_argument(
        "--bands-output",
        default=str(SCRIPT_DIR / "figures" / "cls_runs_threshold_bands.svg"),
        help="Output figure for mean metric curves with std bands.",
    )
    parser.add_argument(
        "--ensemble-output",
        default=str(SCRIPT_DIR / "figures" / "cls_runs_ensemble.svg"),
        help="Output figure for individual run and ensemble comparison.",
    )
    parser.add_argument(
        "--table-output",
        default=str(SCRIPT_DIR / "figures" / "cls_runs_ensemble_metrics.csv"),
        help="Output CSV for individual run and ensemble metrics. Use an empty string to skip.",
    )
    parser.add_argument("--show", action="store_true", help="Show plot windows after saving.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = resolve_glob(args.pattern)
    dfs = []
    for path in paths:
        df = pd.read_csv(path)
        ensure_columns(df, ["example_index", "gold_label", "prob_P"], path)
        dfs.append(df)

    print("Loaded files:")
    for path in paths:
        print(f"  {path}")

    thresholds = np.arange(0.0, 1.0 + args.threshold_step / 2, args.threshold_step)
    plot_threshold_bands(dfs, thresholds, Path(args.bands_output), args.show)
    print(f"Saved threshold band figure: {args.bands_output}")

    table = build_ensemble_table(dfs, args.fixed_threshold, args.majority_votes)
    print("\nMetrics at fixed threshold:")
    print(table)

    if args.table_output:
        table_output = Path(args.table_output)
        table_output.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(table_output, index=False)
        print(f"\nSaved metrics table: {table_output}")

    plot_ensemble_table(table, Path(args.ensemble_output), args.show)
    print(f"Saved ensemble figure: {args.ensemble_output}")


if __name__ == "__main__":
    main()
