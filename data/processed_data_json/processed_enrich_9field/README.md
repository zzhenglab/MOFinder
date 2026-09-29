# Nine-field process-enriched dataset

The original eight reaction inputs plus `stirring`. The existing split, row order, P/N labels, and all eight original values are preserved.

| File | P | N | Total |
|---|---:|---:|---:|
| [train_process_enrich_9field.jsonl](train_process_enrich_9field.jsonl) | 11,968 | 11,560 | 23,528 |
| [holdout_process_enrich_9field.jsonl](holdout_process_enrich_9field.jsonl) | 1,320 | 1,275 | 2,595 |

- `yes`: stirring is reported, including preparation stirring when a later static stage is not stated.
- `no`: synthesis is explicitly static or unstirred, including stirring only before static synthesis.
- `not reported`: stirring is unspecified or ambiguous; sonication, shaking, rotation, or mixing alone is insufficient.

The [nine-field system prompt](../../../prompts/training/reaction_prediction_process_enrich_9field.txt) lists the nine inputs and defines these values. A `yes` value does not imply continuous reaction-stage stirring.

[Download training, holdout, and prompt](process_enrich_9field_train_holdout.zip).

Regenerate from the existing eleven-field files, source mappings, and processed CSVs:

```bash
python -m mofinder.datasets.process_enrich_9field --config configs/dataset_preparation_process_enrich_9field.json --output results/datasets/process_enrich_9field
```
