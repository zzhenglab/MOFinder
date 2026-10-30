# Eleven-field process-enriched dataset

This is the eleven-field version. The [nine-field stirring version](../processed_enrich_9field/README.md) adds only `stirring` to the original eight inputs.

| File | Rows | Positive | Negative |
|---|---:|---:|---:|
| [train_process_enrich.jsonl](train_process_enrich.jsonl) | 23,528 | 11,968 | 11,560 |
| [holdout_process_enrich.jsonl](holdout_process_enrich.jsonl) | 2,595 | 1,320 | 1,275 |

Both files preserve the standard dataset's row order, split, labels, and eight original inputs. Each user prompt adds `vessel_type`, `vessel_volume_mL`, and `agitation`; the system prompt adds these names to its input-field list. Missing values use `Not reported`; unresolved vessel capacities use `Ambiguous`. The `*_sources.csv` files map JSONL rows to source records.

[Download the training and holdout ZIP](process_enrich_train_holdout.zip) or see the [system and user prompt comparison](README_training_package.md). Normalization is shared with the [cleaned CSVs](../../processed_data/with_process_details/README.md); the [positive-data plots](../../../docs/process_details/README.md) summarize the three added fields.

The released JSONL files can be used directly. Recreating them with the [preparation code](../../../src/mofinder/datasets/process_enrich.py) requires a supplied split-assignment CSV matching the baseline JSONL and source CSV row order. The historical assignment file is not distributed, and the config leaves `split_assignments` as `null`; preparation never infers a replacement. Replace the example assignment path below with your matching CSV and use a new output directory:

```bash
python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --split-assignments path/to/matching_split_assignments.csv --output results/datasets/process_enrich
```
