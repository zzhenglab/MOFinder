# MOFinder demonstrations

Start with data curation and dataset preparation, which run locally without an API key or GPU. The `03_api_data_mining/` folder groups abstract triage, positive extraction, and negative reconstruction, whose model calls require an API key. All demonstrations use the same Python modules as the full workflow.

| Demonstration | Workflow | API access |
| --- | --- | --- |
| [Data curation](01_data_curation/README.md) | Raw positive extraction records to normalized synthesis records | No |
| [Dataset preparation](02_dataset_preparation/README.md) | Processed positive and negative records to grouped training and holdout JSONL | No |
| [Data mining demo (API required)](03_api_data_mining/README.md) | Abstract triage, positive extraction, and negative reconstruction | Required for model calls; input validation runs offline |
| [Dataset analysis](04_dataset_analysis/README.md) | Literature coverage, composition, properties, stability, pairwise conditions, and training/test t-SNE | No |

Each demonstration includes a Python script and notebook. The offline notebooks contain saved outputs and verification checks. The data mining notebook previews inputs and requests before making API calls.

## Redraw the dataset and literature figures

The [dataset notebook](04_dataset_analysis/dataset_analysis.ipynb) draws the dataset and literature figures from the included data.

```bash
python -m pip install -e ".[plotting,notebook]"
jupyter lab
```

Run all cells to export PNGs, including synthesis-record and record/DOI versions, at 6-inch width and 600 dpi.

## Run the offline demonstrations
Use Python 3.10 or newer. From the repository root:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_curation/mof_data_curation_demo.py --check
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --positive-csv Demo/01_data_curation/outputs/mof_extraction_6.csv --check
```

The first demonstration curates raw records; the second prepares classification records and grouped splits. `--check` compares the generated files with saved expected results. Each folder's README describes the inputs, settings, and outputs.

Each offline run writes its latest files to `outputs/` and saves a snapshot in `run_history/`. Example [curation runs](01_data_curation/recorded_runs/README.md) and [dataset preparation runs](02_dataset_preparation/recorded_runs/README.md) are included.

To check abstract inputs and match the included article/SI pair:

```bash
python -m pip install -e ".[mining]"
python Demo/03_api_data_mining/mof_api_data_mining_demo.py validate
```

For interactive use, install the optional notebook dependencies and open a walkthrough in the relevant folder:

```bash
python -m pip install -e ".[notebook]"
jupyter lab
```

For data mining, install `.[mining,notebook]` and open [mof_api_data_mining_demo.ipynb](03_api_data_mining/mof_api_data_mining_demo.ipynb). Its three switches enable triage, positive extraction, and negative reconstruction. Run positive extraction before negative reconstruction. All switches default to `False`; live calls use `OPENAI_API_KEY` or a hidden key prompt and incur API charges.

The data mining inputs contain one synthetic article/SI pair and two blank templates. The default notebook uses the synthetic pair.

## Find the workflow code

See the [workflow guide](../docs/workflow.md) for the full pipeline and [src/mofinder/](../src/mofinder/) for the Python modules.
