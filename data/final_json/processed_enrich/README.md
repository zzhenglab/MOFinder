# Process-enriched matched control

`train.jsonl` and `holdout.jsonl` preserve the standard split, record order, labels, and eight original inputs. They add only `vessel_type`, `vessel_volume` (capacity in mL), and `stirring`, using an updated system prompt. Missing values are `Not reported`; unresolved capacities are `Ambiguous`.

The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. `jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.

Negative process annotations can be inherited from successful recipes. The existing split shares 864 DOIs across training and holdout. Use this dataset as a matched control; do not interpret it as causal process validation. No manual benchmark process details are invented and no model was trained.

The release [independent verification](independent_verification.json) records an exhaustive comparison against both archived splits, including source and output hashes. The 53 process, training, and dataset regression tests passed when this release was prepared.

Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich` using a new output directory. See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.
