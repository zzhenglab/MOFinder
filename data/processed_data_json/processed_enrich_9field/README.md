# Nine-field process-enriched dataset

The eight reaction inputs plus `stirring`. All eight shared inputs, row order, and labels match the current baseline. Split membership and stirring annotations are unchanged. Correcting these inputs does not rerun models or revise previously reported performance.

| File | P | N | Total |
|---|---:|---:|---:|
| [train_process_enrich_9field.jsonl](train_process_enrich_9field.jsonl) | 11,968 | 11,560 | 23,528 |
| [holdout_process_enrich_9field.jsonl](holdout_process_enrich_9field.jsonl) | 1,320 | 1,275 | 2,595 |

- `yes`: stirring is reported, including preparation stirring when a later static stage is not stated.
- `no`: synthesis is explicitly static or unstirred, including stirring only before static synthesis.
- `not reported`: stirring is unspecified or ambiguous; sonication, shaking, rotation, or mixing alone is insufficient.

The [nine-field system prompt](../../../prompts/training/reaction_prediction_process_enrich_9field.txt) lists the nine inputs and defines these values. A `yes` value does not imply continuous reaction-stage stirring.

Use the released JSONL files directly. The existing generator shares the eleven-field preparation's unique condition/label requirement and cannot regenerate the corrected release unchanged; see [preparation details](../../../docs/process_enrich_training.md#prepare-the-paired-jsonl-files).
