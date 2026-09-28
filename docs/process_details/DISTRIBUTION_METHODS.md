# Process-detail control distributions

Run from the repository root:

```powershell
python tools/plot_process_details.py
```

Custom inputs and an output folder can be supplied with `--positive`, `--negative`, and `--output`. `--si-output` optionally copies figures into an external SI figure folder. The plotting step never changes either input CSV.

The figures show the complete cleaned positive process-detail dataset, including rows that the original training preparation may subsequently exclude. They therefore describe the positive tabular dataset, not the smaller matched training and holdout files. Negative records are not plotted. Both positive and negative CSVs and training files remain unchanged by this plotting revision. Missing and ambiguous feature labels remain in the tabular data and categorical plots; numeric capacity plots use only accepted finite capacities greater than zero. No numerical capacity is imputed.

- `figures/process_enrich_vessel_type.*`: all cleaned vessel categories.
- `figures/process_enrich_vessel_volume.*`: vessel capacities in mL, with a logarithmic capacity axis and shared bins.
- `figures/process_enrich_stirring.*`: all cleaned stirring categories, including stage information where available.

Each root figure places panel **a**, synthesis-record counts, above panel **b**, unique DOI counts. The color coding matches the positive-dataset temperature/time plots: records use muted teal (`#63948B`), DOIs use light blue (`#A2C4F1`), and bar outlines use dark teal (`#285953`). Categorical plots keep the same category order across both panels and label each bar with its count. Dashed lines on numerical capacity histograms mark the arithmetic mean of the values represented in each panel. Identical copies are under `figures/02_records_and_DOI/`; single-panel record-count versions are under `figures/01_synthesis_records/`. PNG images are 600 dpi and all canvases are exactly 6 inches wide. Vector PDF and SVG versions are supplied. Arial is used when installed; the plotting script records any font fallback in the summary file.

Categorical DOI counts use one count for each distinct DOI/category in the positive dataset. A publication can contain multiple categories, so summing DOI-category counts can exceed the dataset's number of unique DOIs. DOI normalization removes URL or `doi:` prefixes and ignores case; blank DOIs are excluded from DOI summaries. For numeric capacity panel b, one median accepted capacity is calculated per DOI from its positive records. The dashed mean in panel b is the arithmetic mean of these DOI medians.

The plotted calculations are saved in `category_counts.csv`, `field_coverage.csv`, and `volume_histogram_counts.csv`. These CSV exports cover the positive dataset only. The accompanying `distribution_summary.json` retains input-file SHA256 hashes and summary statistics for both source datasets as provenance, including row and DOI denominators, numeric summaries, and counts of nonnumeric capacity labels. `resolved_records` excludes explicitly missing, unclear, ambiguous, and unresolved category labels, as specified in that JSON. Generic shape-unspecified glass/polymer categories remain identifiable categories. Numerical histogram counts are checked to ensure that every accepted numeric positive-dataset value is included, including the upper tail.

See `FIGURE_CAPTIONS.md` for captions and `Section_S5_process_details.md` for the short manuscript subsection. Figure numbers remain placeholders for the final SI layout.
