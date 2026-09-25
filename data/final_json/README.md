# Final training and holdout JSONL

This folder keeps the final model inputs and their split information together. The JSONL files were prepared from the [processed positive and negative records](../processed_data/README.md) and preserve the exact records used for the reported runs.

| File | Contents |
| --- | --- |
| [train.jsonl](train.jsonl) | Fine-tuning training records |
| [holdout.jsonl](holdout.jsonl) | Holdout records for model evaluation |
| [split_assignments.csv](split_assignments.csv) | Retained source rows, condition keys, cluster keys, labels, and partition |
| [split_summary.json](split_summary.json) | Input hashes, preparation settings, filtering counts, split counts, and output identities |
| [class_map.json](class_map.json) | P = success; N = failure |
| [manifest.json](manifest.json) | JSONL checksums, file identities, and label counts |

| Partition | P | N | Total | Clusters |
| --- | ---: | ---: | ---: | ---: |
| Training | 11,968 | 11,560 | 23,528 | 11,157 |
| Holdout | 1,320 | 1,275 | 2,595 | 1,231 |

Each JSONL record contains the original system instruction, eight-field reaction conditions, and a P/N reference answer. The files match the outputs from the source dataset-preparation notebook. Training and holdout have no shared clusters or exact condition inputs, and both have a P:N ratio of 88:85. Distinct clusters from the same DOI can occur in both partitions.

Some training workflows also use the holdout as validation data. Record that use with the training job; this folder does not contain an additional independent test partition.

## Regenerate from processed data

From the repository root:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

This configuration reads the bundled processed positive and negative tables and publication years, then writes a new run under `results/datasets/conditions/`. Regenerated training and holdout JSONL match the distributed files byte for byte. The command also recreates the publication-year subsets identified in the split summary. Summary paths are relative to the repository root. See [dataset preparation](../../docs/datasets.md) for condition fields, filtering, grouping rules, and output filenames.

To prepare newly generated curation outputs, use [dataset_preparation_from_curation.json](../../configs/dataset_preparation_from_curation.json). The [linker-corrected input](../processed_data/linker_corrected/README.md) uses a separate configuration and recalculated partitions.

## Trace records to their source rows

In `split_assignments.csv`, `source_row_id` is the zero-based row number in the original concatenation of the positive and negative tables, before filtering. IDs below 15,340 refer to [processed_positive.csv](../processed_data/processed_positive.csv). For larger IDs, subtract 15,340 to obtain the zero-based row number in [processed_negative.csv](../processed_data/processed_negative.csv). Header rows are excluded.

`is_success` is `True` for P and `False` for N. The assignment table contains retained records only; filtering counts appear in the summary. The CSV uses UTF-8 with a byte-order mark for spreadsheet compatibility.

## Use the final records

The preparation command creates data files without launching a training job. Training routes:

- [GPT-4.1 in the OpenAI dashboard](../../docs/training_openai.md): upload the training JSONL and enter the recorded hyperparameters.
- [GPT-oss-20B on a local GPU or HPC system](../../docs/training_hpc.md): prepare one dataset bundle, transfer it to the training environment, and train a LoRA adapter.

See [holdout evaluation](../../docs/holdout_evaluation.md) to evaluate a configured model. Live evaluation sends only the system instruction and reaction conditions; the reference answer stays local for scoring.
