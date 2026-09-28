# Process-enriched matched control

[`train_process_enrich.jsonl`](train_process_enrich.jsonl) (23,528 rows) and [`holdout_process_enrich.jsonl`](holdout_process_enrich.jsonl) (2,595 rows) preserve the standard split, record order, labels, and eight original inputs. They add only `vessel_type`, `vessel_volume_mL` (capacity in mL), and `agitation` to each user prompt. The system prompt is identical to each original prompt except for these three names appended to its input list. Missing values are `Not reported`; unresolved capacities are `Ambiguous`.

The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. `jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.

Final categories are shared with the cleaned CSVs. The nine agitation categories combine stirring, shaking, rotation, vortexing, mixing, and homogenization by process stage while retaining sonication separately. Labels contain two to five words. `Agitated during preparation` leaves later agitation unknown, `Agitated; stage not reported` makes no stage assumption, and `No stirring` denotes explicitly static or unstirred conditions. The shortened `PTFE-lined autoclave` retains its existing membership. Unspecified vessel types and vessel classes with fewer than 10 positive-reference records map to `Not reported`. The same mapping and source-review rules apply to both labels and splits. Original method details, parsing evidence, and audit reasons remain outside model input. See the [nine-category counts](../../processed_data/with_process_details/README.md#normalization-and-audit), [category audit](../../processed_data/with_process_details/audit/category_consolidation.csv), and [targeted agitation source audit](../../processed_data/with_process_details/audit/AGITATION_SOURCE_AUDIT.md).

Negative process annotations can be inherited from successful recipes. The existing split shares 864 DOIs across training and holdout. Use this dataset as a matched control; do not interpret it as causal process validation. No manual benchmark process details are invented and no model was trained.

The release [independent verification](independent_verification.json) compares every row directly with the same row in the archived split, without sorting. Both splits have zero mismatches in the original values, JSON types, key order, labels, metadata, or prompt text outside the input-list expansion.

Repeat the independent comparison from the repository root with `python tools/audit_process_enrich_alignment.py`. Add `--output results/local/process_alignment.json` to save a fresh report.

Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich` using a new output directory. See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.

The canonical [process-enriched system prompt](../../../prompts/training/reaction_prediction_process_enrich.txt) is stored in `prompts/training/`; no prompt copy is kept in this dataset folder.

## Positive-dataset process distributions

Click any figure to open the full-resolution PNG.

These figures describe all 15,340 positive tabular records from 4,568 DOIs, before model-training exclusions. Each figure shows synthesis records in panel **a** and unique DOIs in panel **b**, using the gradient style of the primary-modulator figure. The [Section S5 draft](../../../docs/process_details/Section_S5_process_details.md), [captions](../../../docs/process_details/FIGURE_CAPTIONS.md), [calculation tables and gallery](../../../docs/process_details/README.md), and [counting methods](../../../docs/process_details/DISTRIBUTION_METHODS.md) provide the accompanying material.

PTFE-lined autoclaves are the most common vessel type, accounting for 37.4% of positive records, followed by vials at 16.8%. A paper can report several vessel types, so it may contribute to multiple DOI counts. The Not reported category also includes rare vessel types pooled during cleaning.

<a href="../../../docs/process_details/figures/process_enrich_vessel_type.png"><img src="../../../docs/process_details/figures/process_enrich_vessel_type.png" alt="Reaction-vessel category frequencies among positive records and unique DOIs" width="500"></a>

Reported vessel capacities have a median of 23 mL and an interquartile range of 16–25 mL. Numeric capacities are available for 7,271 positive records (47.4%). The DOI panel uses one median per paper, and dashed lines show the mean in each panel. Missing and ambiguous capacities are omitted.

<a href="../../../docs/process_details/figures/process_enrich_vessel_volume.png"><img src="../../../docs/process_details/figures/process_enrich_vessel_volume.png" alt="Vessel-capacity distributions among positive records and unique DOIs" width="500"></a>

The No stirring category represents explicitly static or unstirred conditions and accounts for 6,522 positive records (42.5%). Agitation information is Not reported for 3,886 records (25.3%). Among the seven remaining categories, Agitated before static synthesis contains 1,792 records (11.7%), and Agitated; stage not reported contains 2,223 records (14.5%). The nine-category scheme combines related methods by stage while keeping sonication separate. Preparation-only reports leave later agitation unknown; the [source audit](../../processed_data/with_process_details/audit/AGITATION_SOURCE_AUDIT.md) preserves the reviewed method details.

<a href="../../../docs/process_details/figures/process_enrich_agitation.png"><img src="../../../docs/process_details/figures/process_enrich_agitation.png" alt="Agitation-category frequencies among positive records and unique DOIs" width="500"></a>

Categorical panels include **Not reported**, including pooled rare known vessel types; each DOI is counted once per category and may contribute to multiple categories. Capacity panels use accepted numeric values without imputation. Colors progress through categories or bins and do not encode another measurement. These distributions describe feature availability and do not establish improved predictive performance.
