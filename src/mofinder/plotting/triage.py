"""Figures for saved abstract-triage analyses."""

from pathlib import Path
import re

import numpy as np


def slug(value):
    """Return a filename-safe configuration or metric name."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")


def plot_results(context, *, show=False):
    """Save triage figures as PNG, PDF, and SVG files.

    The input is the dictionary returned by evaluate_run. Set show=True to
    display figures in a notebook as well as save them.
    """
    import matplotlib.pyplot as plt

    FIGURE_DIR = Path(context["output_dir"]) / "figures"
    FIGURE_DIR.mkdir(exist_ok=True)
    figure_paths = []
    metrics = context["metrics"]
    metric_details = context["metric_details"]
    shared_details = context["shared_details"]
    vote_summary = context["vote_summary"]
    reference_summary = context["reference_summary"]
    N_ROUNDS = context["rounds"]
    MODELS = context["models"]

    def finish_figure(fig, name):
        fig.tight_layout()
        for extension in ["png", "pdf", "svg"]:
            path = FIGURE_DIR / f"{name}.{extension}"
            fig.savefig(path, dpi=300, bbox_inches="tight")
            figure_paths.append(path)
        if show:
            plt.show()
        plt.close(fig)

    for summary in metrics:
        name, round_number = summary["Configuration"], summary["Round"]
        if summary["Scored N"] == 0:
            print(f"No performance figure for {name}, round {round_number}: no valid scored answers.")
            continue
        suffix = f"{slug(name)}_round_{round_number}"
        fig, ax = plt.subplots(figsize=(6.4, 3.5))
        ax.axis("off")
        table = ax.table(cellText=[[f"TP = {summary['TP']}", f"FN = {summary['FN']}"],
                                  [f"FP = {summary['FP']}", f"TN = {summary['TN']}"]],
                         rowLabels=["Actual Y", "Actual N"], colLabels=["Predicted Y", "Predicted N"],
                         cellLoc="center", rowLoc="center", loc="center", bbox=[0.23, 0.1, 0.74, 0.70])
        table.auto_set_font_size(False); table.set_fontsize(12)
        ax.set_title(f"{name} | round {round_number}\nScored {summary['Scored N']} / {summary['Reference N']} reference papers")
        finish_figure(fig, "confusion_" + suffix)

        selected_metrics = ["Accuracy", "Precision", "Recall", "Specificity", "F1", "Balanced accuracy"]
        detail = {r["Metric"]: r for r in metric_details if r["Configuration"] == name and r["Round"] == round_number}
        fig, ax = plt.subplots(figsize=(7.4, 4.2))
        for i, metric in enumerate(selected_metrics):
            row = detail[metric]
            if np.isfinite(row["Estimate"]):
                ax.plot(row["Estimate"] * 100, i, "o")
            if np.isfinite(row["CI lower"]) and np.isfinite(row["CI upper"]):
                ax.hlines(i, row["CI lower"] * 100, row["CI upper"] * 100)
        ax.set_yticks(range(len(selected_metrics)), selected_metrics); ax.invert_yaxis()
        ax.set_xlim(0, 100); ax.set_xlabel("Performance (%) with 95% intervals")
        ax.set_title(f"{name} | round {round_number} | n = {summary['Scored N']}")
        finish_figure(fig, "performance_" + suffix)

    for round_number in range(1, N_ROUNDS + 1):
        if len(MODELS) < 2:
            continue
        for metric in ["F1", "Recall"]:
            rows = [r for r in shared_details if r["Round"] == round_number and r["Metric"] == metric]
            if not rows or rows[0]["Scored N"] == 0:
                continue
            fig, ax = plt.subplots(figsize=(7.4, max(2.8, len(rows) * 0.55 + 1.6)))
            for i, row in enumerate(rows):
                if np.isfinite(row["Estimate"]): ax.plot(row["Estimate"] * 100, i, "o")
                if np.isfinite(row["CI lower"]) and np.isfinite(row["CI upper"]):
                    ax.hlines(i, row["CI lower"] * 100, row["CI upper"] * 100)
            ax.set_yticks(range(len(rows)), [r["Configuration"] for r in rows]); ax.invert_yaxis()
            ax.set_xlim(0, 100); ax.set_xlabel(f"{metric} (%) with 95% intervals")
            ax.set_title(f"Shared scored papers: n = {rows[0]['Scored N']} | round {round_number}")
            finish_figure(fig, f"comparison_{slug(metric)}_round_{round_number}")

    fig, ax = plt.subplots(figsize=(8.2, max(3.4, len(vote_summary) * 0.45 + 1.5)))
    positions = np.arange(len(vote_summary))
    counts = [r["Publications"] for r in vote_summary]
    ax.barh(positions, counts)
    ax.set_yticks(positions, [r["Vote pattern"] for r in vote_summary]); ax.invert_yaxis()
    for i, count in enumerate(counts): ax.text(count + max(counts) * 0.015, i, str(count), va="center")
    ax.set_xlim(0, max(counts) * 1.17); ax.set_xlabel("Publications")
    ax.set_title("Human annotation vote patterns before consensus")
    finish_figure(fig, "human_vote_patterns")

    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    counts = [r["Publications"] for r in reference_summary]
    ax.bar(["Y", "N"], counts)
    for i, count in enumerate(counts): ax.text(i, count + max(counts) * 0.02, str(count), ha="center")
    ax.set_ylim(0, max(counts) * 1.18); ax.set_ylabel("Publications")
    ax.set_title("Recorded human-consensus reference")
    finish_figure(fig, "reference_label_distribution")

    return figure_paths
