# Artificial perturbation ablation

| File | Contents | P | N | Total |
| --- | --- | ---: | ---: | ---: |
| [train_artificial_perturbation.jsonl](train_artificial_perturbation.jsonl) | Original positives and artificial negatives, generated with seed 101 | 11,968 | 11,560 | 23,528 |
| [holdout.jsonl](holdout.jsonl) | Unchanged standard holdout | 1,320 | 1,275 | 2,595 |

Artificial conditions replace the original training-negative slots by modifying training positives. Their N labels are control assignments, not experimentally verified failures. The original positive records, system prompt, eight input fields, and label format are preserved. Use the existing trained baseline for comparison; its training file is not duplicated here.

[Preparation code](../../../src/mofinder/curation/ablations.py), run from the repository root:

```bash
python -m mofinder.curation.ablations --output results/ablations
```
