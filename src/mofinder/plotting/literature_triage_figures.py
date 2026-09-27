"""Plot publisher coverage by publication period.

This analysis counts bibliography records before abstract triage. It does not
deduplicate DOI values or count synthesis records. Publisher-name mapping is
explicit and shipped with the figure inputs.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path


PUBLISHERS = ("Elsevier", "RSC", "ACS", "Wiley", "Springer Nature")
PERIODS = ((1996, 2005), (2006, 2015), (2016, 2025))
PERIOD_LABELS = tuple(f"{low}\N{EN DASH}{high}" for low, high in PERIODS)
COLORS = ("#98F4E0", "#C6DCB9", "#B6E2DC", "#BBFABF", "#C6C3E1")


def summarize_publishers(source_csv, mapping_csv):
    """Validate every source row and count publisher families by year period."""
    with Path(mapping_csv).open(encoding="utf-8-sig", newline="") as handle:
        mapping_rows = list(csv.DictReader(handle))
    mapping = {row["source_publisher"]: row["publisher_family"] for row in mapping_rows}
    if len(mapping) != len(mapping_rows):
        raise ValueError("Publisher mapping has duplicate source names.")
    if set(mapping.values()) - set(PUBLISHERS):
        raise ValueError("Publisher mapping contains an unrecognized family.")

    counts = Counter()
    source_rows = set()
    with Path(source_csv).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source_row = int(row["source_excel_row"])
            if source_row in source_rows:
                raise ValueError(f"Repeated source row {source_row}.")
            source_rows.add(source_row)
            raw_name = row["Publisher"]
            if raw_name not in mapping:
                raise ValueError(f"Unmapped publisher name: {raw_name!r}")
            year = int(row["Publication Year"])
            matches = [i for i, (low, high) in enumerate(PERIODS) if low <= year <= high]
            if len(matches) != 1:
                raise ValueError(f"Publication year {year} is outside the specified periods.")
            counts[mapping[raw_name], matches[0]] += 1
    total = len(source_rows)
    if total == 0:
        raise ValueError("Source table contains no bibliography records.")
    summary = []
    for family in PUBLISHERS:
        segments = [counts[family, i] for i in range(len(PERIODS))]
        count = sum(segments)
        row = {"Publisher": family, **dict(zip(PERIOD_LABELS, segments))}
        row.update({"Total": count, "Percentage": 100 * count / total})
        summary.append(row)
    assert sum(row["Total"] for row in summary) == total
    return summary


def draw_publisher_coverage(summary, output_dir):
    """Save a 6-inch Arial Figure D11 and its exact source summary."""
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    table_path = destination / "publisher_period_counts.csv"
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    style = {
        "font.family": ["Arial", "DejaVu Sans"], "font.size": 9,
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "legend.fontsize": 9, "axes.linewidth": 0.7, "svg.fonttype": "none",
        "pdf.fonttype": 42,
    }
    with plt.rc_context(style):
        fig, ax = plt.subplots(figsize=(6, 4.15), dpi=120)
        fig.subplots_adjust(left=0.11, right=0.985, top=0.95, bottom=0.23)
        x = np.arange(len(summary))
        bottom = np.zeros(len(summary), dtype=int)
        shades = (0.45, 0.70, 1.0)
        for period, shade in zip(PERIOD_LABELS, shades):
            values = np.array([row[period] for row in summary])
            fills = [tuple(np.array(colors.to_rgb(c)) * shade) for c in COLORS]
            ax.bar(x, values, width=0.5, bottom=bottom, color=fills, linewidth=0)
            bottom += values
        for i, row in enumerate(summary):
            ax.text(i, row["Total"] + 65, f"{row['Total']:,}\n({row['Percentage']:.1f}%)",
                    ha="center", va="bottom", fontsize=9, linespacing=1.0)
        ax.set_xticks(x, [row["Publisher"] for row in summary])
        ax.set_ylabel("Counts")
        ax.set_ylim(0, max(bottom) * 1.20)
        ax.set_xlim(-0.6, len(summary) - 0.4)
        ax.tick_params(width=0.7, length=3)
        ax.grid(False)
        handles = [Patch(facecolor=c, edgecolor="none", label=label)
                   for c, label in zip(("#737373", "#AAAAAA", "#E5E5E5"), PERIOD_LABELS)]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.53, 0.03),
                   ncol=3, frameon=False, handlelength=0.8, columnspacing=1.1,
                   handletextpad=0.4)
        outputs = {}
        for extension in ("png", "pdf", "svg"):
            path = destination / f"Figure_D11_publisher_coverage.{extension}"
            fig.savefig(path, dpi=600, facecolor="white")
            outputs[extension] = path
        plt.close(fig)
    outputs["counts"] = table_path
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = summarize_publishers(args.source, args.mapping)
    outputs = draw_publisher_coverage(summary, args.output_dir)
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
