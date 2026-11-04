# Eleven-field process-enriched dataset

This is the eleven-field version. The [nine-field stirring version](../processed_enrich_9field/README.md) adds only `stirring` to the original eight inputs.

| File | Rows | Positive | Negative |
| --- | ---: | ---: | ---: |
| [train_process_enrich.jsonl](train_process_enrich.jsonl) | 23,528 | 11,968 | 11,560 |
| [holdout_process_enrich.jsonl](holdout_process_enrich.jsonl) | 2,595 | 1,320 | 1,275 |

All eight shared inputs, row order, and labels match the current baseline. Each user prompt adds `vessel_type`, `vessel_volume_mL`, and `agitation`; the system prompt adds these names to its input-field list. Missing values use `Not reported`; unresolved vessel capacities use `Ambiguous`. The `*_sources.csv` files map JSONL rows to source records, with condition and cluster keys reflecting the corrected inputs. Split membership and process annotations are unchanged.

The [verification report](independent_verification.json) checks every row against the current baseline. Normalization is shared with the [cleaned CSVs](../../processed_data/with_process_details/README.md); the [positive-data plots](../../../docs/process_details/README.md) summarize the three added fields. Correcting these inputs does not rerun models or revise previously reported performance.

Use the released JSONL files directly. They retain explicit row-to-source mappings, including four training condition pairs with consistent N labels. The existing [preparation code](../../../src/mofinder/datasets/process_enrich.py) requires unique condition/label keys and cannot regenerate this corrected release unchanged; see [preparation details](../../../docs/process_enrich_training.md#prepare-the-paired-jsonl-files).
