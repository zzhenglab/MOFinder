# Dataset preparation demonstration

Prepare condition-classification training and holdout files from 146 processed positive records and 175 processed negative records. This demonstration calls `mofinder.datasets.prepare`, including the same condition builder, conflict handling, cluster split, class balancing, and JSONL writer used for the [full dataset](../../data/final_json/README.md).

## Run

From the repository root, with Python 3.10 or later:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --check
```

The bundled positive input matches the expected output of the [data curation demonstration](../01_data_curation/README.md). To use a freshly generated data curation output:

```bash
python Demo/01_data_curation/mof_data_curation_demo.py --check
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --positive-csv Demo/01_data_curation/outputs/mof_extraction_6.csv --check
```

The demonstration requires no API key, GPU, or model download and does not start a fine-tuning job. A typical run takes less than one minute. For an interactive walkthrough with saved outputs, install the `notebook` extra and open [prepare and verify training and holdout datasets](mof_dataset_preparation_demo.ipynb). The implementation is in [the demonstration script](mof_dataset_preparation_demo.py) and [the main dataset preparation code](../../src/mofinder/datasets/prepare.py); the [dataset guide](../../docs/datasets.md) describes their use.

The notebook previews holdout examples first, followed by training examples, with two P and two N records per split by default. Change `N_PER_LABEL` to adjust the sample size. Each example includes its source row, DOI, publication year, JSONL line number, eight reaction parameters, and expandable full JSON. Records are matched by normalized conditions and label because the JSONL files are shuffled.

## Inputs and settings

| File | Contents |
| --- | --- |
| [input/processed_positive.csv](input/processed_positive.csv) | Processed positive records from the data curation demonstration |
| [input/processed_negative.csv](input/processed_negative.csv) | Up to ten processed negative records per selected publication |
| [input/publication_years.csv](input/publication_years.csv) | DOI-to-year mapping for the selected publications |
| [input/source_manifest.json](input/source_manifest.json) | Source table hash and original negative row positions |
| [config.json](config.json) | Seed, split targets, paths, and balancing settings |
| [reaction-prediction prompt](../../prompts/training/reaction_prediction.txt) | System message used in the JSONL records; shared with MOF Quest evaluation and HPC training |

The seed is 42, with 10% row and cluster targets for holdout. Clusters combine the primary metal precursor, all linkers, and all solvents. The demonstration's reserved-question list is empty. The full dataset configuration is maintained separately in `configs/`.

## Expected output

| Partition | P | N | Total |
| --- | ---: | ---: | ---: |
| Training | 108 | 144 | 252 |
| Holdout | 12 | 16 | 28 |

Training and holdout share no clusters and have the same 3:4 P:N ratio. All 321 input records pass the required-field check; conflict handling, exact-input deduplication, and balancing leave 280 records. The [dataset guide](../../docs/datasets.md) describes these rules and their scope.

Each run writes the following files to `outputs/`:

- `mof_ft_train.jsonl` and `mof_ft_holdout.jsonl`: system/user/assistant message records with `P` or `N` labels.
- `mof_ft_class_map.json`: label definitions.
- `mof_ft_split_assignments.csv`: source row, DOI, condition key, cluster, and partition.
- `mof_ft_split_summary.json`: filtering counts, split settings, input hashes, and generated file locations.
- `mof_cls_train_*.jsonl`: publication-year training subsets.
- `demo_summary.json`: compact counts and cluster checks.

## Verify and inspect a saved run

The [expected](expected/) folder contains the training and holdout JSONL, class map, split assignments, and compact summary. `--check` compares these files with the new run. The notebook's separate **Verify against expected output** section repeats the comparison against the current output files and shows expected rows, actual rows, **PASS** or **FAIL**, and details for each file. Files without a tabular row count are still compared for content. These small datasets demonstrate dataset preparation and are separate from the full training and holdout datasets.

Each run preserves an output snapshot and run record under `run_history/<timestamp>/`, while `outputs/` holds the latest generated files. Local history is excluded from Git by default. Open the checked-in [recorded runs](recorded_runs/README.md) or the notebook's executed tables to inspect completed examples on GitHub.

To run another dataset, supply a separate `--config` file and use `--output-dir` for its outputs. The expected-output check applies to the bundled demonstration inputs.
