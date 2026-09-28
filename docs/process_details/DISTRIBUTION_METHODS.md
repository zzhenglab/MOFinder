# Process-detail distributions

The plotting script reads the cleaned process-detail CSVs and never changes either source table. Run from the repository root:

```powershell
python tools/plot_process_details.py --output "../Figure 1 and Figure 4/SI figures/process enrich figures" --report-dir "../Figure 1 and Figure 4/SI figures/data/process_enrich"
```

`--output` is required and receives three PNG figures. `--report-dir` is separate and holds calculation tables, captions, provenance, and the Section S5 Markdown draft. If omitted, it defaults to a sibling directory named `process_enrich_data`. Custom source paths can be supplied with `--positive` and `--negative`. `--si-section` and `--docx` save manuscript drafts, including beside the local figures. PNG is the only figure export format; no PDF/SVG files or single-panel variants are generated. The published copies appear in the [figure gallery](README.md#figures) and the [process-enriched dataset README](../../data/processed_data_json/processed_enrich/README.md).

The figures describe all 15,340 cleaned positive tabular records from 4,568 DOIs, before model-training exclusions. Negative records are not plotted. The three outputs are:

- `process_enrich_vessel_type.png`: final vessel categories and counts.
- `process_enrich_vessel_volume.png`: accepted vessel capacities in mL on logarithmic axes with shared bins.
- `process_enrich_stirring.png`: final stirring categories and counts.

Each figure places panel **a**, synthesis records, above panel **b**, unique DOIs. The gradients match the primary-modulator frequency figure: panel a progresses from light blue (`#A2C4F1`) to pale teal (`#B6E2DC`), and panel b from dark teal (`#285953`) through muted teal (`#63948B`) to gray (`#8D969E`). Categorical colors follow the displayed order, which is shared across panels and follows positive-record frequency with **Not reported** last. Each bar is labeled with its count. Histogram gradients progress through capacity bins from left to right. These gradients do not encode an additional numeric variable. Boxed axes and bars without outlines follow the same reference style. PNGs are 600 dpi and six inches wide. Arial is used when installed; any font fallback is recorded in the summary. Dashed capacity-histogram lines show the arithmetic mean of the values represented in each panel.

## Category preparation

These are final dataset categories, with no extra merging in the plotting script. The same labels appear in the cleaned CSVs and enriched training/holdout files. Consolidation thresholds use **positive synthesis-record counts**, not DOI counts, and the resulting mapping is applied consistently to both classes.

Material-only vessels are named **Glass vessel**, **Polymer vessel**, or **Metal vessel**, without the parenthetical shape qualifier. The former PTFE-lined autoclave / pressure vessel category is shortened to **PTFE-lined autoclave**, with unchanged membership. **Vessel (type not reported)** is merged into **Not reported**. Vessel classes with fewer than 10 positive records are also assigned to **Not reported**. Thus, this label includes both missing/unresolved vessel types and deliberately pooled rare known types; it is not a pure missingness count. Original text and detailed categories remain available in the preparation audits.

All final stirring labels contain at most five words. Reported-agitation classes with fewer than 50 positive records are combined as **Stirring, mixing, shaking, rotation, sonication** (121 positive and 115 negative records). The list names alternative reported methods across these records; it does not assert that every method occurs in each record. **No stirring** denotes explicitly static or unstirred conditions. **Stirred during preparation** leaves later agitation unknown. **Stirred; stage not reported** makes no assumption about the process stage. The remaining classes are **Stirred before static synthesis**, **Sonicated before static synthesis**, and **Not reported**. Detailed stage and agitation classifications are retained in the audit instead of being shown as separate rare classes. Audited ambiguous descriptions that do not establish a unique stirring state are assigned to **Not reported**. Neither this label nor an ambiguous description is interpreted as static synthesis.

## Counting and provenance

Categorical panels include every positive record, including **Not reported**. DOI counts use one count per distinct DOI/category. A paper can contribute to multiple categories, so the sum of DOI-category counts may exceed the number of unique papers. DOI normalization removes URL or `doi:` prefixes, ignores case, and excludes blank DOIs from DOI summaries.

Capacity histograms use only positive finite numerical capacities. **Not reported** and **Ambiguous** capacities are excluded without imputation. Panel b uses one median accepted capacity per DOI; its dashed line is the arithmetic mean of those DOI medians. Histogram totals are checked to include every accepted value, including the upper tail.

`category_counts.csv`, `field_coverage.csv`, and `volume_histogram_counts.csv` contain positive-dataset calculations. `distribution_summary.json` retains both input-file SHA256 hashes and summary statistics for provenance. Its `resolved_records` measure counts retained final categories and excludes explicitly missing, unclear, ambiguous, and unresolved labels; after rare-vessel pooling, it should not be interpreted as the count of every source record that mentions a known vessel.

The [figure captions](FIGURE_CAPTIONS.md) and [Section S5 draft](Section_S5_process_details.md) accompany the published figures and are also saved with the local manuscript assets. Figure numbers are placeholders pending final SI placement. Negative process annotations may be inherited from successful parent protocols, so this control does not constitute independent experimental verification of failed-trial process conditions.
