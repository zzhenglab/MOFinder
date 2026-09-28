# Processed-data training and holdout JSONL

Training and holdout files prepared from the [processed positive and negative records](../processed_data/README.md).

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

Each JSONL record contains system, user, and assistant messages. The user message contains eight reaction-condition fields; the assistant answer is `P` or `N`. Training and holdout use separate chemistry clusters, with a P:N ratio of 88:85 in each partition. See [split preparation](../../docs/datasets.md) for the filtering and grouping rules.

## Process-enriched dataset

[processed_enrich/](processed_enrich/README.md) preserves the same records, order, labels, and eight original inputs, adding `vessel_type`, `vessel_volume_mL`, and `agitation` to the user and system prompts.

## Training-data ablations

- [artificial_perturbation/](artificial_perturbation/README.md): one training set replacing reconstructed negatives with artificial perturbations of training positives.
- [leave_one_perturbation_out/](leave_one_perturbation_out/README.md): one training set removing single-field negative neighbors and five equally sized random-drop controls.

Both folders include the standard holdout and use the existing trained baseline for comparison.

## Training and test visualization

![Training and test synthesis records](../../docs/dataset_analysis/figures/Figure_D10_training_test_tsne.png)

The [analysis notebook](../../Demo/04_dataset_analysis/dataset_analysis.ipynb) generates these plots; test panels use the holdout partition above.

## Regenerate from processed data

From the repository root:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

This reads the processed CSVs and publication years, then writes training, holdout, split metadata, and publication-year subsets under `results/datasets/conditions/`.

To prepare newly generated curation outputs, use [dataset_preparation_from_curation.json](../../configs/dataset_preparation_from_curation.json). The [linker-corrected input](../processed_data/linker_corrected/README.md) uses a separate configuration and recalculated partitions.

## Trace records to their source rows

In `split_assignments.csv`, `source_row_id` is the zero-based row number in the original concatenation of the positive and negative tables, before filtering. IDs below 15,340 refer to [processed_positive.csv](../processed_data/processed_positive.csv). For larger IDs, subtract 15,340 to obtain the zero-based row number in [processed_negative.csv](../processed_data/processed_negative.csv). Header rows are excluded.

`is_success` is `True` for P and `False` for N. The assignment table contains retained records only; filtering counts appear in the summary. The CSV uses UTF-8 with a byte-order mark for spreadsheet compatibility.

## Use the final records

Training instructions:

- [GPT-4.1 in the OpenAI dashboard](../../docs/training_openai.md): upload the training JSONL and enter the recorded hyperparameters.
- [GPT-oss-20B on a local GPU or HPC system](../../docs/training_hpc.md): prepare one dataset bundle, transfer it to the training environment, and train a LoRA adapter.

See [holdout evaluation](../../docs/holdout_evaluation.md) to evaluate a configured model. Live evaluation sends only the system instruction and reaction conditions; the reference answer stays local for scoring.
