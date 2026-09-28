# Process-enriched matched control

`train.jsonl` and `holdout.jsonl` preserve the standard split, record order, labels, and eight original inputs. They add only `vessel_type`, `vessel_volume_mL` (capacity in mL), and `stirring`. The system prompt is identical to each original prompt except for these three names appended to its input list. Missing values are `Not reported`; unresolved capacities are `Ambiguous`.

The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. `jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.

Final category consolidation is shared with the cleaned CSVs. Stirring labels contain at most five words; rare stirring classes map to `Stirring, mixing, shaking, rotation, sonication`, listing alternative methods across records. `Stirred during preparation` leaves later agitation unknown, and `No stirring` denotes explicitly static or unstirred conditions. The shortened `PTFE-lined autoclave` retains its existing membership. Unspecified and selected rare vessel types map to `Not reported`. These fixed mappings use positive-reference record counts and are applied identically to both labels and splits. Detailed classes and audit reasons remain outside model input. See the [consolidation audit](../../processed_data/with_process_details/audit/category_consolidation.csv).

Negative process annotations can be inherited from successful recipes. The existing split shares 864 DOIs across training and holdout. Use this dataset as a matched control; do not interpret it as causal process validation. No manual benchmark process details are invented and no model was trained.

The release [independent verification](independent_verification.json) compares every row directly with the same row in the archived split, without sorting. Both splits have zero mismatches in the original values, JSON types, key order, labels, metadata, or prompt text outside the input-list expansion. The 57 process, training, and dataset regression tests passed when this release was prepared.

Repeat the independent comparison from the repository root with `python tools/audit_process_enrich_alignment.py`. Add `--output results/local/process_alignment.json` to save a fresh report.

Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich` using a new output directory. See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.
