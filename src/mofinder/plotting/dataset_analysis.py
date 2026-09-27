"""Plot the positive dataset by synthesis record and unique DOI."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import textwrap

import numpy as np


CATEGORIES = (
    ("D2", "metal_1", "top20_metal_precursors", "Primary metal precursor", 20),
    ("D3", "linker_1", "top20_linkers", "Primary linker", 20),
    ("D4", "solvent_main", "top10_solvents", "Main solvent", 10),
    ("D5", "modulator_1", "top10_modulators", "Primary modulator", 10),
    ("D6", "topology_code", "top20_topology_codes", "Topology code", 20),
)
PROPERTIES = (
    ("D7", "BET_surface_area_m2g", "BET_surface_area", "BET surface area (m²/g)", "linear"),
    ("D8", "tga_decomposition_temp_c", "TGA_temperature", "TGA decomposition temperature (°C)", "linear"),
)
VARIANTS = {False: "01_synthesis_records", True: "02_records_and_DOI"}
STABILITY_FIELDS = (("air_stable", "Air stability"), ("water_stable", "Water stability"))
STABILITY_LABELS = ("Yes", "No", "Not reported")
MISSING = {"", "nan", "none", "null", "n/a", "na"}
MODULATOR_ALIASES = {
    "sodium hydroxide": ["sodium hydroxide", "naoh"],
    "potassium hydroxide": ["potassium hydroxide", "koh"],
    "hydrochloric acid": ["hydrochloric acid", "hcl"],
    "nitric acid": ["nitric acid", "hno3"],
    "acetic acid": ["acetic acid", "hoac", "hac", "ch3cooh"],
    "formic acid": ["formic acid", "hcooh"],
    "triethylamine": ["triethylamine", "et3n", "tea"],
    "benzoic acid": ["benzoic acid"],
    "trifluoroacetic acid": ["trifluoroacetic acid", "tfa", "cf3cooh"],
    "hydrofluoric acid": ["hydrofluoric acid", "hf"],
    "pyridine": ["pyridine"],
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def clean_text(value):
    value = re.sub(r"\s+", " ", str(value)).strip()
    return "" if value.lower() in MISSING else value


def chemical_text(value):
    return clean_text(value).replace("′", "'").replace("’", "'").replace("‘", "'")


def normalize_doi(value):
    value = re.sub(r"\s+", "", value).lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", value)
    if not value.startswith("10."):
        raise ValueError("A processed positive record has a missing or invalid DOI.")
    return value


def canonical_modulator(value):
    """Group known aliases; preserve mixtures and unknown identities."""
    value = chemical_text(value).lower()
    if not value or "+" in value or re.search(r"\b(?:and|or|buffer)\b", value):
        return value
    stripped = re.sub(
        r"^(?:(?:glacial|concentrated|aqueous|dilute)\s+|\d+(?:\.\d+)?\s*(?:%|m)\s+)+",
        "", value,
    )
    for name, aliases in MODULATOR_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if stripped == alias:
                return name
            if not stripped.startswith(alias):
                continue
            suffix = stripped[len(alias):]
            if not suffix or suffix[0] not in " (,":
                continue
            bare = re.sub(r"\([^()]*\)", "", suffix).strip(" ,")
            if not bare or re.match(
                r"^(?:aqueous|solution|glacial|concentrated|dilute|diluted|aq\.?|"
                r"for pH|to adjust pH|pH adjust|adjusted to pH|stock solution|"
                r"in (?:water|h2o|dmf|methanol)|\d)", bare, re.I,
            ):
                return name
    return value


def normalize_stability(value):
    """Normalize Yes/No/Not reported labels."""
    label = " ".join(value.split()).lower()
    if label in ("", "not_reported"):
        return "Not reported"
    if label == "yes":
        return "Yes"
    if label == "no":
        return "No"
    raise ValueError("Unrecognized stability label: " + repr(value))


def numeric(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def eligible(value, field):
    if not np.isfinite(value):
        return False
    return value >= (-273.15 if field == "tga_decomposition_temp_c" else 0)


def load_records(project_root):
    """Verify pinned inputs and normalize the distributed processed records.

    Source row numbers are 1-based data-row indices, excluding the header. The
    source table is read without modifying its chemical or numeric values.
    """
    root = Path(project_root)
    inputs = root / "docs" / "dataset_analysis" / "data"
    provenance = json.loads((inputs / "provenance.json").read_text(encoding="utf-8"))
    for item in provenance["repository_inputs"]:
        path = root / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError("Input checksum changed; review the analysis provenance: " + item["path"])
    source = read_csv(root / "data" / "processed_data" / "processed_positive.csv")
    records = []
    for number, row in enumerate(source, 1):
        record = {"source_row_1based": number, "doi": normalize_doi(row["doi"])}
        for field in ("metal_1", "linker_1", "solvent_main"):
            record[field] = chemical_text(row[field])
        record["modulator_1"] = canonical_modulator(row["modulator_1"])
        record["topology_code"] = " ".join(row["topology_code"].split()).lower()
        for field, _ in STABILITY_FIELDS:
            record[field] = normalize_stability(row[field])
        for _, field, _, _, _ in PROPERTIES:
            record[field] = numeric(row[field])
        records.append(record)
    if len(records) != provenance["cohort_records"]:
        raise ValueError("Processed positive cohort size changed.")
    if len({row["doi"] for row in records}) != provenance["cohort_unique_dois"]:
        raise ValueError("Processed positive DOI cohort changed.")
    return records


def category_counts(records, field, by_doi=False):
    """Count primary labels, ranking record and DOI frequencies independently."""
    if by_doi:
        members = defaultdict(set)
        for row in records:
            if row[field]:
                members[row[field]].add(row["doi"])
        counts = {label: len(dois) for label, dois in members.items()}
    else:
        counts = Counter(row[field] for row in records if row[field])
    return [{"rank": i, "label": label, "count": int(count)}
            for i, (label, count) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0])), 1)]


def property_values(records, field, by_doi=False):
    """Use one median per DOI when requested; otherwise retain every eligible row."""
    valid = [row for row in records if eligible(row[field], field)]
    if not by_doi:
        return np.array([row[field] for row in valid], dtype=float)
    groups = defaultdict(list)
    for row in valid:
        groups[row["doi"]].append(row[field])
    return np.array([np.median(groups[doi]) for doi in sorted(groups)], dtype=float)


def stability_counts(records, field, by_doi=False):
    """Count each DOI in every represented stability category, including missing."""
    counts = {row["label"]: row["count"] for row in category_counts(records, field, by_doi)}
    denominator = len({row["doi"] for row in records}) if by_doi else len(records)
    return [{"field": field, "label": label, "count": counts.get(label, 0),
             "denominator": denominator, "percent_of_cohort": 100 * counts.get(label, 0) / denominator}
            for label in STABILITY_LABELS]


def summarize(records):
    """Return coverage, complete rankings, and numeric summaries used by the plots."""
    n = len(records)
    summary = {"cohort_records": n, "cohort_unique_dois": len({r["doi"] for r in records}),
               "cohort": "Processed positive synthesis records before dataset-preparation filtering",
               "categories": {}, "properties": {}, "stability": {}}
    for figure, field, _, label, top_n in CATEGORIES:
        reported = [r for r in records if r[field]]
        summary["categories"][field] = {
            "figure": figure, "label": label, "top_n": top_n,
            "reported_records": len(reported), "coverage_percent": 100 * len(reported) / n,
            "unique_dois": len({r["doi"] for r in reported}),
            "records": category_counts(records, field),
            "dois": category_counts(records, field, by_doi=True),
        }
    for figure, field, _, label, scale in PROPERTIES:
        entry = {"figure": figure, "label": label, "scale": scale}
        for key, is_doi in (("records", False), ("dois", True)):
            values = property_values(records, field, by_doi=is_doi)
            entry[key] = {"n": len(values), "minimum": float(values.min()),
                          "maximum": float(values.max()), "median": float(np.median(values)),
                          "mean": float(values.mean()), "sum": float(values.sum())}
        entry["coverage_percent"] = 100 * entry["records"]["n"] / n
        summary["properties"][field] = entry
    for field, label in STABILITY_FIELDS:
        summary["stability"][field] = {
            "figure": "D9", "label": label,
            "records": stability_counts(records, field),
            "dois": stability_counts(records, field, by_doi=True),
            "doi_categories_overlap": True,
        }
    return summary


def validate_against_reference(summary, project_root):
    """Check every historical category count and both numeric plotting units."""
    path = Path(project_root) / "docs" / "dataset_analysis" / "data" / "expected_statistics.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    for field, entry in summary["categories"].items():
        for unit in ("records", "dois"):
            if entry[unit] != expected["categories"][field][unit]:
                raise ValueError("Category count differs from the reference: " + field + "/" + unit)
    for field, entry in summary["properties"].items():
        for unit in ("records", "dois"):
            for statistic, value in entry[unit].items():
                if not np.isclose(value, expected["properties"][field][unit][statistic], rtol=1e-12, atol=1e-9):
                    raise ValueError("Property statistic changed: " + field + "/" + unit + "/" + statistic)
    for field, entry in summary["stability"].items():
        for unit in ("records", "dois"):
            for actual, reference in zip(entry[unit], expected["stability"][field][unit]):
                for key in ("field", "label", "count", "denominator"):
                    if actual[key] != reference[key]:
                        raise ValueError("Stability category changed: " + field + "/" + unit + "/" + key)
                if not np.isclose(actual["percent_of_cohort"], reference["percent_of_cohort"], rtol=1e-12):
                    raise ValueError("Stability percentage changed: " + field + "/" + unit)
    return True


def configure_style():
    """Use Arial where installed and an explicit portable sans-serif fallback."""
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = next((name for name in ("Arial", "Liberation Sans", "DejaVu Sans") if name in available), "DejaVu Sans")
    plt.rcParams.update({
        "font.family": family, "font.size": 9, "axes.labelsize": 9,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 8,
        "axes.linewidth": .6, "xtick.major.width": .6, "ytick.major.width": .6,
        "xtick.major.size": 3, "ytick.major.size": 3,
        "text.color": "#222222", "axes.labelcolor": "#222222", "axes.edgecolor": "#333333",
        "xtick.color": "#222222", "ytick.color": "#222222", "axes.grid": False,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "mathtext.fontset": "custom", "mathtext.rm": family,
        "mathtext.it": family + ":italic", "mathtext.bf": family + ":bold", "mathtext.default": "regular",
    })
    return family


def gradient(count, by_doi=False):
    from matplotlib.colors import LinearSegmentedColormap, to_hex
    colors = ["#285953", "#63948B", "#8D969E"] if by_doi else ["#A2C4F1", "#B6E2DC"]
    cmap = LinearSegmentedColormap.from_list("ranked", colors)
    return [to_hex(cmap(value)) for value in np.linspace(0, 1, count)]


def format_label(label, field):
    if field == "metal_1":
        return re.sub(r"(?<=[A-Za-z\)])\d+", lambda match: "$_{" + match.group(0) + "}$", label)
    width = 42 if field == "linker_1" else 30
    label = label.replace("\u00a0", " ")
    if ")bis(" in label and len(label) > width:
        return label.replace(")bis(", ")\nbis(", 1)
    return "\n".join(textwrap.wrap(label, width=width, break_long_words=False, break_on_hyphens=True))


def count_axis(ax, direction="y", bins=5):
    from matplotlib.ticker import MaxNLocator, StrMethodFormatter
    axis = getattr(ax, direction + "axis")
    axis.set_major_locator(MaxNLocator(nbins=bins, integer=True))
    axis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.tick_params(direction="out", pad=3)


def slot_axis(fig, offset, height, rectangle):
    left, bottom, width, axis_height = rectangle
    total = fig.get_size_inches()[1]
    return fig.add_axes([left, (offset + bottom * height) / total, width, axis_height * height / total])


def label_panel(fig, offset, height, is_doi):
    fig.text(.02, (offset + height - .07) / fig.get_size_inches()[1], "b" if is_doi else "a",
             ha="left", va="top", fontsize=12, fontweight="bold")


def plot_category(records, field, *, combined=True):
    """Return a six-inch-wide category figure with records above unique DOIs."""
    import matplotlib.pyplot as plt
    spec = next(spec for spec in CATEGORIES if spec[1] == field)
    top_n = spec[-1]
    rankings = [category_counts(records, field, by_doi=flag)[:top_n] for flag in (False, True)]
    labels = [[format_label(row["label"], field) for row in ranking] for ranking in rankings]
    row_sizes = [np.array([.225 + .14 * item.count("\n") for item in panel]) for panel in labels]
    height = round(max(3, max(float(sizes.sum()) for sizes in row_sizes) + .85), 4)
    left = {"metal_1": .32, "linker_1": .465, "topology_code": .15}.get(field, .41)
    fig = plt.figure(figsize=(6, height * (2 if combined else 1)))
    slots = [(height, False), (0, True)] if combined else [(0, False)]
    for offset, is_doi in slots:
        index = int(is_doi)
        values = np.array([row["count"] for row in rankings[index]])
        sizes = row_sizes[index]
        positions = np.cumsum(sizes) - sizes / 2
        ax = slot_axis(fig, offset, height, [left, .47 / height, .965 - left, (height - .87) / height])
        ax.barh(positions, values, height=.162, color=gradient(top_n, is_doi), edgecolor="none")
        ax.set_yticks(positions, labels=labels[index], fontsize=8)
        ax.set_ylim(sizes.sum() + .035, -.035)
        ax.set_xlim(0, values.max() * 1.20)
        ax.tick_params(axis="y", length=0, pad=5)
        for position, value in zip(positions, values):
            ax.text(value + values.max() * .018, position, f"{value:,}", va="center", ha="left", fontsize=8)
        ax.set_xlabel("Unique DOIs" if is_doi else "Synthesis records", labelpad=5)
        count_axis(ax, "x", bins=4)
        if combined:
            label_panel(fig, offset, height, is_doi)
    return fig


def property_bins(records, field):
    values = property_values(records, field)
    return np.linspace(min(0, values.min()), np.nextafter(values.max(), np.inf), 41)


def plot_property(records, field, *, combined=True):
    """Return a property histogram using identical bins for both counting units."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, MaxNLocator, StrMethodFormatter
    _, _, _, xlabel, scale = next(spec for spec in PROPERTIES if spec[1] == field)
    edges = property_bins(records, field)
    height = 3.45
    fig = plt.figure(figsize=(6, height * (2 if combined else 1)))
    slots = [(height, False), (0, True)] if combined else [(0, False)]
    for offset, is_doi in slots:
        values = property_values(records, field, by_doi=is_doi)
        counts, _ = np.histogram(values, bins=edges)
        if counts.sum() != len(values):
            raise ValueError("A numeric histogram lost eligible observations.")
        ax = slot_axis(fig, offset, height, [.105, .18, .875, .69])
        ax.bar(edges[:-1], counts, width=np.diff(edges), align="edge",
               color="#A2C4F1" if is_doi else "#63948B", edgecolor="#285953", linewidth=.35)
        ax.set_xlim(edges[0], edges[-1])
        ax.set_ylim(0, counts.max() * 1.18)
        ax.set_xscale(scale)
        if scale == "log":
            ax.xaxis.set_major_locator(FixedLocator([1, 10, 100, 1000]))
            ax.minorticks_off()
        else:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel(xlabel, labelpad=5)
        ax.set_ylabel("Unique DOIs" if is_doi else "Synthesis records", labelpad=5)
        count_axis(ax, "y", bins=5)
        average = float(values.mean())
        ax.axvline(average, color="#222222", linewidth=1, linestyle=(0, (4, 3)), zorder=5)
        ax.text(.96, .965, f"Mean = {average:,.1f}", transform=ax.transAxes,
                ha="right", va="top", fontsize=8)
        if combined:
            label_panel(fig, offset, height, is_doi)
    return fig


