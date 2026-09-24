# Archived condition-classification split

These files record the partition used by [train.jsonl](../training/train.jsonl) and [holdout.jsonl](../training/holdout.jsonl). They were regenerated from the archived positive and negative stage 6 tables using [dataset_preparation_archived.json](../../configs/dataset_preparation_archived.json). Both regenerated JSONL files match the archived files byte for byte.

| File | Contents |
| --- | --- |
| `split_assignments.csv` | Retained source rows, condition keys, cluster keys, labels, and partition |
| `split_summary.json` | Input hashes, preparation settings, filtering counts, split counts, and output identities |
| `class_map.json` | P = success; N = failure |

| Partition | P | N | Total | Clusters |
| --- | ---: | ---: | ---: | ---: |
| Training | 11,968 | 11,560 | 23,528 | 11,157 |
| Holdout | 1,320 | 1,275 | 2,595 | 1,231 |

Training and holdout have no shared clusters or exact condition inputs. Their P:N ratio is 88:85. Distinct clusters from the same DOI can occur in both partitions.

`source_row_id` is the zero-based row number in the original concatenation of the positive and negative tables, before filtering. IDs below 15,340 refer to [positive_stage6.csv](../cleaned_data/archived/positive_stage6.csv). For larger IDs, subtract 15,340 to obtain the zero-based row number in [negative_stage6_v3.csv](../cleaned_data/archived/negative_stage6_v3.csv). Header rows are excluded. `is_success` is `True` for P and `False` for N. The assignment table contains retained records only; filtering counts appear in the summary.

The CSV uses UTF-8 with a byte-order mark for spreadsheet compatibility. Paths in the summary are relative to the repository root. The publication-year subset paths identify files generated during preparation; those subsets can be recreated with:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_archived.json
```

The command writes a new run under `results/datasets/archived_conditions/`. See [the dataset guide](../../docs/datasets.md) for the condition fields and grouping rules.
