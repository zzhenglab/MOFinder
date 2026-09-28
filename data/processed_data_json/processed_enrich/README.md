# Process-enriched matched control

[`train_process_enrich.jsonl`](train_process_enrich.jsonl) (23,528 rows) and [`holdout_process_enrich.jsonl`](holdout_process_enrich.jsonl) (2,595 rows) preserve the standard split, record order, labels, and eight original inputs. They add only `vessel_type`, `vessel_volume_mL` (capacity in mL), and `stirring`. The system prompt is identical to each original prompt except for these three names appended to its input list. Missing values are `Not reported`; unresolved capacities are `Ambiguous`.

The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. `jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.

Final category consolidation is shared with the cleaned CSVs. Stirring labels contain at most five words; rare stirring classes map to `Stirring, mixing, shaking, rotation, sonication`, listing alternative methods across records. `Stirred during preparation` leaves later agitation unknown, and `No stirring` denotes explicitly static or unstirred conditions. The shortened `PTFE-lined autoclave` retains its existing membership. Unspecified and selected rare vessel types map to `Not reported`. These fixed mappings use positive-reference record counts and are applied identically to both labels and splits. Detailed classes and audit reasons remain outside model input. See the [consolidation audit](../../processed_data/with_process_details/audit/category_consolidation.csv).

Negative process annotations can be inherited from successful recipes. The existing split shares 864 DOIs across training and holdout. Use this dataset as a matched control; do not interpret it as causal process validation. No manual benchmark process details are invented and no model was trained.

The release [independent verification](independent_verification.json) compares every row directly with the same row in the archived split, without sorting. Both splits have zero mismatches in the original values, JSON types, key order, labels, metadata, or prompt text outside the input-list expansion. The 57 process, training, and dataset regression tests passed when this release was prepared.

Repeat the independent comparison from the repository root with `python tools/audit_process_enrich_alignment.py`. Add `--output results/local/process_alignment.json` to save a fresh report.

Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich` using a new output directory. See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.

The canonical [process-enriched system prompt](../../../prompts/training/reaction_prediction_process_enrich.txt) is stored in `prompts/training/`; no prompt copy is kept in this dataset folder.

## Positive-dataset process distributions

These figures describe all 15,340 positive tabular records from 4,568 DOIs, before model-training exclusions. Each figure shows synthesis records in panel **a** and unique DOIs in panel **b**, using the gradient style of the primary-modulator figure. The [Section S5 draft](../../../docs/process_details/Section_S5_process_details.md), [captions](../../../docs/process_details/FIGURE_CAPTIONS.md), [calculation tables and gallery](../../../docs/process_details/README.md), and [counting methods](../../../docs/process_details/DISTRIBUTION_METHODS.md) provide the accompanying material.

![Reaction-vessel category frequencies among positive records and unique DOIs](../../../docs/process_details/figures/process_enrich_vessel_type.png)

**Figure Sxx. Frequencies of vessel types after cleaning and consolidation of name and material variants.** a, Vessel-type frequencies among positive synthesis records. b, Unique DOI counts per vessel type. Not reported includes unspecified types and vessel classes with fewer than 10 positive records; a DOI may contribute to multiple categories.

![Vessel-capacity distributions among positive records and unique DOIs](../../../docs/process_details/figures/process_enrich_vessel_volume.png)

**Figure Sxx+1. Distributions of reported vessel capacities after cleaning and unit conversion to mL.** a, Vessel capacities among positive synthesis records. b, Median vessel capacity per unique DOI. Histograms use shared logarithmic bins; dashed lines indicate the arithmetic mean in each panel. Not reported and Ambiguous capacities are excluded.

![Stirring-category frequencies among positive records and unique DOIs](../../../docs/process_details/figures/process_enrich_stirring.png)

**Figure Sxx+2. Frequencies of stirring categories after cleaning and consolidation of process descriptions.** a, Stirring-category frequencies among positive synthesis records. b, Unique DOI counts per stirring category. Reported-agitation classes with fewer than 50 positive records are pooled as Stirring, mixing, shaking, rotation, sonication, denoting alternative methods across records; a DOI may contribute to multiple categories.

Figure numbers remain placeholders for final SI placement. Categorical panels include **Not reported**, including pooled rare known vessel types; each DOI is counted once per category and may contribute to multiple categories. Capacity panels use accepted numeric values without imputation. Colors progress through categories or bins and do not encode another measurement. These distributions describe feature availability and do not establish improved predictive performance.
