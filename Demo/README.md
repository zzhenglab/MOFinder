# MOFinder demonstrations

The demonstrations cover input validation, document matching, data cleaning, and JSONL preparation. They use the same Python modules as the full workflow and include small input tables, expected outputs where available, and optional notebook walkthroughs. Offline checks require no API key or GPU.

| Folder | Workflow | API access |
| --- | --- | --- |
| [01_data_cleaning](01_data_cleaning/README.md) | Raw positive extraction records to normalized synthesis records | No |
| [02_json_preparation](02_json_preparation/README.md) | Cleaned positive and negative records to grouped training/holdout JSONL | No |
| [03_abstract_triage](03_abstract_triage/README.md) | Validate a twelve-paper subset of the abstract-triage reference | No |
| [04_literature_retrieval](04_literature_retrieval/README.md) | Input template and article/SI folder layout for local downloading | No; replace placeholder records before downloading |
| [05_data_mining](05_data_mining/README.md) | Match and validate the illustrative article/SI pair; optional extraction | Required for extraction; matching and text validation run offline |
| [additional_demo_api_needed](additional_demo_api_needed/README.md) | Literature triage, positive mining, and negative mining | Required for model calls; local validation runs offline |

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
python Demo/03_abstract_triage/validate_example.py
python -m mofinder.literature.match_documents match --config configs/example_document_matching.json
python -m mofinder.extraction.positive validate --config configs/example_positive_extraction.json
```

For interactive use, install the optional notebook dependencies and open a walkthrough in the relevant folder:

```bash
python -m pip install -e ".[notebook]"
jupyter lab
```

The [API demonstrations](additional_demo_api_needed/README.md) use small literature inputs and the sample article/SI pair. Model requests must be enabled explicitly, and an API key can be entered through a hidden prompt.

The numbered subfolders above replace the earlier notebooks and datasets at the top level of `Demo/`. Those earlier files and their original processing configuration remain accessible in the [historical Demo directory](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo). The original [name–SMILES mappings](../data/name_SMILES_mappers/README.md) are included separately in the current dataset.
