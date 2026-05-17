"""Plot human chemist and LLM performance figures.

This script refactors the fourth code cell from ``step 7 plot.ipynb``.
Run it from the repository root:

    python visualization/plot_human_llm_performance.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent

LABELS = [
    "MOF Synthesis <1 yr",
    "MOF Synthesis 1-3 yr",
    "MOF Synthesis >3 yr",
    "Vanilla LLM",
    "Web-search LLM",
    "Ft LLM (7k exps)",
    "Ft LLM (14k exps)",
    "Ft LLM (21k exps)",
    "Ft LLM (28k exps)",
]
ACCURACY = np.array([50.6, 56.8, 51.9, 61.5, 60.4, 62.5, 68.2, 75.3, 80.2])
STD = np.array([11.6, 10.8, 9.1, 3.6, 4.1, 3.7, 3.5, 3.9, 2.2])


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.labelsize": 13,
            "axes.titlesize": 14,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "figure.dpi": 150,
        }
    )


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", linewidth=0.7, alpha=0.4)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=3)


def annotate_groups(ax: plt.Axes, y_position: float = 92.0) -> None:
    ax.axvline(2.5, linestyle="--", linewidth=0.8)
    ax.text(1.0, y_position, "Human chemists", ha="center", va="center")
    ax.text(5.5, y_position, "LLMs", ha="center", va="center")


def plot_bar(output_path: Path, show: bool) -> None:
    idx = np.arange(len(LABELS))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(idx, ACCURACY, yerr=STD, capsize=4)
    ax.set_ylabel("Accuracy (%)")
    ax.set_xticks(idx)
    ax.set_xticklabels(LABELS, rotation=30, ha="right")
    ax.set_ylim(0, 100)
    ax.set_title("Performance of Human Chemists vs LLMs")
    annotate_groups(ax)

    for i, (mean, std) in enumerate(zip(ACCURACY, STD)):
        ax.text(i, mean + std + 1.0, f"{mean:.1f}", ha="center", va="bottom", fontsize=9)

    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def plot_interval(output_path: Path, show: bool) -> None:
    idx = np.arange(len(LABELS))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    x_humans = idx[:3]
    x_llms = idx[3:]

    ax.plot(x_humans, ACCURACY[:3], marker="o", linewidth=1.6)
    for x, mean, std in zip(x_humans, ACCURACY[:3], STD[:3]):
        ax.fill_between([x - 0.18, x + 0.18], [mean - std, mean - std], [mean + std, mean + std], alpha=0.25)

    ax.plot(x_llms, ACCURACY[3:], marker="s", linewidth=1.6)
    for x, mean, std in zip(x_llms, ACCURACY[3:], STD[3:]):
        ax.fill_between([x - 0.18, x + 0.18], [mean - std, mean - std], [mean + std, mean + std], alpha=0.25)

    ax.set_ylabel("Accuracy (%)")
    ax.set_xticks(idx)
    ax.set_xticklabels(LABELS, rotation=30, ha="right")
    ax.set_ylim(0, 100)
    ax.set_title("Interval plot of performance: mean +/- SD")
    annotate_groups(ax)

    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot human chemist and LLM performance figures.")
    parser.add_argument(
        "--bar-output",
        default=str(SCRIPT_DIR / "figures" / "human_llm_performance_bar.svg"),
        help="Output path for the bar plot.",
    )
    parser.add_argument(
        "--interval-output",
        default=str(SCRIPT_DIR / "figures" / "human_llm_performance_interval.svg"),
        help="Output path for the interval plot.",
    )
    parser.add_argument("--show", action="store_true", help="Show plot windows after saving.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    apply_style()
    plot_bar(Path(args.bar_output), args.show)
    print(f"Saved bar plot: {args.bar_output}")
    plot_interval(Path(args.interval_output), args.show)
    print(f"Saved interval plot: {args.interval_output}")


if __name__ == "__main__":
    main()
