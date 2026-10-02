# Leave-one-perturbation-out ablation

| Files | Training P | Training N | Total |
| --- | ---: | ---: | ---: |
| [train_leave_one_perturbation_out.jsonl](train_leave_one_perturbation_out.jsonl) | 11,968 | 7,733 | 19,701 |
| `train_random_drop_seed*.jsonl` (101, 202, 303, 404, 505) | 11,968 each | 7,733 each | 19,701 each |

The removal set drops 3,827 negatives that differ from any training positive in exactly one of the eight input fields. Each random-drop control removes the same number of negatives at random. All positives are retained, and retained records preserve their original order and prompts.

[holdout.jsonl](holdout.jsonl) is the unchanged standard holdout: 1,320 P and 1,275 N (2,595 records). Compare with the existing trained baseline.

[Preparation code](../../../src/mofinder/datasets/ablations.py), run from the repository root:

```bash
python -m mofinder.datasets.ablations --output results/ablations
```
