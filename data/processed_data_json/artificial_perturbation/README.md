# Artificial perturbation ablation

| File | Contents | P | N | Total |
| --- | --- | ---: | ---: | ---: |
| [train_artificial_field_matched.jsonl](train_artificial_field_matched.jsonl) | Field-matched artificial perturbation | 11,968 | 11,560 | 23,528 |
| [train_artificial_count_matched.jsonl](train_artificial_count_matched.jsonl) | Count-matched random perturbation | 11,968 | 11,560 | 23,528 |
| [holdout.jsonl](holdout.jsonl) | Unchanged standard holdout | 1,320 | 1,275 | 2,595 |

Both variants replace the original training negatives with perturbations of training positives, using seed 101. The original positives, record order, system prompt, and eight-field format are preserved.

- **Field-matched:** the existing dataset, renamed. It preserves which fields differ from each negative's nearest training positive and approximately matches numerical change magnitudes.
- **Count-matched:** keeps the same positive reference and number of changed fields, randomly chooses which fields to change, and samples replacement values from their training-positive distributions.

The change count is measured against the selected positive reference. Both variants reject duplicate conditions and held-out chemistry clusters. Generated conditions receive N labels for these controls. Compare each variant with the existing trained baseline on the unchanged holdout.

[Preparation code](../../../src/mofinder/curation/ablations.py), run from the repository root:

```bash
python -m mofinder.curation.ablations --output results/ablations
```
