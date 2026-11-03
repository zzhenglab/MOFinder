# Artificial perturbation ablation

| File | Contents | P | N | Total |
| --- | --- | ---: | ---: | ---: |
| [train_artificial_field_matched.jsonl](train_artificial_field_matched.jsonl) | Field-matched artificial perturbation | 11,968 | 11,560 | 23,528 |
| [train_artificial_count_matched.jsonl](train_artificial_count_matched.jsonl) | Count-matched random perturbation | 11,968 | 11,560 | 23,528 |
| [Shared holdout](../holdout.jsonl) | Current corrected holdout | 1,320 | 1,275 | 2,595 |

Both variants replace the original training negatives with perturbations of training positives, using seed 101. The original positives, record order, system prompt, and eight-field format are preserved.

- **Field-matched:** preserves which fields differ from each negative's nearest training positive and approximately matches numerical change magnitudes.
- **Count-matched:** keeps the same positive reference and number of changed fields, randomly chooses which fields to change, and samples replacement values from their training-positive distributions.

The change count is measured against the selected positive reference. Both variants reject duplicate conditions and held-out chemistry clusters. Generated conditions receive N labels for these controls. Use the shared current holdout for new evaluations; recorded model results retain the input versions used for their runs.

[Preparation code](../../../src/mofinder/datasets/ablations.py), with the [artificial-negative generation rules](../../../src/mofinder/datasets/artificial_control.py). It reproduces the original study files from its pinned inputs, available in the [private archive](https://github.com/zzhenglab/MOFinder-archive-20261101/tree/200cdcf6272fbd31ceca8227d7762e59583460df/data/processed_data_json) (repository permission required). Its copied holdout predates the corrections in the shared current holdout. Run with those exact inputs:

```bash
python -m mofinder.datasets.ablations --output results/ablations
```
