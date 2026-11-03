"""Plot pairwise synthesis conditions from the positive and negative datasets."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .dataset_analysis import configure_style, numeric, read_csv, sha256


PARAMETERS = {
    "temperature": {"column": "temperature_c", "label": "Temperature (°C)",
                    "limits": (-100, 425), "scale": "linear", "ticks": (0, 200, 400)},
    "time": {"column": "time_h", "label": "Time (h)",
             "limits": (0.001, 10000), "scale": "log", "ticks": (0.001, 0.1, 10, 1000)},
    "concentration": {"column": "metel_concnertation", "label": "Metal concentration (mM)",
                      "limits": (0.7, 10000000), "scale": "log", "ticks": (1, 100, 10000, 1000000)},
    "ratio": {"column": "M_L_ratio", "label": "Metal-to-linker ratio",
              "limits": (0.007, 1000000), "scale": "log", "ticks": (0.01, 1, 100, 10000, 1000000)},
}
PAIRS = (
    ("time_temperature", "time", "temperature"),
    ("ratio_concentration", "ratio", "concentration"),
    ("temperature_concentration", "temperature", "concentration"),
    ("time_concentration", "time", "concentration"),
    ("temperature_ratio", "temperature", "ratio"),
    ("time_ratio", "time", "ratio"),
)
CLASSES = ("Positive", "Negative")
COLORS = {"Positive": "#285953", "Negative": "#8D969E"}
BASE_ALPHA = 0.24
CAPTION = (
    "Figure D1. Pairwise distributions of synthesis conditions. Columns show positive records, "
    "negative records, and their overlay; marker opacity reflects coincident records."
)


def load_conditions(project_root):
    """Read the positive and negative datasets with verified input hashes."""
    root = Path(project_root)
    provenance = json.loads((root / "docs/dataset_analysis/data/condition_coverage_provenance.json")
                            .read_text(encoding="utf-8"))
    data = {}
    for entry in provenance["repository_inputs"]:
        path = root / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError("Condition-coverage input changed: " + entry["path"])
        rows = read_csv(path)
        if len(rows) != entry["records"]:
            raise ValueError("Condition-coverage dataset size changed.")
        data[entry["class"]] = np.array(
            [[numeric(row[spec["column"]]) for spec in PARAMETERS.values()] for row in rows],
            dtype=float,
        )
    if set(data) != set(CLASSES):
        raise ValueError("Both positive and negative datasets are required.")
    return data


def _select_pair(records, x_parameter, y_parameter):
    keys = list(PARAMETERS)
    values = np.asarray(records, dtype=float)[:, [keys.index(x_parameter), keys.index(y_parameter)]]
    finite = np.isfinite(values).all(axis=1)
    valid = finite.copy()
    for column, key in enumerate((x_parameter, y_parameter)):
        if PARAMETERS[key]["scale"] == "log":
            valid &= values[:, column] > 0
    valid_values = values[valid]
    for column, key in enumerate((x_parameter, y_parameter)):
        low, high = PARAMETERS[key]["limits"]
        if not np.all((valid_values[:, column] >= low) & (valid_values[:, column] <= high)):
            raise ValueError("A valid condition falls outside the configured " + key + " range.")
    coordinates, multiplicities = np.unique(valid_values, axis=0, return_counts=True)
    counts = {"total_records": len(values), "finite_pair_records": int(finite.sum()),
              "plotted_records": int(valid.sum()),
              "omitted_missing_or_nonpositive": int((~valid).sum()),
              "distinct_coordinates": len(coordinates), "out_of_view": 0,
              "coordinates_sha256": hashlib.sha256(coordinates.astype("<f8").tobytes()).hexdigest(),
              "multiplicities_sha256": hashlib.sha256(multiplicities.astype("<i8").tobytes()).hexdigest()}
    return coordinates, multiplicities, counts


def select_coordinates(records, x_parameter, y_parameter):
    """Select finite pairs, requiring positive values on logarithmic axes."""
    coordinates, _, counts = _select_pair(records, x_parameter, y_parameter)
    return coordinates, counts


def marker_colors(label, multiplicities):
    """Combine the opacity of all records at each exact coordinate."""
    from matplotlib.colors import to_rgba

    counts = np.asarray(multiplicities)
    rgba = np.tile(to_rgba(COLORS[label]), (len(counts), 1))
    rgba[:, 3] = -np.expm1(counts * np.log1p(-BASE_ALPHA))
    return rgba


def summarize_coverage(data):
    rows = []
    for pair_id, x_parameter, y_parameter in PAIRS:
        for label in CLASSES:
            _, counts = select_coordinates(data[label], x_parameter, y_parameter)
            rows.append({"pair_id": pair_id, "class": label, **counts})
    return rows


def validate_reference(summary, project_root):
    path = Path(project_root) / "docs/dataset_analysis/data/condition_coverage_expected.json"
    expected = json.loads(path.read_text(encoding="utf-8"))["counts"]
    lookup = {(row["pair_id"], row["class"]): row for row in expected}
    if len(lookup) != len(summary):
        raise ValueError("Condition-coverage reference has a different set of parameter pairs.")
    for actual in summary:
        reference = lookup[(actual["pair_id"], actual["class"])]
        if any(actual[key] != reference[key] for key in actual):
            raise ValueError("Condition coverage differs from the reference: "
                             + actual["pair_id"] + "/" + actual["class"])
    return True


def plot_coverage(data):
    """Draw positive, negative, and overlaid records for six parameter pairs."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, LogFormatterMathtext, NullLocator

    configure_style()
    fig, axes = plt.subplots(6, 3, figsize=(6, 8.6), sharex="row", sharey="row")
    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.045, top=0.94,
                        hspace=0.72, wspace=0.18)
    for row, (_, x_parameter, y_parameter) in enumerate(PAIRS):
        points = {label: _select_pair(data[label], x_parameter, y_parameter)[:2]
                  for label in CLASSES}
        for column, ax in enumerate(axes[row]):
            labels = ("Positive",) if column == 0 else ("Negative",) if column == 1 else ("Negative", "Positive")
            for label in labels:
                xy, multiplicities = points[label]
                ax.scatter(xy[:, 0], xy[:, 1], s=3, c=marker_colors(label, multiplicities),
                           marker="o", linewidths=0, edgecolors="none", rasterized=False)
            for direction, key in (("x", x_parameter), ("y", y_parameter)):
                spec = PARAMETERS[key]
                getattr(ax, "set_" + direction + "scale")(spec["scale"])
                getattr(ax, "set_" + direction + "lim")(*spec["limits"])
                if direction == "x" or column == 0:
                    getattr(ax, "set_" + direction + "label")(spec["label"], fontsize=8, labelpad=3)
                axis = getattr(ax, direction + "axis")
                axis.set_major_locator(FixedLocator(spec["ticks"]))
                if spec["scale"] == "log":
                    axis.set_major_formatter(LogFormatterMathtext())
                axis.set_minor_locator(NullLocator())
            ax.tick_params(labelsize=8, direction="out", length=2.5, width=0.55,
                           pad=2, labelbottom=True, labelleft=column == 0)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.grid(False)
            ax.text(0, 1.08, chr(ord("a") + row * 3 + column), transform=ax.transAxes,
                    fontsize=12, fontweight="bold", ha="left", va="bottom")
            if row == 0:
                ax.set_title(("Positive", "Negative", "Overlaid")[column], fontsize=9, pad=18)
    return fig


