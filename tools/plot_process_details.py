#!/usr/bin/env python3
"""Plot and summarize cleaned process-control CSVs without changing their rows.

Requires matplotlib, numpy, and pandas. Run from any working directory:
    python tools/plot_process_details.py --help

Writes only three PNGs to an explicit local output directory. Categories are
read directly from the cleaned CSVs, without additional display-only merging.
DOI categories may overlap within a publication; numeric DOI distributions use
one within-DOI median per cohort.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import textwrap
from xml.sax.saxutils import escape
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, StrMethodFormatter
import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/processed_data/with_process_details"
COLORS = {"records": "#63948B", "unique_dois": "#A2C4F1"}
OUTLINE = "#285953"
FIELDS = ("vessel_type", "vessel_volume_mL", "stirring")
MISSING = {"", "not reported", "not_reported", "unknown", "nan", "none", "n/a"}
UNRESOLVED_CATEGORIES = {"not reported", "ambiguous", "unclear", "unclear / ambiguous",
                         "unresolved vessel description", "vessel (type not reported)"}


def configure() -> str:
    try:
        findfont(FontProperties(family="Arial"), fallback_to_default=False)
        family = "Arial"
    except ValueError:
        family = "DejaVu Sans"
    plt.rcParams.update({
        "font.family": family, "font.size": 9, "axes.labelsize": 9,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
        "axes.linewidth": .6, "xtick.major.width": .6, "ytick.major.width": .6,
        "axes.edgecolor": "#333333", "text.color": "#222222",
        "axes.labelcolor": "#222222", "xtick.color": "#222222",
        "ytick.color": "#222222", "svg.fonttype": "none", "pdf.fonttype": 42,
        "svg.hashsalt": "mofinder-process-detail-control", "savefig.facecolor": "white",
    })
    return family


def normalize_doi(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", value)
    return re.sub(r"^doi\s*:\s*", "", value).strip()


def read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    needed = {"doi", *FIELDS}
    if not needed.issubset(frame.columns):
        raise ValueError(f"{path}: missing columns {sorted(needed - set(frame.columns))}")
    frame = frame.copy()
    frame["doi_normalized"] = frame.doi.map(normalize_doi)
    for field in ("vessel_type", "stirring"):
        frame[field] = frame[field].str.strip()
        frame.loc[frame[field].str.casefold().isin(MISSING), field] = "Not reported"
    frame["volume_ml"] = pd.to_numeric(frame.vessel_volume_mL, errors="coerce")
    frame.loc[~np.isfinite(frame.volume_ml) | (frame.volume_ml <= 0), "volume_ml"] = np.nan
    return frame


def numeric_stats(values: pd.Series) -> dict:
    values = values.dropna()
    if values.empty:
        return {"n": 0}
    return {"n": int(len(values)), "mean": float(values.mean()),
            "p25": float(values.quantile(.25)), "median": float(values.median()),
            "p75": float(values.quantile(.75)), "minimum": float(values.min()),
            "maximum": float(values.max())}


def summarize(frames: dict[str, pd.DataFrame]) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    summary = {"datasets": {}, "doi_rule": "Lowercase; remove DOI URL or doi: prefix; omit blank DOIs from DOI counts.",
               "category_doi_rule": "One count per distinct DOI/category/cohort; a DOI can have multiple categories.",
               "volume_doi_rule": "One median of accepted positive numeric capacities per DOI within each cohort.",
               "resolved_coverage_rule": "Numeric positive finite capacity; categorical values excluding Not reported, Ambiguous, Unclear, Unclear / ambiguous, Unresolved vessel description, and Vessel (type not reported).",
               "consolidation_note": "Categories come directly from the final cleaned inputs. Vessel Not reported includes rare known vessel classes pooled during preparation, so categorical coverage is coverage of retained final categories, not a count of all mentioned vessel types."}
    categories, coverage = [], []
    for label, frame in frames.items():
        doi_frame = frame[frame.doi_normalized.ne("")]
        doi_n = int(doi_frame.doi_normalized.nunique())
        valid = frame.volume_ml.notna()
        numeric_doi = doi_frame.groupby("doi_normalized").volume_ml.median().dropna()
        summary["datasets"][label] = {
            "records": len(frame), "unique_dois": doi_n,
            "records_without_doi": int(frame.doi_normalized.eq("").sum()),
            "volume_records": numeric_stats(frame.volume_ml),
            "volume_doi_medians": numeric_stats(numeric_doi),
            "volume_nonnumeric_labels": frame.loc[~valid, "vessel_volume_mL"].value_counts().to_dict(),
        }
        for field in FIELDS:
            if field == "vessel_volume_mL":
                reported = valid
            else:
                # Missing and ambiguity labels remain plotted but are not
                # counted as resolved feature values in coverage statistics.
                reported = ~frame[field].str.casefold().isin(UNRESOLVED_CATEGORIES)
            doi_present = int(frame.loc[reported & frame.doi_normalized.ne(""), "doi_normalized"].nunique())
            coverage.append({"dataset": label, "field": field,
                             "resolved_records": int(reported.sum()), "total_records": len(frame),
                             "resolved_percent": float(reported.mean() * 100),
                             "dois_with_resolved_value": doi_present, "total_dois": doi_n})
        for field in ("vessel_type", "stirring"):
            record_counts = frame[field].value_counts()
            doi_counts = doi_frame[["doi_normalized", field]].drop_duplicates()[field].value_counts()
            for category, n in record_counts.items():
                categories.append({"dataset": label, "field": field, "category": category,
                                   "records": int(n), "record_percent": float(n / len(frame) * 100),
                                   "unique_dois": int(doi_counts.get(category, 0)),
                                   "doi_percent": float(doi_counts.get(category, 0) / doi_n * 100) if doi_n else 0.0})
    return summary, pd.DataFrame(categories), pd.DataFrame(coverage)


def decorate_count_axis(ax, axis="x"):
    target = ax.xaxis if axis == "x" else ax.yaxis
    target.set_major_locator(MaxNLocator(nbins=4, integer=True))
    target.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", pad=3)


def panel_axes(fig, row, panels, left, bottom=.18, height=.75):
    """Match the existing SI layout: synthesis records above unique DOIs."""
    ax = fig.add_axes([left, (panels - row - 1 + bottom) / panels,
                       .97 - left, height / panels])
    if panels == 2:
        fig.text(.03, (panels - row - .025) / panels, "ab"[row],
                 fontsize=12, fontweight="bold", ha="left", va="top")
    return ax


def check_layout(fig):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in fig.axes:
        extent = ax.get_tightbbox(renderer)
        if extent.x0 < -1 or extent.y0 < -1 or extent.x1 > fig.bbox.x1 + 1 or extent.y1 > fig.bbox.y1 + 1:
            raise ValueError(f"Figure labels exceed the canvas: {extent}")


def save_figure(fig, folder: Path, stem: str, dpi: int):
    folder.mkdir(parents=True, exist_ok=True)
    check_layout(fig)
    fig.savefig(folder / f"{stem}.png", dpi=dpi)
    plt.close(fig)


def plot_categories(counts: pd.DataFrame, field: str, out: Path, dpi: int):
    subset = counts[counts.field.eq(field) & counts.dataset.eq("positive")].set_index("category")
    order = subset.records.sort_values(ascending=False, kind="stable").index.tolist()
    # Put explicitly missing/ambiguous categories at the end while retaining
    # them individually; resolved categories are ranked on positive records.
    unavailable = [x for x in order if x.casefold() in UNRESOLVED_CATEGORIES]
    order = [x for x in order if x not in unavailable] + unavailable
    labels = [textwrap.fill(x, width=40, break_long_words=False) for x in order]
    line_counts = np.array([label.count("\n") + 1 for label in labels])
    # Give multi-line categories more room, while keeping 8-pt labels legible.
    row_heights = .13 * line_counts + .055
    positions = np.cumsum(row_heights) - row_heights / 2
    plot_height = float(row_heights.sum())
    height = max(1.8, plot_height + .8)
    fig = plt.figure(figsize=(6, height * 2))
    for idx, metric in enumerate(("records", "unique_dois")):
        ax = panel_axes(fig, idx, 2, .46, bottom=.48 / height,
                        height=plot_height / height)
        values = subset[metric].reindex(order)
        max_count = int(values.max())
        ax.barh(positions, values, height=.12, color=COLORS[metric],
                edgecolor=OUTLINE, linewidth=.35)
        for y, value in zip(positions, values):
            ax.text(value + max_count * .018, y, f"{int(value):,}",
                    ha="left", va="center", fontsize=8)
        ax.set_xlim(0, max(max_count * 1.22, 1))
        ax.set_ylim(plot_height + .025, -.025)
        ax.set_yticks(positions, labels, fontsize=8)
        ax.set_xlabel("Synthesis records" if metric == "records" else "Unique DOIs")
        decorate_count_axis(ax)
    save_figure(fig, out, f"process_enrich_{field}", dpi)


def volume_bins(frames: dict[str, pd.DataFrame]) -> np.ndarray:
    values = pd.concat([frame.volume_ml.dropna() for frame in frames.values()])
    if values.empty:
        return np.geomspace(.1, 100, 31)
    low, high = math.floor(math.log10(values.min())), math.ceil(math.log10(values.max()))
    if low == high:
        high += 1
    return np.geomspace(10 ** low, 10 ** high * 1.00000001, 6 * (high - low) + 1)


def volume_tick(value, pos):
    if value < 1:
        return f"{value:g}"
    if value < 1000:
        return f"{value:g}"
    return f"{value / 1000:g}k"


def plot_volume(frames: dict[str, pd.DataFrame], out: Path, dpi: int) -> pd.DataFrame:
    frame = frames["positive"]
    bins = volume_bins({"positive": frame})
    bin_rows = []
    fig = plt.figure(figsize=(6, 2.8 * 2))
    for idx, metric in enumerate(("records", "doi_medians")):
        ax = panel_axes(fig, idx, 2, .135, bottom=.22, height=.71)
        values = frame.volume_ml.dropna() if metric == "records" else frame[
            frame.doi_normalized.ne("")].groupby("doi_normalized").volume_ml.median().dropna()
        ns, _ = np.histogram(values, bins)
        if int(ns.sum()) != len(values):
            raise ValueError("Vessel-volume histogram did not retain every numeric value")
        ax.hist(values, bins=bins, color=COLORS["records" if idx == 0 else "unique_dois"],
                edgecolor=OUTLINE, linewidth=.45)
        mean = float(values.mean()) if len(values) else float("nan")
        ax.axvline(mean, color="#222222", linestyle=(0, (4, 3)), linewidth=.9)
        ax.text(.97, .95, f"Mean = {mean:,.2f}", transform=ax.transAxes,
                fontsize=8, ha="right", va="top")
        bin_rows.extend({"dataset": "positive", "metric": metric, "bin_left_ml": float(a),
                         "bin_right_ml": float(b), "count": int(n)}
                        for a, b, n in zip(bins[:-1], bins[1:], ns))
        ax.set_xscale("log")
        ax.set_xlim(bins[0], bins[-1])
        ax.xaxis.set_major_locator(FixedLocator(10.0 ** np.arange(math.floor(math.log10(bins[0])),
                                                                 math.floor(math.log10(bins[-1])) + 1)))
        ax.xaxis.set_major_formatter(FuncFormatter(volume_tick))
        ax.minorticks_off()
        ax.set_xlabel("Vessel capacity (mL)")
        ax.set_ylabel("Synthesis records" if metric == "records" else "Unique DOIs")
        decorate_count_axis(ax, "y")
    save_figure(fig, out, "process_enrich_vessel_volume", dpi)
    return pd.DataFrame(bin_rows)


def captions(summary: dict) -> str:
    return "\n\n".join([
        "# Process-detail figure captions\n\nAll panels describe the positive dataset. Figure numbers remain placeholders pending SI placement. Each PNG has synthesis records above unique DOIs, using the same final categories as the enriched CSVs and training inputs.",
        "**Figure Sxx. Frequencies of cleaned reaction-vessel categories in the positive dataset, including unreported values.** "
        "a, Synthesis-record counts. b, Unique DOI counts per category; a paper can contribute to multiple categories. Numbers beside bars give counts.",
        "**Figure Sxx+1. Distributions of reported vessel capacities in the positive dataset, with logarithmic capacity axes and dashed arithmetic-mean lines.** "
        "a, Accepted numeric capacities among synthesis records. b, Median accepted capacity per unique DOI.",
        "**Figure Sxx+2. Frequencies of cleaned stirring descriptions in the positive dataset, including unreported values.** "
        "a, Synthesis-record counts. b, Unique DOI counts per category; a paper can contribute to multiple categories. Numbers beside bars give counts.",
        "Records use muted teal; unique DOIs use light blue. Vessel Not reported includes unspecified vessel types and known vessel classes with fewer than 10 positive records. Reported-agitation classes with fewer than 50 positive records are pooled as Other reported agitation; descriptions without a uniquely classifiable stirring state are Not reported. These final dataset categories are used directly for plotting. Counts, methods, and provenance are stored separately from the PNGs.",
    ]) + "\n"


def manuscript_section(summary: dict, counts: pd.DataFrame) -> str:
    p, n = summary["datasets"]["positive"], summary["datasets"]["negative"]

    def count(dataset, field, category):
        return int(counts.loc[counts.dataset.eq(dataset) & counts.field.eq(field) &
                              counts.category.eq(category), "records"].sum())

    def pct(dataset, field, category):
        return count(dataset, field, category) / summary["datasets"][dataset]["records"] * 100

    ptfe = "PTFE-lined autoclave / pressure vessel"
    static = "Static / no stirring"
    staged = "Stirred before static synthesis"
    text = [
        "## Process-detail control dataset",
        "To assess whether reported process conditions provide additional predictive information, we prepared an auxiliary process-detail dataset alongside the primary eight-variable representation. "
        f"The enriched tables retain all {p['records']:,} positive and {n['records']:,} inferred negative records and add three cleaned features: vessel type, vessel capacity (mL), and stirring description. "
        "Original descriptions are preserved for traceability; missing process information does not cause row exclusion.",
        "Vessel descriptions were normalized across spelling, punctuation, and unit variants, with low-frequency and unresolved entries audited. "
        "The procedure distinguishes vessel bodies from ancillary caps or seals; material-only names use glass, polymer, or metal vessel. "
        "Unspecified vessel types and vessel classes with fewer than 10 positive records are encoded as Not reported. "
        "Capacity is taken only from an interpretable stated vessel size; solution charges and geometric dimensions are not substituted. "
        "Thus, vessel Not reported also includes rare known classes. Missing values are encoded as Not reported, while uncertain capacities remain Ambiguous rather than being imputed.",
        f"In the positive dataset, PTFE-lined autoclaves/pressure vessels are the dominant vessel class "
        f"({pct('positive', 'vessel_type', ptfe):.1f}%), followed by vials "
        f"({pct('positive', 'vessel_type', 'Vial'):.1f}%; Figure Sxx). "
        f"Numeric capacities are available for {p['volume_records']['n']:,} positive records "
        f"({p['volume_records']['n'] / p['records'] * 100:.1f}%), with a median of "
        f"{p['volume_records']['median']:g} mL and an interquartile range of "
        f"{p['volume_records']['p25']:g}–{p['volume_records']['p75']:g} mL (Figure Sxx+1).",
        "Stirring normalization preserves stage information where stated; reported-agitation classes with fewer than 50 positive records are consolidated as Other reported agitation "
        f"({count('positive', 'stirring', 'Other reported agitation'):,} records). "
        "Audited descriptions without a uniquely classifiable stirring state are encoded as Not reported. Detailed classifications remain in the audit. "
        f"Static/no-stirring descriptions account for {pct('positive', 'stirring', static):.1f}% of positive records; "
        f"stirring before static synthesis accounts for {pct('positive', 'stirring', staged):.1f}%. "
        f"Stirring is not reported for {pct('positive', 'stirring', 'Not reported'):.1f}% (Figure Sxx+2). "
        "Mixing during preparation is not assumed to continue during crystallization. Negative process annotations may be inherited from successful parent protocols and should not be interpreted as independently observed failed experiments.",
        "The figures summarize the positive tabular cohort at record and DOI levels. Categorical panels count records and distinct DOIs per category; numeric DOI panels use one median per paper. "
        "The enriched training control retains both classes and preserves the standard training/holdout membership, adding only these three features and their names in the system prompt. "
        "Washing and activation remain outside this crystallization-outcome control because they describe downstream processing. These distributions document feature availability; they do not establish a predictive improvement.",
    ]
    return "\n\n".join(text) + "\n"


def write_docx(path: Path, section: str, figure_folder: Path, caption_path: Path):
    """Write a small text-only Word draft using standard Office XML (no extra dependency)."""
    paragraphs = []
    for text in section.strip().split("\n\n"):
        heading = text.startswith("## ")
        text = text.removeprefix("## ")
        properties = '<w:pPr><w:spacing w:after="120"/></w:pPr>'
        run_properties = '<w:rPr><w:b/></w:rPr>' if heading else ''
        paragraphs.append(f'<w:p>{properties}<w:r>{run_properties}<w:t>{escape(text)}</w:t></w:r></w:p>')
    relationships = []
    links = [("Vessel categories", figure_folder / "process_enrich_vessel_type.png"),
             ("Vessel capacities", figure_folder / "process_enrich_vessel_volume.png"),
             ("Stirring descriptions", figure_folder / "process_enrich_stirring.png"),
             ("Figure captions", caption_path)]
    for idx, (label, target) in enumerate(links, start=1):
        relative = os.path.relpath(target.resolve(), path.parent.resolve()).replace("\\", "/")
        relationships.append(f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                             f'Target="{escape(relative, {chr(34): "&quot;"})}" TargetMode="External"/>')
        paragraphs.append(f'<w:p><w:pPr><w:spacing w:after="40"/></w:pPr><w:hyperlink r:id="rId{idx}">'
                          f'<w:r><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr><w:t>{escape(label)}</w:t></w:r>'
                          '</w:hyperlink></w:p>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>' +
                ''.join(paragraphs) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
                '<w:pgMar w:top="1008" w:right="1008" w:bottom="1008" w:left="1008"/></w:sectPr></w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults>'
              '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="20"/></w:rPr></w:rPrDefault>'
              '</w:docDefaults></w:styles>')
    relationships.append('<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    namespace = 'http://schemas.openxmlformats.org/package/2006/relationships'
    package_rels = f'<Relationships xmlns="{namespace}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{namespace}">' + ''.join(relationships) + '</Relationships>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", type=Path, default=DATA / "Process_detail_positive.csv")
    parser.add_argument("--negative", type=Path, default=DATA / "Process_detail_negative.csv")
    parser.add_argument("--output", type=Path, required=True,
                        help="Local directory for exactly three PNG figures")
    parser.add_argument("--report-dir", type=Path,
                        help="Separate directory for count tables, captions and provenance; defaults to a sibling named process_enrich_data")
    parser.add_argument("--si-section", type=Path, help="Optional path for a copy of the short Section S5 Markdown draft")
    parser.add_argument("--docx", type=Path, help="Optional path for a text-only Word draft with relative figure links")
    parser.add_argument("--dpi", type=int, default=600)
    args = parser.parse_args()
    report_dir = args.report_dir or args.output.parent / "process_enrich_data"
    if report_dir.resolve() == args.output.resolve():
        parser.error("--report-dir must differ from --output so that the figure folder contains only PNGs")
    args.output.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    font = configure()
    frames = {"positive": read_frame(args.positive), "negative": read_frame(args.negative)}
    summary, counts, coverage = summarize(frames)
    summary["rendering"] = {"width_inches": 6, "font": font, "png_dpi": args.dpi,
                            "figure_cohort": "positive", "panel_layout": "a records above b unique DOIs",
                            "colors": COLORS, "outline": OUTLINE,
                            "categorical_count_labels": True, "histogram_reference_line": "arithmetic mean"}
    summary["inputs"] = {label: {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for label, path in (("positive", args.positive), ("negative", args.negative))}
    positive_counts = counts[counts.dataset.eq("positive")]
    for field in ("vessel_type", "stirring"):
        if positive_counts.loc[positive_counts.field.eq(field), "records"].sum() != len(frames["positive"]):
            raise ValueError(f"Categorical counts must include every positive record: {field}")
    positive_counts.to_csv(report_dir / "category_counts.csv", index=False)
    coverage[coverage.dataset.eq("positive")].to_csv(report_dir / "field_coverage.csv", index=False)
    (report_dir / "distribution_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for field in ("vessel_type", "stirring"):
        plot_categories(positive_counts, field, args.output, args.dpi)
    plot_volume(frames, args.output, args.dpi).to_csv(report_dir / "volume_histogram_counts.csv", index=False)
    (report_dir / "FIGURE_CAPTIONS.md").write_text(captions(summary), encoding="utf-8")
    methods = REPO / "docs/process_details/DISTRIBUTION_METHODS.md"
    if methods.exists():
        (report_dir / "DISTRIBUTION_METHODS.md").write_text(methods.read_text(encoding="utf-8"), encoding="utf-8")
    section = manuscript_section(summary, counts)
    (report_dir / "Section_S5_process_details.md").write_text(section, encoding="utf-8")
    if args.si_section:
        args.si_section.parent.mkdir(parents=True, exist_ok=True)
        args.si_section.write_text(section, encoding="utf-8")
    if args.docx:
        write_docx(args.docx, section, args.output, report_dir / "FIGURE_CAPTIONS.md")
    print(json.dumps({"output": str(args.output), "reports": str(report_dir),
                      "plotted_records": len(frames["positive"]),
                      "figures": 3, "format": "png", "font": font}, indent=2))


if __name__ == "__main__":
    main()
