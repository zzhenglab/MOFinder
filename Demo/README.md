# MOFinder demonstrations

Start with data cleaning and JSONL preparation, which run locally without an API key or GPU. The `03_api_demo/` folder groups abstract triage and data mining, whose model calls require an API key. All demonstrations use the same Python modules as the full workflow.

| Folder | Workflow | API access |
| --- | --- | --- |
| [01_data_cleaning](01_data_cleaning/README.md) | Raw positive extraction records to normalized synthesis records | No |
| [02_json_preparation](02_json_preparation/README.md) | Processed positive and negative records to grouped training/holdout JSONL | No |
| [03_api_demo](03_api_demo/README.md) | Abstract triage and positive/negative data mining | Required for model calls; input validation runs offline |

The [API walkthrough](03_api_demo/api_demo.ipynb) combines abstract triage and positive/negative data mining in one notebook.

## Run the offline demonstrations

Use Python 3.10 or newer. From the repository root:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_cleaning/run_demo.py --check
python Demo/02_json_preparation/run_demo.py --positive-csv Demo/01_data_cleaning/outputs/mof_extraction_1_2_3_4_5_6.csv --check
```

The first command regenerates cleaned records from the raw example. The second prepares classification records and grouped splits. `--check` compares the generated files with the saved expected results. See each folder's README for inputs, settings, output files, and use with other data.

To check abstract inputs and match the included article/SI pair:

```bash
python -m pip install -e ".[mining]"
python Demo/03_api_demo/run_demo.py validate
```

For interactive use, install the optional notebook dependencies and open a walkthrough in the relevant folder:

```bash
python -m pip install -e ".[notebook]"
jupyter lab
```

For the [API demo](03_api_demo/README.md), install `.[mining,notebook]` and open [api_demo.ipynb](03_api_demo/api_demo.ipynb). Inspect the four abstracts and request previews, then set `RUN_TRIAGE = True` to obtain GPT predictions. The same notebook uses `RUN_POSITIVE_MINING` and `RUN_NEGATIVE_MINING` for the sample article/SI pair; run positive mining first. All switches default to `False`. Use `OPENAI_API_KEY` or the hidden key prompt for live calls, which send the selected text to OpenAI and incur API charges.

The numbered subfolders above replace the earlier notebooks and datasets at the top level of `Demo/`. Those earlier files and their original processing configuration remain accessible in the [historical Demo directory](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo). The original [name–SMILES mappings](../data/name_SMILES_mappers/README.md) are included separately in the current dataset.