def generate_outputs(data, project_root, output_dir, dpi=600):
    """Save Figure D1 and per-pair record counts."""
    import matplotlib.pyplot as plt

    root, output = Path(project_root), Path(output_dir)
    summary = summarize_coverage(data)
    validate_reference(summary, root)
    fig = plot_coverage(data)
    fig.canvas.draw()
    for ax in fig.axes:
        bounds = ax.get_tightbbox(fig.canvas.get_renderer())
        if bounds.x0 < -0.5 or bounds.y0 < -0.5 or bounds.x1 > fig.bbox.x1 + 0.5 or bounds.y1 > fig.bbox.y1 + 0.5:
            raise ValueError("A condition-coverage label extends outside the figure.")
    image_path = output / "figures/Figure_D1_pairwise_condition_coverage.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(image_path, dpi=dpi, facecolor="white")
    plt.close(fig)
    table_path = output / "tables/D1_pairwise_coverage_counts.csv"
    table_path.parent.mkdir(parents=True, exist_ok=True)
    with table_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    provenance_path = root / "docs/dataset_analysis/data/condition_coverage_provenance.json"
    manifest = {"figure": "D1", "caption": CAPTION,
                "width_inches": 6, "height_inches": 8.6, "dpi": dpi,
                "font": configure_style(), "axis_font_pt": 8, "panel_font_pt": 12,
                "panel_columns": ["Positive", "Negative", "Overlaid"],
                "display_parameters": PARAMETERS, "base_marker_opacity": BASE_ALPHA,
                "png": image_path.relative_to(output).as_posix(), "png_sha256": sha256(image_path),
                "provenance_sha256": sha256(provenance_path), "counts": summary}
    (output / "condition_coverage_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("results/dataset_analysis"))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    data = load_conditions(args.project_root)
    validate_reference(summarize_coverage(data), args.project_root)
    if args.check_only:
        print("Verified all 12 class/pair counts and coordinate sets.")
        return
    output = args.output if args.output.is_absolute() else args.project_root / args.output
    generate_outputs(data, args.project_root, output)
    print("Saved Figure D1 and condition-coverage counts.")


if __name__ == "__main__":
    main()
