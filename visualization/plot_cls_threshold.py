"""Plot classification metrics as a function of the probability threshold.

This script refactors the first code cell from ``step 7 plot.ipynb``.
Run it from the repository root:

    python visualization/plot_cls_threshold.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_existing_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        if path.exists():
            return path
        raise FileNotFoundError(path)

    candidates = [
        Path.cwd() / path,
        ROOT / path,
        ROOT / "eval" / path,
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


def compute_metrics(df: pd.DataFrame, thresholds: np.ndarray) -> pd.DataFrame:
    y_true = (df["gold_label"] == "P").astype(int)
    prob = df["prob_P"]

    rows = []
    for threshold in thresholds:
        y_pred = (prob >= threshold).astype(int)
        rows.append(
            {
                "threshold": threshold,
                "accuracy": accuracy_score(y_true, y_pred),
                "precision": precision_score(y_true, y_pred, zero_division=0),
                "recall": recall_score(y_true, y_pred, zero_division=0),
                "f1": f1_score(y_true, y_pred, zero_division=0),
            }
        )

    return pd.DataFrame(rows)


def print_summary(metrics: pd.DataFrame) -> None:
    metric_names = ["accuracy", "precision", "recall", "f1"]

    print("Max values for each metric:")
    for name in metric_names:
        row = metrics.loc[metrics[name].idxmax()]
        print(f"  {name:9s} max = {row[name]:.4f} at threshold = {row['threshold']:.3f}")

    print("\nCrossing (closest) thresholds between metric pairs:")
    interior = metrics[(metrics["threshold"] > 0) & (metrics["threshold"] < 1)]
    if interior.empty:
        interior = metrics

    for i, first in enumerate(metric_names):
        for second in metric_names[i + 1 :]:
            diff = (interior[first] - interior[second]).abs()
            row = interior.loc[diff.idxmin()]
            print(
                f"  {first:9s} and {second:9s} closest at threshold ~{row['threshold']:.3f} "
                f"({row[first]:.4f} vs {row[second]:.4f})"
            )


def plot_metrics(metrics: pd.DataFrame, output_path: Path, show: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(metrics["threshold"], metrics["accuracy"], label="accuracy")
    ax.plot(metrics["threshold"], metrics["recall"], label="recall")
    ax.plot(metrics["threshold"], metrics["precision"], label="precision")
    ax.plot(metrics["threshold"], metrics["f1"], label="f1")
    ax.set_xlabel("threshold")
    ax.set_ylabel("score")
    ax.set_title("Metrics vs threshold")
    ax.legend()
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")

    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot accuracy, precision, recall, and F1 over classification thresholds."
    )
    parser.add_argument(
        "--input",
        default="out/mof_cls_holdout_eval.csv",
        help="CSV containing gold_label and prob_P. Relative paths are searched from cwd, repo root, eval/, and visualization/.",
    )
    parser.add_argument(
        "--output",
        default=str(SCRIPT_DIR / "figures" / "cls_threshold_metrics.svg"),
        help="Figure path to write.",
    )
    parser.add_argument(
        "--metrics-csv",
        default=str(SCRIPT_DIR / "figures" / "cls_threshold_metrics.csv"),
        help="Optional CSV path for the threshold metric table. Use an empty string to skip.",
    )
    parser.add_argument("--steps", type=int, default=101, help="Number of thresholds between 0 and 1.")
    parser.add_argument("--show", action="store_true", help="Show the plot window after saving.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_existing_path(args.input)
    output_path = Path(args.output)

    df = pd.read_csv(input_path)
    ensure_columns(df, ["gold_label", "prob_P"], input_path)

    thresholds = np.linspace(0, 1, args.steps)
    metrics = compute_metrics(df, thresholds)
    print_summary(metrics)

    if args.metrics_csv:
        metrics_csv = Path(args.metrics_csv)
        metrics_csv.parent.mkdir(parents=True, exist_ok=True)
        metrics.to_csv(metrics_csv, index=False)
        print(f"\nSaved metrics table: {metrics_csv}")

    plot_metrics(metrics, output_path, args.show)
    print(f"Saved figure: {output_path}")


if __name__ == "__main__":
    main()
