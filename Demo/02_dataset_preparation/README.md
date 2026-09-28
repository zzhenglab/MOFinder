# Dataset preparation demonstration

Prepare condition-classification training and holdout files from 146 processed positive records and 175 processed negative records. This demonstration calls `mofinder.datasets.prepare`, including the same condition builder, conflict handling, cluster split, class balancing, and JSONL writer used for the [full dataset](../../data/processed_data_json/README.md).

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

The demonstration runs on a CPU without API access, typically in less than one minute. For an interactive walkthrough with saved outputs, install the `notebook` extra and open [prepare and verify training and holdout datasets](mof_dataset_preparation_demo.ipynb). The implementation is in [the demonstration script](mof_dataset_preparation_demo.py) and [the main dataset preparation code](../../src/mofinder/datasets/prepare.py); the [dataset guide](../../docs/datasets.md) describes their use.

The notebook previews two P and two N records per split, including their source rows, DOIs, conditions, and JSON. Change `N_PER_LABEL` to adjust the sample size.

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

The [expected](expected/) folder contains the reference JSONL files, class map, split assignments, and summary. `--check` and the notebook's **Verify against expected output** section compare the generated files with these references.

Each run writes its latest files to `outputs/` and saves a snapshot, settings, hashes, and verification results in `run_history/`. Example outputs are available in [recorded runs](recorded_runs/README.md).

To run another dataset, supply a separate `--config` file and use `--output-dir` for its outputs. The expected-output check applies to the bundled demonstration inputs.
