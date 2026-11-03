# Leave-one-perturbation-out ablation

| Files | Training P | Training N | Total |
| --- | ---: | ---: | ---: |
| [train_leave_one_perturbation_out.jsonl](train_leave_one_perturbation_out.jsonl) | 11,968 | 7,733 | 19,701 |
| `train_random_drop_seed*.jsonl` (101, 202, 303, 404, 505) | 11,968 each | 7,733 each | 19,701 each |

The study removal set drops 3,827 negatives that differed from a training positive in exactly one of the eight input fields. Each random-drop control removes the same number of negatives at random. All positives and the selected row order are retained; shared inputs now match the corrected [training set](../train.jsonl). The removal set was not recomputed after these input corrections.

Use the shared [holdout.jsonl](../holdout.jsonl): 1,320 P and 1,275 N (2,595 records). Dataset corrections do not rerun models or revise previously recorded comparisons.

[Preparation code](../../../src/mofinder/datasets/ablations.py) reproduces the original selection and input values using its pinned inputs, available in the [private archive](https://github.com/zzhenglab/MOFinder-archive-20261101/tree/200cdcf6272fbd31ceca8227d7762e59583460df/data/processed_data_json) (repository permission required). The released files retain that selection with corrected reaction inputs. Run the original generation with its exact inputs:

```bash
python -m mofinder.datasets.ablations --output results/ablations
```
