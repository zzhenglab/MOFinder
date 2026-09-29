# Eleven-field process-enriched dataset

This is the eleven-field version. The [nine-field stirring version](../processed_enrich_9field/README.md) adds only `stirring` to the original eight inputs.

| File | Rows | Positive | Negative |
|---|---:|---:|---:|
| [train_process_enrich.jsonl](train_process_enrich.jsonl) | 23,528 | 11,968 | 11,560 |
| [holdout_process_enrich.jsonl](holdout_process_enrich.jsonl) | 2,595 | 1,320 | 1,275 |

Both files preserve the standard dataset's row order, split, labels, and eight original inputs. Each user prompt adds `vessel_type`, `vessel_volume_mL`, and `agitation`; the system prompt adds these names to its input-field list. Missing values use `Not reported`; unresolved vessel capacities use `Ambiguous`. The `*_sources.csv` files map JSONL rows to source records.

[Download the training and holdout ZIP](process_enrich_train_holdout.zip) or see the [system and user prompt comparison](README_training_package.md). Normalization is shared with the [cleaned CSVs](../../processed_data/with_process_details/README.md); the [positive-data plots](../../../docs/process_details/README.md) summarize the three added fields.

Recreate the files with the [preparation code](../../../src/mofinder/datasets/process_enrich.py), using a new output directory:

```bash
python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich
```
