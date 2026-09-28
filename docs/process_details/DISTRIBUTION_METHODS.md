# Process-detail control distributions

Run from the repository root:

```powershell
python tools/plot_process_details.py
```

Custom inputs and an output folder can be supplied with `--positive`, `--negative`, and `--output`. `--si-output` optionally copies figures into an external SI figure folder. The plotting step never changes either input CSV.

The figures show the complete cleaned process-detail CSVs, including rows that the original training preparation may subsequently exclude. They therefore describe the tabular cohorts, not the smaller matched training and holdout files. Positive and inferred negative cohorts are shown separately. Missing and ambiguous feature labels remain in the tabular data and categorical plots; numeric capacity plots use only accepted finite capacities greater than zero. No numerical capacity is imputed.

- `figures/process_enrich_vessel_type.*`: all cleaned vessel categories.
- `figures/process_enrich_vessel_volume.*`: vessel capacities in mL, with a logarithmic capacity axis and shared bins.
- `figures/process_enrich_stirring.*`: all cleaned stirring categories, including stage information where available.

Each root figure has panel **a**, synthesis-record counts, and panel **b**, unique DOI counts. Identical copies are under `figures/02_records_and_DOI/`; single-panel record-count versions are under `figures/01_synthesis_records/`. PNG images are 600 dpi and all canvases are exactly 6 inches wide. Vector PDF and SVG versions are supplied. Arial is used when installed; the plotting script records any font fallback in the summary file.

Categorical DOI counts use one count for each distinct DOI/category/cohort. A publication can contain multiple categories, so summing DOI-category counts can exceed the cohort's number of unique DOIs. DOI normalization removes URL or `doi:` prefixes and ignores case; blank DOIs are excluded from DOI summaries. For numeric capacity panel b, one median accepted capacity is calculated per DOI within each cohort. A DOI represented in both positive and negative cohorts contributes independently to each cohort.

The full calculation is saved in `category_counts.csv`, `field_coverage.csv`, `volume_histogram_counts.csv`, and `distribution_summary.json`. The JSON includes input-file SHA256 hashes, row and DOI denominators, numeric summaries, and counts of nonnumeric capacity labels. `resolved_records` excludes explicitly missing, unclear, ambiguous, and unresolved category labels, as specified in that JSON. Generic shape-unspecified glass/polymer categories remain identifiable categories. Numerical histogram counts are checked to ensure that every accepted numeric value is included, including the upper tail.

See `FIGURE_CAPTIONS.md` for captions and `Section_S5_process_details.md` for the short manuscript subsection. Figure numbers remain placeholders for the final SI layout.