def stability_break_marks(ax, upper_axis):
    """Draw diagonal marks for the omitted count interval."""
    from matplotlib.patches import Polygon
    y = 0 if upper_axis else 1
    width_in = ax.get_position().width * ax.figure.get_size_inches()[0]
    height_in = ax.get_position().height * ax.figure.get_size_inches()[1]
    dx, dy = .026 / width_in, .026 / height_in
    ax.plot([-dx, dx], [y - dy, y + dy], transform=ax.transAxes,
            color="#222222", linewidth=.75, clip_on=False, zorder=5)
    left, right = 2 - .325, 2 + .325
    rise = .065 / height_in
    if upper_axis:
        line_y = [0, rise]
        mask = [(left, 0), (right, 0), (right, rise)]
    else:
        line_y = [1 - rise, 1]
        mask = [(left, 1 - rise), (left, 1), (right, 1)]
    transform = ax.get_xaxis_transform()
    ax.add_patch(Polygon(mask, closed=True, facecolor="white", edgecolor="none", transform=transform, zorder=4))
    ax.plot([left, right], line_y, transform=transform, color="#222222",
            linewidth=.65, clip_on=False, zorder=5)


def plot_stability(records, *, combined=True):
    """Plot air/water side by side, with record panels above DOI-presence panels."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, StrMethodFormatter
    height = 4.2
    fig = plt.figure(figsize=(6, height * (2 if combined else 1)))
    slots = [(height, False), (0, True)] if combined else [(0, False)]
    for offset, is_doi in slots:
        low, high = ([0, 950], [3600, 4550]) if is_doi else ([0, 1800], [12800, 15000])
        colors = ["#63948B", "#8D969E", "#285953"] if is_doi else ["#A2C4F1", "#F2DAE7", "#285953"]
        for j, (field, xlabel) in enumerate(STABILITY_FIELDS):
            rows = stability_counts(records, field, by_doi=is_doi)
            counts = np.array([row["count"] for row in rows], dtype=int)
            denominator = rows[0]["denominator"]
            left = [.105, .612][j]
            upper = slot_axis(fig, offset, height, [left, .645, .368, .225])
            lower = slot_axis(fig, offset, height, [left, .17, .368, .448])
            if not (max(counts[:2]) < low[1] and high[0] < counts[2] < high[1]):
                raise ValueError("Stability counts no longer fit the audited axis-break limits.")
            for ax in (upper, lower):
                ax.bar(np.arange(3), counts, width=.65, color=colors, edgecolor="none")
                ax.set_xlim(-.55, 2.55)
                ax.tick_params(direction="out", labelsize=8)
                ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            lower.set_ylim(*low)
            upper.set_ylim(*high)
            lower.yaxis.set_major_locator(FixedLocator([0, 250, 500, 750] if is_doi else [0, 500, 1000, 1500]))
            upper.yaxis.set_major_locator(FixedLocator([3750, 4000, 4250, 4500] if is_doi else [13000, 14000, 15000]))
            upper.spines["bottom"].set_visible(False)
            lower.spines["top"].set_visible(False)
            upper.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
            lower.set_xticks(np.arange(3), labels=STABILITY_LABELS, fontsize=8)
            lower.tick_params(axis="x", length=0, pad=6)
            lower.set_xlabel(xlabel, labelpad=7)
            if j == 0:
                lower.set_ylabel("Unique DOIs" if is_doi else "Synthesis records", labelpad=7)
            for k, value in enumerate(counts):
                ax = upper if k == 2 else lower
                pad = (high[1] - high[0]) * .027 if k == 2 else low[1] * .033
                ax.text(k, value + pad, f"{value:,}\n({100 * value / denominator:.1f}%)",
                        ha="center", va="bottom", fontsize=8, linespacing=1)
            stability_break_marks(upper, True)
            stability_break_marks(lower, False)
        if combined:
            label_panel(fig, offset, height, is_doi)
        else:
            fig.text(.02, .985, "a", ha="left", va="top", fontsize=12, fontweight="bold")
            fig.text(.535, .985, "b", ha="left", va="top", fontsize=12, fontweight="bold")
    return fig


def export_figure(fig, path, dpi=600):
    """Preserve exact physical width and reject titles or clipped axis labels."""
    if not np.isclose(fig.get_size_inches()[0], 6):
        raise ValueError("Dataset figures must be six inches wide.")
    if any(ax.get_title() for ax in fig.axes) or fig._suptitle is not None:
        raise ValueError("Figure captions belong outside the artwork.")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in fig.axes:
        bounds = ax.get_tightbbox(renderer)
        if bounds.x0 < -.5 or bounds.y0 < -.5 or bounds.x1 > fig.bbox.x1 + .5 or bounds.y1 > fig.bbox.y1 + .5:
            raise ValueError("Figure labels extend outside the canvas: " + Path(path).name)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)


def generate_outputs(records, output_dir, *, dpi=600):
    """Write both PNG versions, all category counts, histogram bins, and summaries."""
    import matplotlib.pyplot as plt
    output = Path(output_dir)
    tables = output / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    font = configure_style()
    summary = summarize(records)
    files = []
    for specs, draw in ((CATEGORIES, plot_category), (PROPERTIES, plot_property)):
        for figure, field, stem, _, _ in specs:
            for combined, folder in VARIANTS.items():
                fig = draw(records, field, combined=combined)
                relative = Path("figures") / folder / ("Figure_" + figure + "_" + stem + ".png")
                export_figure(fig, output / relative, dpi=dpi)
                files.append({"path": relative.as_posix(), "sha256": sha256(output / relative),
                              "width_inches": 6, "height_inches": float(fig.get_size_inches()[1]), "dpi": dpi})
                plt.close(fig)
    for combined, folder in VARIANTS.items():
        fig = plot_stability(records, combined=combined)
        relative = Path("figures") / folder / "Figure_D9_air_water_stability.png"
        export_figure(fig, output / relative, dpi=dpi)
        files.append({"path": relative.as_posix(), "sha256": sha256(output / relative),
                      "width_inches": 6, "height_inches": float(fig.get_size_inches()[1]), "dpi": dpi})
        plt.close(fig)
    for _, field, _, _, _ in CATEGORIES:
        for by_doi in (False, True):
            suffix = "dois" if by_doi else "records"
            write_csv(tables / (field + "_" + suffix + ".csv"), category_counts(records, field, by_doi),
                      ["rank", "label", "count"])
    for _, field, _, _, _ in PROPERTIES:
        edges = property_bins(records, field)
        for by_doi in (False, True):
            counts, _ = np.histogram(property_values(records, field, by_doi), bins=edges)
            rows = [{"bin_left": left, "bin_right": right, "count": int(count)}
                    for left, right, count in zip(edges[:-1], edges[1:], counts)]
            suffix = "dois" if by_doi else "records"
            write_csv(tables / (field + "_" + suffix + "_bins.csv"), rows, ["bin_left", "bin_right", "count"])
    for by_doi in (False, True):
        rows = [row for field, _ in STABILITY_FIELDS for row in stability_counts(records, field, by_doi)]
        suffix = "dois" if by_doi else "records"
        write_csv(tables / ("stability_" + suffix + ".csv"), rows,
                  ["field", "label", "count", "denominator", "percent_of_cohort"])
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {"font": font, "label_font_pt": 8, "axis_font_pt": 9, "panel_font_pt": 12,
                "panel_order": "a: synthesis records above b: unique DOIs",
                "doi_category_gradient": ["#285953", "#63948B", "#8D969E"],
                "property_doi_reduction": "median of eligible values per DOI",
                "stability_doi_counting": "Category presence; one DOI can belong to several labels, including Not reported",
                "stability_axis_breaks": {"records": [1800, 12800], "dois": [950, 3600]},
                "stability_axis_break_style": "parallel diagonal cuts on the bar and matching count-axis marks",
                "figures": files}
    (output / "figure_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return summary, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="MOFinder checkout root")
    parser.add_argument("--output", type=Path, default=Path("results/dataset_analysis"),
                        help="Output directory, relative to project root unless absolute")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--check-only", action="store_true", help="Verify inputs and statistics without plotting")
    args = parser.parse_args(argv)
    records = load_records(args.project_root)
    summary = summarize(records)
    validate_against_reference(summary, args.project_root)
    if args.check_only:
        print("Verified category counts and numeric summaries.")
        return
    output = args.output if args.output.is_absolute() else args.project_root / args.output
    _, manifest = generate_outputs(records, output, dpi=args.dpi)
    print(f"Generated {len(manifest['figures'])} PNGs from {len(records):,} positive synthesis records.")


if __name__ == "__main__":
    main()
