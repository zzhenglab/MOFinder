# Recorded JSON preparation run

This is a completed run using the bundled inputs. All expected-output checks passed.

Recorded at: `2026-09-25T18:47:37.788901+00:00`.

| Output | Expected rows | Actual rows | Check |
| --- | ---: | ---: | --- |
| [mof_ft_train.jsonl](outputs/mof_ft_train.jsonl) | 252 | 252 | PASS |
| [mof_ft_holdout.jsonl](outputs/mof_ft_holdout.jsonl) | 28 | 28 | PASS |
| [mof_ft_class_map.json](outputs/mof_ft_class_map.json) | JSON values | JSON values | PASS |
| [demo_summary.json](outputs/demo_summary.json) | JSON values | JSON values | PASS |
| [mof_ft_split_assignments.csv](outputs/mof_ft_split_assignments.csv) | 280 | 280 | PASS |

[Executed notebook](../mof_json_preparation_demo.ipynb) ? [All saved output files](outputs/) ? [Run record and hashes](run_record.json) ? [Console log](run.log)

Later runs create their own local `run_history/` folders. This checked-in example remains available for inspection.
