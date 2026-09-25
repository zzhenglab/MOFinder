# MOFinder demonstrations

Start with data cleaning and JSONL preparation, which run locally without an API key or GPU. The `03_api_demo/` folder groups abstract triage and data mining, whose model calls require an API key. All demonstrations use the same Python modules as the full workflow.

| Folder | Workflow | API access |
| --- | --- | --- |
| [01_data_cleaning](01_data_cleaning/README.md) | Raw positive extraction records to normalized synthesis records | No |
| [02_json_preparation](02_json_preparation/README.md) | Processed positive and negative records to grouped training/holdout JSONL | No |
| [03_api_demo](03_api_demo/README.md) | Abstract triage and positive/negative data mining | Required for model calls; input validation runs offline |

The demonstrations include executable Python scripts, Markdown instructions, and notebooks with saved outputs. The [API walkthrough](03_api_demo/mof_api_demo.ipynb) combines abstract triage and positive/negative data mining in one notebook; its checked-in output shows offline previews and validation.

## Run the offline demonstrations

Use Python 3.10 or newer. From the repository root:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_cleaning/mof_cleaning_demo.py --check
python Demo/02_json_preparation/mof_json_preparation_demo.py --positive-csv Demo/01_data_cleaning/outputs/mof_extraction_6.csv --check
```

The first command regenerates cleaned records from the raw example. The second prepares classification records and grouped splits. `--check` compares the generated files with the saved expected results. Each notebook has a separate **Verify against expected output** section with expected/actual counts and **PASS** or **FAIL** results. See each folder's README for inputs, settings, output files, and use with other data.

Each offline run keeps its output snapshot and run record in a new `run_history/<timestamp>/` folder. `outputs/` holds the latest files. Local histories are excluded from Git by default; the checked-in [cleaning run](01_data_cleaning/saved_run/run_record.json) and [JSON preparation run](02_json_preparation/saved_run/run_record.json), together with executed notebook outputs, preserve examples that can be viewed on GitHub.

To check abstract inputs and match the included article/SI pair:

```bash
python -m pip install -e ".[mining]"
python Demo/03_api_demo/mof_api_demo.py validate
```

For interactive use, install the optional notebook dependencies and open a walkthrough in the relevant folder:

```bash
python -m pip install -e ".[notebook]"
jupyter lab
```

For the [API demo](03_api_demo/README.md), install `.[mining,notebook]` and open [mof_api_demo.ipynb](03_api_demo/mof_api_demo.ipynb). Inspect the four abstracts and request previews, then set `RUN_TRIAGE = True` to obtain GPT predictions. The same notebook uses `RUN_POSITIVE_MINING` and `RUN_NEGATIVE_MINING` for the sample article/SI pair; run positive mining first. All switches default to `False`. Use `OPENAI_API_KEY` or the hidden key prompt for live calls, which send the selected text to OpenAI and incur API charges.

## Find the workflow code

Offline run records preserve input and output hashes; Python source hashes normalize line endings to UTF-8/LF so the same code can be checked on Windows and Linux. Dataset hashes preserve the original bytes.

The full workflow is documented in [the Markdown workflow guide](../docs/workflow.md), with runnable Python under [src/mofinder/](../src/mofinder/). The [source-to-code guide](../docs/source_to_code.md) maps the original implementation to the current functions and links its Git history. The notebooks in these demo folders provide interactive examples and saved run outputs.

The numbered subfolders above replace the earlier notebooks and datasets at the top level of `Demo/`. Those earlier files and their original processing configuration remain accessible in the [historical Demo directory](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo). The original [name–SMILES mappings](../data/name_SMILES_mappers/README.md) are included separately in the current dataset.
