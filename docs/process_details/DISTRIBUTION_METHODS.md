# Local process-detail distributions

The plotting script reads the cleaned process-detail CSVs and never changes either source table. Run from the repository root:

```powershell
python tools/plot_process_details.py --output "../Figure 1 and Figure 4/SI figures/process enrich figures" --report-dir "../Figure 1 and Figure 4/SI figures/data/process_enrich"
```

`--output` is required and contains only the three PNG figures. `--report-dir` is separate and holds calculation tables, captions, provenance, and the Section S5 Markdown draft. If omitted, it defaults to a sibling directory named `process_enrich_data`. Custom source paths can be supplied with `--positive` and `--negative`. `--si-section` and `--docx` optionally save local manuscript drafts. No PDF/SVG files, single-panel variants, or repository figure copies are generated.

The figures describe all 15,340 cleaned positive tabular records from 4,568 DOIs, before model-training exclusions. Negative records are not plotted. The three outputs are:

- `process_enrich_vessel_type.png`: final vessel categories and counts.
- `process_enrich_vessel_volume.png`: accepted vessel capacities in mL on logarithmic axes with shared bins.
- `process_enrich_stirring.png`: final stirring categories and counts.

Each figure places panel **a**, synthesis records, above panel **b**, unique DOIs. Records use muted teal (`#63948B`), DOIs use light blue (`#A2C4F1`), and outlines use dark teal (`#285953`). Category order is shared across panels and each bar is labeled with its count. PNGs are 600 dpi and six inches wide. Arial is used when installed; any font fallback is recorded in the summary. Dashed capacity-histogram lines show the arithmetic mean of the values represented in each panel.

## Category preparation

These are final dataset categories, with no extra merging in the plotting script. The same labels appear in the cleaned CSVs and enriched training/holdout files. Consolidation thresholds use **positive synthesis-record counts**, not DOI counts, and the resulting mapping is applied consistently to both classes.

Material-only vessels are named **Glass vessel**, **Polymer vessel**, or **Metal vessel**, without the parenthetical shape qualifier. **Vessel (type not reported)** is merged into **Not reported**. Vessel classes with fewer than 10 positive records are also assigned to **Not reported**. Thus, this label includes both missing/unresolved vessel types and deliberately pooled rare known types; it is not a pure missingness count. Original text and detailed categories remain available in the preparation audits.

Reported-agitation classes with fewer than 50 positive records are combined as **Other reported agitation**. Detailed stage and agitation classifications are retained in the audit instead of being shown as separate rare classes. Audited ambiguous descriptions that do not establish a unique stirring state are assigned to **Not reported**. Neither this label nor an ambiguous description is interpreted as static synthesis. Mixing reported only during preparation is not assumed to continue during crystallization.

## Counting and provenance

Categorical panels include every positive record, including **Not reported**. DOI counts use one count per distinct DOI/category. A paper can contribute to multiple categories, so the sum of DOI-category counts may exceed the number of unique papers. DOI normalization removes URL or `doi:` prefixes, ignores case, and excludes blank DOIs from DOI summaries.

Capacity histograms use only positive finite numerical capacities. **Not reported** and **Ambiguous** capacities are excluded without imputation. Panel b uses one median accepted capacity per DOI; its dashed line is the arithmetic mean of those DOI medians. Histogram totals are checked to include every accepted value, including the upper tail.

`category_counts.csv`, `field_coverage.csv`, and `volume_histogram_counts.csv` contain positive-dataset calculations. `distribution_summary.json` retains both input-file SHA256 hashes and summary statistics for provenance. Its `resolved_records` measure counts retained final categories and excludes explicitly missing, unclear, ambiguous, and unresolved labels; after rare-vessel pooling, it should not be interpreted as the count of every source record that mentions a known vessel.

`FIGURE_CAPTIONS.md` and `Section_S5_process_details.md` in the local report directory contain captions and the short manuscript subsection. Figure numbers are placeholders pending final SI placement. Negative process annotations may be inherited from successful parent protocols, so this control does not constitute independent experimental verification of failed-trial process conditions.
