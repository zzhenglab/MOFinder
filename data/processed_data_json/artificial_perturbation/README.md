# Artificial perturbation ablation

| File | Contents | P | N | Total |
| --- | --- | ---: | ---: | ---: |
| [train_artificial_field_matched.jsonl](train_artificial_field_matched.jsonl) | Field-matched artificial perturbation | 11,968 | 11,560 | 23,528 |
| [train_artificial_count_matched.jsonl](train_artificial_count_matched.jsonl) | Count-matched random perturbation | 11,968 | 11,560 | 23,528 |
| [holdout.jsonl](holdout.jsonl) | Archived study holdout | 1,320 | 1,275 | 2,595 |

Both variants replace the original training negatives with perturbations of training positives, using seed 101. The original positives, record order, system prompt, and eight-field format are preserved.

- **Field-matched:** the existing dataset, renamed. It preserves which fields differ from each negative's nearest training positive and approximately matches numerical change magnitudes.
- **Count-matched:** keeps the same positive reference and number of changed fields, randomly chooses which fields to change, and samples replacement values from their training-positive distributions.

The change count is measured against the selected positive reference. Both variants reject duplicate conditions and held-out chemistry clusters. Generated conditions receive N labels for these controls. The supplied holdout preserves the archived study inputs used for the recorded comparison; it is not the current corrected main holdout.

[Preparation code](../../../src/mofinder/datasets/ablations.py), with the [artificial-negative generation rules](../../../src/mofinder/datasets/artificial_control.py). Reproduction requires the historical inputs pinned in the preparation code. Run from a checkout containing those inputs:

```bash
python -m mofinder.datasets.ablations --output results/ablations
```
