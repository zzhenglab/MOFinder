# Five-period year splits

Publication-year subsets of the standard training set: 5 individual blocks and 3 cumulative subsets. Filenames, prompts, and row order match the original Step 5 exports.

| Subset | P | N | Total |
| --- | ---: | ---: | ---: |
| [1999-2011](mof_cls_train_5periods_1999to2011.jsonl) | 1,944 | 2,408 | 4,352 |
| [2012-2014](mof_cls_train_5periods_2012to2014.jsonl) | 2,259 | 2,364 | 4,623 |
| [2015-2017](mof_cls_train_5periods_2015to2017.jsonl) | 2,512 | 2,714 | 5,226 |
| [2018-2020](mof_cls_train_5periods_2018to2020.jsonl) | 2,232 | 1,922 | 4,154 |
| [2021-2025](mof_cls_train_5periods_2021to2025.jsonl) | 3,021 | 2,152 | 5,173 |
| [1999-2014 (cumulative)](mof_cls_train_5periods_1999to2014.jsonl) | 4,203 | 4,772 | 8,975 |
| [1999-2017 (cumulative)](mof_cls_train_5periods_1999to2017.jsonl) | 6,715 | 7,486 | 14,201 |
| [1999-2020 (cumulative)](mof_cls_train_5periods_1999to2020.jsonl) | 8,947 | 9,408 | 18,355 |
| [1999-2025 (full cumulative / FullN)](../train.jsonl) | 11,968 | 11,560 | 23,528 |

The five cumulative training cutoffs are **2011, 2014, 2017, 2020 and 2025**, corresponding to A, A+B, A+B+C, A+B+C+D and FullN. The 2025 training set is the shared `../train.jsonl`, whose records are the union of the five individual blocks; it is not duplicated in this folder.

Use the shared [holdout.jsonl](../holdout.jsonl): **2,595 records (1,320 P + 1,275 N)**.

Regenerate both year-split versions from the processed positive and negative CSVs:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

Outputs are written to `results/datasets/conditions/`.
