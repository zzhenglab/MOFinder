# MOFinder demo package

This folder contains a minimal demonstration workflow for preparing MOF synthesis records for model fine-tuning.

## Contents

- `demo_01_clean_data.ipynb`: cleans raw positive MOF synthesis extraction records.
- `demo_02_prepare_json_for_fine_tuning.ipynb`: combines cleaned positive records with negative records and prepares JSONL files for model fine-tuning and held-out evaluation.
- `requirements.txt`: Python dependencies for running the notebooks.

## Required input files

Place the following files in this same folder before running the notebooks:

- `mof_extraction.csv`
- `linker and mw.csv`
- `mof_extraction_failures_enum_1_2_3_4_5_6.csv`
- `Full.xlsx`

The notebooks use local relative paths and expect all input files to be in the same folder as the notebooks.

## System requirements

The notebooks are intended to run with Python 3.10 or later on Linux, macOS, or Windows. The demo requires a standard Python environment with Jupyter installed. No non-standard hardware is required for the cleaning and JSONL-preparation workflow.

GPU resources are not required for this demo. GPU resources may be useful for full model fine-tuning outside the scope of this demo.

## Installation

From this folder, create and activate a Python environment, then install the dependencies:

```bash
pip install -r requirements.txt
```

Typical installation time is less than 30 minutes on a standard desktop computer with internet access.

## Demo instructions

Launch Jupyter Notebook or JupyterLab from this folder:

```bash
jupyter lab
```

Run the notebooks in order:

1. `demo_01_clean_data.ipynb`
2. `demo_02_prepare_json_for_fine_tuning.ipynb`

The first notebook generates cleaned intermediate CSV files ending with:

- `mof_extraction_1_2_3_4_5_6.csv`

The second notebook reads this cleaned table together with the negative-reaction table and metadata file, then writes model-ready JSONL files to the `out/` folder.

## Expected outputs

Representative outputs from the second notebook include:

- `out/mof_cls_train.jsonl`
- `out/mof_cls_holdout.jsonl`
- `out/mof_cls_split_summary.json`
- `out/mof_sft_train.jsonl`
- `out/mof_sft_holdout.jsonl`

The expected runtime for the demo is less than 30 minutes on a standard desktop computer, depending on the size of the input files.

## Instructions for use on other data

To run the workflow on new data, place files with the same schema and filenames in this folder, then rerun both notebooks from top to bottom. The workflow performs positive-record cleaning, normalization, descriptor generation, train/holdout splitting, and JSONL export for fine-tuning workflows.

## Notes on API keys

The demo notebooks do not require hard-coded API keys. If optional API-based steps are added later, credentials should be supplied through environment variables rather than written into notebooks.
