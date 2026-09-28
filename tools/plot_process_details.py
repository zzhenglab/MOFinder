#!/usr/bin/env python3
"""Plot and summarize cleaned process-control CSVs without changing their rows.

Requires matplotlib, numpy, and pandas. Run from any working directory:
    python tools/plot_process_details.py --help

All category plots retain every category. DOI categories may overlap within a
publication; numeric DOI distributions use one within-DOI median per cohort.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import textwrap
from xml.sax.saxutils import escape
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, StrMethodFormatter
import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/processed_data/with_process_details"
COLORS = {"positive": "#A2C4F1", "negative": "#F2DAE7"}
FIELDS = ("vessel_type", "vessel_volume", "stirring")
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
    frame["volume_ml"] = pd.to_numeric(frame.vessel_volume, errors="coerce")
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
               "resolved_coverage_rule": "Numeric positive finite capacity; categorical values excluding Not reported, Ambiguous, Unclear, Unclear / ambiguous, Unresolved vessel description, and Vessel (type not reported)."}
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
            "volume_nonnumeric_labels": frame.loc[~valid, "vessel_volume"].value_counts().to_dict(),
        }
        for field in FIELDS:
            if field == "vessel_volume":
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


def add_legend(fig):
    fig.legend(handles=[Patch(facecolor=COLORS[k], edgecolor="#777777", linewidth=.3,
                              label=k.capitalize()) for k in COLORS],
               loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.57, .998))


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
    for ext in ("png", "pdf", "svg"):
        fig.savefig(folder / f"{stem}.{ext}", dpi=dpi)
    plt.close(fig)


def plot_categories(counts: pd.DataFrame, field: str, out: Path, dpi: int):
    subset = counts[counts.field.eq(field)]
    order = subset.groupby("category").records.sum().sort_values(ascending=False).index.tolist()
    # Put explicitly missing/ambiguous categories at the end while retaining
    # them individually; all resolved categories are ranked on pooled rows.
    unavailable = [x for x in order if x.casefold() in UNRESOLVED_CATEGORIES]
    order = [x for x in order if x not in unavailable] + unavailable
    labels = [textwrap.fill(x, width=27, break_long_words=False) for x in order]
    height = max(3.0, .38 * len(order) + 1.0)
    for combined in (False, True):
        ncols = 2 if combined else 1
        fig, axes = plt.subplots(1, ncols, figsize=(6, height), squeeze=False, sharey=True)
        axes = axes[0]
        fig.subplots_adjust(left=.33, right=.985, bottom=.52 / height, top=1 - .45 / height,
                            wspace=.17 if combined else 0)
        metrics = ["records", "unique_dois"] if combined else ["records"]
        for idx, (ax, metric) in enumerate(zip(axes, metrics)):
            max_count = 0
            for offset, label in ((-.19, "positive"), (.19, "negative")):
                values = subset[subset.dataset.eq(label)].set_index("category")[metric].reindex(order, fill_value=0)
                max_count = max(max_count, int(values.max()))
                ax.barh(np.arange(len(order)) + offset, values, height=.35,
                        color=COLORS[label], edgecolor="#777777", linewidth=.3)
            ax.set_xlim(0, max(max_count * 1.06, 1))
            ax.set_yticks(np.arange(len(order)), labels if idx == 0 else [])
            ax.set_xlabel("Synthesis records" if metric == "records" else "Unique DOIs")
            decorate_count_axis(ax)
            if combined:
                ax.text(-.04, 1.0, "ab"[idx], transform=ax.transAxes, fontsize=12,
                        fontweight="bold", ha="right", va="bottom")
        # Shared-axis label setting must happen after the right subplot setup.
        axes[0].set_yticks(np.arange(len(order)), labels)
        for ax in axes[1:]:
            ax.tick_params(axis="y", labelleft=False, left=False)
        axes[0].invert_yaxis()
        add_legend(fig)
        variant = "02_records_and_DOI" if combined else "01_synthesis_records"
        save_figure(fig, out / variant, f"process_enrich_{field}", dpi)


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
    bins = volume_bins(frames)
    bin_rows = []
    for combined in (False, True):
        metrics = ["records", "doi_medians"] if combined else ["records"]
        fig, axes = plt.subplots(1, len(metrics), figsize=(6, 2.9), squeeze=False)
        axes = axes[0]
        fig.subplots_adjust(left=.10, right=.96, bottom=.24, top=.85, wspace=.34)
        for idx, (ax, metric) in enumerate(zip(axes, metrics)):
            medians = []
            for label, frame in frames.items():
                values = frame.volume_ml.dropna() if metric == "records" else frame[
                    frame.doi_normalized.ne("")].groupby("doi_normalized").volume_ml.median().dropna()
                ax.hist(values, bins=bins, color=COLORS[label], alpha=.70,
                        edgecolor="#777777", linewidth=.3, histtype="stepfilled")
                median = float(values.median()) if len(values) else float("nan")
                medians.append((label, median))
                if combined:
                    ns, _ = np.histogram(values, bins)
                    if int(ns.sum()) != len(values):
                        raise ValueError("Vessel-volume histogram did not retain every numeric value")
                    bin_rows.extend({"dataset": label, "metric": metric, "bin_left_ml": float(a),
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
            ax.text(.98, .96, "\n".join(f"{label.capitalize()} median = {median:g}" for label, median in medians),
                    transform=ax.transAxes, fontsize=8, ha="right", va="top")
            if combined:
                ax.text(-.25, 1.04, "ab"[idx], transform=ax.transAxes, fontsize=12,
                        fontweight="bold", ha="left", va="bottom")
        add_legend(fig)
        variant = "02_records_and_DOI" if combined else "01_synthesis_records"
        save_figure(fig, out / variant, "process_enrich_vessel_volume", dpi)
    return pd.DataFrame(bin_rows)


def captions(summary: dict) -> str:
    p, n = summary["datasets"]["positive"], summary["datasets"]["negative"]
    base = (f"Positive and inferred negative cohorts contain {p['records']:,} and {n['records']:,} records, "
            f"respectively. Blue and pink indicate positive and inferred negative records, respectively.")
    return "\n\n".join([
        "# Process-detail figure captions\n\nFigure numbers are placeholders pending SI placement. Main files use the two-panel version; records-only variants are also supplied.",
        "**Figure Sxx. Cleaned reaction-vessel categories in the process-detail control dataset.** "
        "a, Synthesis-record counts. b, Unique DOI counts for each category. " + base +
        " Categories are ordered by pooled record frequency, with missing or ambiguous categories displayed last. "
        "A DOI can contribute to multiple vessel categories, so DOI counts are not mutually exclusive. Every cleaned category is shown.",
        "**Figure Sxx+1. Reported vessel capacities in the process-detail control dataset.** "
        "a, Histograms of accepted numeric capacities among synthesis records. b, Histograms of the median accepted capacity per DOI within each cohort. "
        "Blue and pink indicate positive and inferred negative records, respectively. Common logarithmically spaced capacity bins include every accepted numeric value; the horizontal axis is logarithmic. "
        f"Panel a includes {p['volume_records']['n']:,} positive and {n['volume_records']['n']:,} negative records; panel b includes "
        f"{p['volume_doi_medians']['n']:,} and {n['volume_doi_medians']['n']:,} DOI medians, respectively. "
        "Not reported and Ambiguous values are excluded from these histograms but retained in the dataset and coverage tables. Annotations give medians in mL.",
        "**Figure Sxx+2. Cleaned stirring descriptions in the process-detail control dataset.** "
        "a, Synthesis-record counts. b, Unique DOI counts for each category. " + base +
        " All categories, including missing and ambiguous descriptions, are retained. A DOI can contribute to multiple categories. "
        "The labels describe the extracted protocol; mention of mixing before heating does not establish agitation throughout crystallization.",
        "For each records-only variant, omit the panel-b sentence and DOI-specific statements from the corresponding caption.",
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
        "The procedure distinguishes vessel bodies from ancillary caps or seals and retains nested or multiple-vessel descriptions explicitly. "
        "Capacity is taken only from an interpretable stated vessel size; solution charges and geometric dimensions are not substituted. "
        "Missing values are encoded as Not reported, while uncertain capacities remain Ambiguous rather than being imputed.",
        f"PTFE-lined autoclaves/pressure vessels are the dominant vessel class ({pct('positive', 'vessel_type', ptfe):.1f}% of positive and "
        f"{pct('negative', 'vessel_type', ptfe):.1f}% of negative records), followed by vials "
        f"({pct('positive', 'vessel_type', 'Vial'):.1f}% and {pct('negative', 'vessel_type', 'Vial'):.1f}%; Figure Sxx). "
        f"Numeric capacities are available for {p['volume_records']['n']:,} positive records "
        f"({p['volume_records']['n'] / p['records'] * 100:.1f}%) and {n['volume_records']['n']:,} negative records "
        f"({n['volume_records']['n'] / n['records'] * 100:.1f}%). Their medians are "
        f"{p['volume_records']['median']:g} and {n['volume_records']['median']:g} mL, respectively, with interquartile ranges "
        f"{p['volume_records']['p25']:g}–{p['volume_records']['p75']:g} and "
        f"{n['volume_records']['p25']:g}–{n['volume_records']['p75']:g} mL (Figure Sxx+1).",
        "Stirring normalization preserves stage information where stated. "
        f"Static/no-stirring descriptions account for {pct('positive', 'stirring', static):.1f}% of positive and "
        f"{pct('negative', 'stirring', static):.1f}% of negative records; stirring before static synthesis accounts for "
        f"{pct('positive', 'stirring', staged):.1f}% and {pct('negative', 'stirring', staged):.1f}%, respectively. "
        f"Stirring is not reported for {pct('positive', 'stirring', 'Not reported'):.1f}% and "
        f"{pct('negative', 'stirring', 'Not reported'):.1f}% (Figure Sxx+2). "
        "Mixing during preparation is not assumed to continue during crystallization. Negative process annotations may be inherited from successful parent protocols and should not be interpreted as independently observed failed experiments.",
        "The figures summarize complete tabular cohorts at record and DOI levels. The enriched training control preserves the standard training/holdout membership and adds only these three features and corresponding prompt instructions. "
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
    links = [("Vessel categories", figure_folder / "process_enrich_vessel_type.pdf"),
             ("Vessel capacities", figure_folder / "process_enrich_vessel_volume.pdf"),
             ("Stirring descriptions", figure_folder / "process_enrich_stirring.pdf"),
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
    parser.add_argument("--output", type=Path, default=REPO / "docs/process_details")
    parser.add_argument("--si-output", type=Path, help="Optional SI output directory for figure copies")
    parser.add_argument("--si-section", type=Path, help="Optional path for a copy of the short Section S5 Markdown draft")
    parser.add_argument("--docx", type=Path, help="Optional path for a text-only Word draft with relative figure links")
    parser.add_argument("--dpi", type=int, default=600)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    font = configure()
    frames = {"positive": read_frame(args.positive), "negative": read_frame(args.negative)}
    summary, counts, coverage = summarize(frames)
    summary["rendering"] = {"width_inches": 6, "font": font, "png_dpi": args.dpi}
    summary["inputs"] = {label: {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for label, path in (("positive", args.positive), ("negative", args.negative))}
    counts.to_csv(args.output / "category_counts.csv", index=False)
    coverage.to_csv(args.output / "field_coverage.csv", index=False)
    (args.output / "distribution_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    figures = args.output / "figures"
    for field in ("vessel_type", "stirring"):
        plot_categories(counts, field, figures, args.dpi)
    plot_volume(frames, figures, args.dpi).to_csv(args.output / "volume_histogram_counts.csv", index=False)
    (args.output / "FIGURE_CAPTIONS.md").write_text(captions(summary), encoding="utf-8")
    section = manuscript_section(summary, counts)
    (args.output / "Section_S5_process_details.md").write_text(section, encoding="utf-8")
    if args.si_section:
        args.si_section.parent.mkdir(parents=True, exist_ok=True)
        args.si_section.write_text(section, encoding="utf-8")
    # The default root filenames always point to the records+DOI version.
    for path in (figures / "02_records_and_DOI").iterdir():
        shutil.copy2(path, figures / path.name)
    if args.si_output:
        for path in figures.rglob("*"):
            if path.is_file():
                destination = args.si_output / path.relative_to(figures)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        (args.si_output / "process_enrich_FIGURE_CAPTIONS.md").write_text(captions(summary), encoding="utf-8")
    if args.docx:
        write_docx(args.docx, section, args.si_output or figures,
                   args.si_output / "process_enrich_FIGURE_CAPTIONS.md" if args.si_output else args.output / "FIGURE_CAPTIONS.md")
    print(json.dumps({"output": str(args.output), "records": {k: len(v) for k, v in frames.items()},
                      "figures": 6, "font": font}, indent=2))


if __name__ == "__main__":
    main()
