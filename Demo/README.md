# MOFinder demonstrations

Start with data curation and dataset preparation, which run locally without an API key or GPU. The `03_api_data_mining/` folder groups abstract triage, positive extraction, and negative reconstruction, whose model calls require an API key. All demonstrations use the same Python modules as the full workflow.

| Demonstration | Workflow | API access |
| --- | --- | --- |
| [Data curation](01_data_curation/README.md) | Raw positive extraction records to normalized synthesis records | No |
| [Dataset preparation](02_dataset_preparation/README.md) | Processed positive and negative records to grouped training and holdout JSONL | No |
| [Data mining demo (API required)](03_api_data_mining/README.md) | Abstract triage, positive extraction, and negative reconstruction | Required for model calls; input validation runs offline |

The demonstrations include executable Python scripts, Markdown instructions, and notebooks. The two offline notebooks retain saved outputs and expected-result checks. The [data mining walkthrough](03_api_data_mining/mof_api_data_mining_demo.ipynb) starts with empty outputs; run its preview cells to inspect the abstracts, requests, and document validation before enabling model calls.

## Run the offline demonstrations

Use Python 3.10 or newer. From the repository root:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_curation/mof_data_curation_demo.py --check
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --positive-csv Demo/01_data_curation/outputs/mof_extraction_6.csv --check
```

The first demonstration regenerates processed records from the raw example. The second prepares classification records and grouped splits. `--check` compares the generated files with the saved expected results. Each notebook has a separate **Verify against expected output** section with expected/actual counts and **PASS** or **FAIL** results. See each folder's README for inputs, settings, output files, and use with other data.

Each offline run keeps its output snapshot and run record in a new `run_history/<timestamp>/` folder. `outputs/` holds the latest files. Local histories are excluded from Git by default; the checked-in [data curation runs](01_data_curation/recorded_runs/README.md) and [dataset preparation runs](02_dataset_preparation/recorded_runs/README.md), together with executed notebook outputs, preserve examples that can be viewed on GitHub.

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

For the [data mining demo (API required)](03_api_data_mining/README.md), install `.[mining,notebook]` and open [mof_api_data_mining_demo.ipynb](03_api_data_mining/mof_api_data_mining_demo.ipynb). Inspect the four abstracts and request previews, then set `RUN_TRIAGE = True` to obtain predictions using GPT-5 with high reasoning effort. The same notebook uses `RUN_POSITIVE_EXTRACTION` and `RUN_NEGATIVE_RECONSTRUCTION` for the sample article/SI pair; run positive extraction first. All switches default to `False`. Use `OPENAI_API_KEY` or the hidden key prompt for live calls, which send the selected text to OpenAI and incur API charges.

## Find the workflow code

Offline run records preserve input and output hashes; Python source hashes normalize line endings to UTF-8/LF so the same code can be checked on Windows and Linux. Dataset hashes preserve the original bytes.

The full workflow is documented in [the Markdown workflow guide](../docs/workflow.md), with runnable Python under [src/mofinder/](../src/mofinder/). The [source-to-code guide](../docs/source_to_code.md) maps the original implementation to the current functions and links its Git history. The notebooks provide interactive examples; completed runs save their outputs locally as described in each demonstration's instructions.

The numbered subfolders above replace the earlier notebooks and datasets at the top level of `Demo/`. Those earlier files and their original processing configuration remain accessible in the [historical Demo directory](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo). The original [name–SMILES mappings](../data/name_SMILES_mappers/README.md) are included separately in the current dataset.
