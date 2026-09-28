# Four-period year splits

Publication-year subsets of the standard training set: 4 individual blocks and 2 cumulative subsets. Filenames, prompts, and row order match the original Step 5 exports.

| Subset | P | N | Total |
| --- | ---: | ---: | ---: |
| [1999-2012](mof_cls_train_1999to2012.jsonl) | 2,719 | 3,287 | 6,006 |
| [2013-2015](mof_cls_train_2013to2015.jsonl) | 2,378 | 2,924 | 5,302 |
| [2016-2019](mof_cls_train_2016to2019.jsonl) | 3,137 | 2,609 | 5,746 |
| [2020-2025](mof_cls_train_2020to2025.jsonl) | 3,734 | 2,740 | 6,474 |
| [1999-2015 (cumulative)](mof_cls_train_1999to2015.jsonl) | 5,097 | 6,211 | 11,308 |
| [1999-2019 (cumulative)](mof_cls_train_1999to2019.jsonl) | 8,234 | 8,820 | 17,054 |

Use the shared [holdout.jsonl](../holdout.jsonl): **2,595 records (1,320 P + 1,275 N)**.

Regenerate both year-split versions from the processed positive and negative CSVs:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

Outputs are written to `results/datasets/conditions/`.
