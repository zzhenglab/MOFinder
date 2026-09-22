# Historical workflow

This document describes the historical workflow at [commit `bb6502b`](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a). Dataset counts, model settings, dependency versions, and measured runtimes below refer to that implementation. See the [root README](../README.md) and [installation guide](installation.md) for the current workflow and environment.

The current version replaces the old numbered scripts, `eval/`, `visualization/`, top-level demo files, and old datasets. The paths and commands below refer to the historical checkout. Use the links below to inspect those files, or check out that commit in a separate clone before following its commands. The current version preserves the `MOF-Quest`, `SMILESearcher`, and `WebApplication` submodule commits and configuration, together with the MIT license.

| Historical path | Files at `bb6502b` |
| --- | --- |
| `Demo/` | [Original notebooks and demo inputs](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo) |
| `data/` | [Original datasets and research outputs](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/data) |
| `step_1_literature_classification/` | [Literature classification scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_1_literature_classification) |
| `step_2_fetching/` | [Article and SI retrieval scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_2_fetching) |
| `step_3_mining/` | [Positive and negative extraction scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_3_mining) |
| `step_4_cleansing/` | [Data cleaning scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_4_cleansing) |
| `step_5_assembly/` | [Dataset assembly scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_5_assembly) |
| `eval/` | [Historical evaluation scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/eval) |
| `visualization/` | [Historical plotting scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/visualization) |

MOFinder
========

MOFinder is a research codebase for mining metal-organic framework (MOF) synthesis recipes from the chemistry literature, reconstructing positive and negative reaction records, and assembling datasets for LLM-based MOF synthesis prediction.

<p align="center">
  <img src="../data/mofinder.png" alt="MOFinder overview figure" width="750">
</p>


Checked-in data
---------------

The historical workflow includes raw and cleaned extraction tables, SMILES caches, inferred negative records, and assembled JSONL datasets.

### Positive extraction tables and caches

| File | Description |
| --- | --- |
| `data/mof_extraction.csv` | Raw positive synthesis extraction table from Step 3.2. This is also the starting input for the offline demo. |
| `data/mof_extraction_1.csv` ... `data/mof_extraction_1_2_3_4_5_6.csv` | Successive Step 4 cleaning outputs. The final positive cleaned table contains 15,340 rows before required-field filtering for classifier assembly. |
| `data/name_SMILES_mappers/*.json` | Persistent name-to-SMILES caches generated and used by `SMILESearcher`. |

### Negative extraction table

| File | Description |
| --- | --- |
| `data/mof_extraction_failures_enum_1_2_3_4_5_6.csv` | Cleaned inferred negative reaction table used with the cleaned positive table to assemble the positive/negative classifier dataset. In the classifier assembly demo, required-field filtering and conflict removal yield 18,371 negative records. |

### Assembled JSONL datasets ready for LLM use

These files are already assembled for fine-tuning, preference optimization, or downstream evaluation.

| File | Description |
| --- | --- |
| `data/mof_cls_train.jsonl` | Binary P/N reaction-outcome classifier training set, 28,388 records. Labels: 11,854 positive (`P`) and 16,534 negative (`N`). |
| `data/mof_cls_holdout.jsonl` | Clustered binary P/N classifier holdout set, 3,154 records. Labels: 1,317 positive (`P`) and 1,837 negative (`N`). |
| `data/mof_sft_train.jsonl` | SFT training set for condition prediction or instruction-tuning experiments, 28,388 records. |
| `data/mof_sft_holdout.jsonl` | SFT holdout set for condition prediction or instruction-tuning experiments, 2,034 records. |
| `data/mof_sft_train_pos_only.jsonl` | SFT training set restricted to successful syntheses. |

The classifier JSONL records follow a chat fine-tuning style:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "P"}]}
```

The classifier user message contains a compact reaction-condition JSON object with fields such as:

```json
{
  "metal_precursor": "ZrCl4",
  "organic_linker": "terephthalic acid",
  "modulator": "acetic acid",
  "solvent": "dimethylformamide",
  "metal_concentration_mM": 25.0,
  "M_L_ratio": 1.0,
  "temperature_C": 120.0,
  "time_h": 12.0
}
```



System requirements
-------------------

### Operating systems and Python versions

Python 3.10 or newer is required. The package metadata declares support for Python 3.10, 3.11, and 3.12.

Reported test environment for the historical offline demonstration:

| System | Python | Status |
| --- | --- | --- |
| Windows desktop, exact version: `Windows 11` | `Python 3.11.9` | Core install tested. `pip install -e ".[legacy]"` completed in 5.8 seconds in the tested environment. |


### Core Python dependencies

The historical core runtime used the following minimum dependency versions:

| Dependency | Minimum version |
| --- | --- |
| `pandas` | `>=1.5` |
| `numpy` | `>=1.23` |
| `matplotlib` | `>=3.6` |
| `scikit-learn` | `>=1.2` |
| `openai` | `>=1.40` |
| `pydantic` | `>=2.0` |
| `tiktoken` | `>=0.5` |
| `pypdf` | `>=4.0` |
| `openpyxl` | `>=3.1` |
| `requests` | `>=2.28` |
| `tqdm` | `>=4.64` |
| `rich` | `>=13.0` |
| `python-dotenv` | `>=1.0` |
| `ipywidgets` | `>=8.0` |
| `nest_asyncio` | `>=1.5` |

### Optional dependency groups

| Extra | Purpose | Dependencies |
| --- | --- | --- |
| `fetch-gui` | Desktop PDF and SI downloader tools | `pyautogui>=0.9.54`, `pyperclip>=1.8`, `pynput>=1.7`, `opencv-python>=4.7` |
| `fetch-web` | Selenium-backed web resolvers | `selenium>=4.10`, `webdriver-manager>=4.0` |
| `chem` | RDKit-backed SMILES validation | `rdkit>=2023.3` |
| `notebook` | JupyterLab or notebook interface | `jupyterlab>=4.0`, `notebook>=7.0` |
| `all` | Full research environment | all optional dependencies above |

For command-line notebook execution, install notebook support and `nbconvert`:

```bash
pip install -e ".[legacy,notebook]" nbconvert ipykernel
```

### External services

| Service | Required for | Not required for |
| --- | --- | --- |
| OpenAI API key | Step 1 LLM classification, Step 3 LLM extraction, API-based evaluation, optional gpt-4.1 JSON runs | Offline demo |
| Publisher or institutional access | Step 2 article and Supporting Information download | Offline demo |
| Hugging Face model weights | Optional local inference with the trained open-weight model | Offline demo and JSONL preparation |

### Hardware requirements

No GPU is required for the offline demo or for deterministic data processing.

A normal laptop or desktop computer with CPU and standard memory is sufficient for:

- Installing the core package
- Running `demo_01_clean_data.ipynb`
- Running `demo_02_prepare_json_for_fine_tuning.ipynb`
- Reading and validating the checked-in JSONL files

Optional local inference with `StarLiu714/GPT-oss-MOF` requires hardware suitable for a 20B-parameter language model. This is not part of the required offline demonstration.


### Demo files

For a local demonstration, use the offline demo in `Demo/`. The demo runs from the checked-in extraction table to cleaned reaction records and then prepares model-ready positive/negative JSONL files for fine-tuning.

The demo does **not** require:

- OpenAI API access
- Hugging Face model weights
- GPU hardware
- Chrome automation
- Publisher access

From the repository root:

```bash
pip install -e ".[legacy,notebook]"
cd Demo
python -m jupyter nbconvert --to notebook --execute demo_01_clean_data.ipynb --output demo_01_clean_data_executed.ipynb
python -m jupyter nbconvert --to notebook --execute demo_02_prepare_json_for_fine_tuning.ipynb --output demo_02_prepare_json_for_fine_tuning_executed.ipynb
cd ..
```

Expected main outputs:

```text
Demo/mof_extraction_1_2_3_4_5_6.csv
Demo/out/mof_cls_train.jsonl
Demo/out/mof_cls_holdout.jsonl
Demo/out/mof_cls_class_map.json
Demo/out/mof_cls_split_summary.json
```

Measured runtime on the tested Windows desktop: 9.6 seconds for Demo 01 and 105 seconds for Demo 02, approximately 1 minute 55 seconds total excluding installation.


### Demo-generated classifier files

`demo_02_prepare_json_for_fine_tuning.ipynb` writes the following files under `Demo/out/`:

| File | Description |
| --- | --- |
| `Demo/out/mof_cls_train.jsonl` | Main P/N classifier training set, 28,388 records. |
| `Demo/out/mof_cls_holdout.jsonl` | Main clustered holdout set, 3,154 records. |
| `Demo/out/mof_cls_class_map.json` | Class map for `P` and `N`. |
| `Demo/out/mof_cls_split_summary.json` | Summary of filtering, conflict removal, cluster split, label counts, and year subsets. |
| `Demo/out/mof_cls_train_1999to2012.jsonl` | Year-bin training subset, 6,521 records. Labels: 2,571 `P`, 3,950 `N`. |
| `Demo/out/mof_cls_train_2013to2016.jsonl` | Year-bin training subset, 7,679 records. Labels: 3,094 `P`, 4,585 `N`. |
| `Demo/out/mof_cls_train_2017to2020.jsonl` | Year-bin training subset, 7,547 records. Labels: 3,081 `P`, 4,466 `N`. |
| `Demo/out/mof_cls_train_2021to2025.jsonl` | Year-bin training subset, 6,640 records. Labels: 3,107 `P`, 3,533 `N`. |
| `Demo/out/mof_cls_train_1999to2016.jsonl` | Cumulative year subset, 14,200 records. Labels: 5,665 `P`, 8,535 `N`. |
| `Demo/out/mof_cls_train_1999to2020.jsonl` | Cumulative year subset, 21,747 records. Labels: 8,746 `P`, 13,001 `N`. |

Installation guide
------------------

### Clone the repository

```bash
git clone --recurse-submodules https://github.com/zzhenglab/MOFinder.git
cd MOFinder
```

If the repository was cloned without submodules, initialize `SMILESearcher`:

```bash
git submodule update --init --recursive
```

### Create a Python environment

Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

If PowerShell blocks activation in the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Install MOFinder

Core runtime dependencies:

```bash
pip install -e ".[legacy]"
```

Notebook demo support:

```bash
pip install -e ".[legacy,notebook]" nbconvert ipykernel
```

Full research environment:

```bash
pip install -e ".[all]"
```

Useful optional extras:

```bash
pip install -e ".[fetch-gui]"   # Tk/PyAutoGUI downloader tools
pip install -e ".[fetch-web]"   # Selenium-backed web resolvers
pip install -e ".[chem]"        # RDKit-backed SMILES validation
pip install -e ".[legacy,notebook]"    # JupyterLab / notebook UI
```

### Verify installation

```bash
python - <<'PY'
import pandas
import numpy
import sklearn
import openai
import pydantic
import pypdf
import openpyxl
print("MOFinder core dependencies import successfully.")
PY
```

Windows PowerShell alternative:

```powershell
python -c "import pandas, numpy, sklearn, openai, pydantic, pypdf, openpyxl; print('MOFinder core dependencies import successfully')"
```

### Typical installation time

On the tested Windows desktop environment, the command below completed in 5.8 seconds:

```powershell
Measure-Command { pip install -e ".[legacy]" }
```

A fresh environment without cached wheels may take longer depending on network speed. Installing the full optional environment, especially RDKit and browser automation dependencies, may take several minutes.


Demo
----

The demo is in `Demo/` and consists of two notebooks.

### Demo input files

The following files should be present in `Demo/`:

| File | Purpose |
| --- | --- |
| `Demo/mof_extraction.csv` | Raw positive extraction table. |
| `Demo/linker and mw.csv` | Linker lookup table used during cleaning. |
| `Demo/Full.xlsx` | Paper metadata table with DOI and publication year. |
| `Demo/mof_extraction_failures_enum_1_2_3_4_5_6.csv` | Cleaned inferred negative reaction table. |
| `Demo/demo_01_clean_data.ipynb` | Cleans positive extraction records. |
| `Demo/demo_02_prepare_json_for_fine_tuning.ipynb` | Builds model-ready P/N JSONL files. |

### Run Demo 01: clean positive synthesis records

From the repository root:

```bash
cd Demo
python -m jupyter nbconvert --to notebook --execute demo_01_clean_data.ipynb --output demo_01_clean_data_executed.ipynb
```

Expected outputs:

```text
Demo/mof_extraction_1.csv
Demo/mof_extraction_1_2.csv
Demo/mof_extraction_1_2_3.csv
Demo/mof_extraction_1_2_3_4.csv
Demo/mof_extraction_1_2_3_4_5.csv
Demo/mof_extraction_1_2_3_4_5_6.csv
Demo/metal_linker_pairs_report_all.csv
Demo/metal_linker_pairs_report_all_missing.csv
```

Expected final positive cleaned table:

```text
Rows: 15,340
Main file: Demo/mof_extraction_1_2_3_4_5_6.csv
```

### Run Demo 02: prepare JSONL files for fine-tuning

Continue from the `Demo/` folder:

```bash
python -m jupyter nbconvert --to notebook --execute demo_02_prepare_json_for_fine_tuning.ipynb --output demo_02_prepare_json_for_fine_tuning_executed.ipynb
cd ..
```

Expected outputs:

```text
Demo/out/mof_cls_train.jsonl
Demo/out/mof_cls_holdout.jsonl
Demo/out/mof_cls_class_map.json
Demo/out/mof_cls_split_summary.json
Demo/out/mof_cls_train_1999to2012.jsonl
Demo/out/mof_cls_train_2013to2016.jsonl
Demo/out/mof_cls_train_2017to2020.jsonl
Demo/out/mof_cls_train_2021to2025.jsonl
Demo/out/mof_cls_train_1999to2016.jsonl
Demo/out/mof_cls_train_1999to2020.jsonl
```

Expected Demo 02 summary:

```text
Input rows total: 37,878
Rows kept after required field checks: 34,419
Rows skipped required: 3,459
Rows with same input JSON but both P and N: 2,877
Rows after conflict drop: 31,542
Unique clusters: 10,291
Holdout clusters: 1,060
Train rows: 28,388, labels = {'P': 11854, 'N': 16534}
Holdout rows: 3,154, labels = {'P': 1317, 'N': 1837}
```

### Demo runtime

The following runtimes were measured on the tested Windows desktop environment. Demo 01 timing is the sum of the timed stages reported by the notebook; full command-line execution through `nbconvert` may differ slightly depending on notebook startup overhead.

| Task | Runtime on tested Windows desktop |
| --- | --- |
| Core install, `pip install -e ".[legacy]"` | 5.8 seconds |
| Demo 01, clean positive records | 9.6 seconds total across timed stages: 1.5, 2.1, 0.9, 0.5, 0.8, 0.9, 0.8, and 2.1 seconds |
| Demo 02, prepare JSONL | 105 seconds, approximately 1 minute 45 seconds |
| End-to-end offline demo, excluding install | 114.6 seconds, approximately 1 minute 55 seconds |
| Optional API-based gpt-4.1 JSON run | approximately 1 hour in author tests |

PowerShell timing commands:

```powershell
cd Demo
Measure-Command { python -m jupyter nbconvert --to notebook --execute .\demo_01_clean_data.ipynb --output demo_01_clean_data_executed.ipynb }
Measure-Command { python -m jupyter nbconvert --to notebook --execute .\demo_02_prepare_json_for_fine_tuning.ipynb --output demo_02_prepare_json_for_fine_tuning_executed.ipynb }
cd ..
```

Generated files under `Demo/out/` and executed notebooks are local outputs. They do not need to be committed unless a release package is being prepared with expected outputs.


Pipeline
--------

```text
WoS / paper metadata
  -> step_1_literature_classification/
       1.1 abstract-only Y/N screening
       1.2 PDF-based Y/N screening
       1.3 evaluation against expert / model labels
  -> step_2_fetching/
       2.1 download main article PDFs
       2.2 download Supporting Information files
  -> step_3_mining/
       3.1 match main PDFs with SI files and count words/tokens
       3.2 extract successful synthesis records with structured LLM output
       3.3 mine and enumerate failed synthesis conditions
  -> step_4_cleansing/
       clean metals, linkers, solvents, stoichiometry, and derived features
  -> step_5_assembly/
       build SFT, classifier, DPO, and clustered holdout JSONL datasets
  -> eval/
       run P/N classifiers, ablations, out-of-distribution probes, and screening
  -> visualization/
       generate result figures
```

The cumulative CSV suffixes in `data/` and `Demo/` show the cleaning chain. For example, `mof_extraction_1_2_3_4_5_6.csv` is the positive extraction table after all Step 4 cleaning passes in this workflow.

<p align="center">
  <img src="../data/Figures-03a.png" alt="MOFinder data figure" width="500">
</p>


Instructions for use
--------------------

### Run Step 1 paper classification

Step 1 scripts are resume-safe and write Excel outputs.

Set your OpenAI API key first:

```bash
export OPENAI_API_KEY="sk-..."
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

Abstract-only screening:

```bash
python step_1_literature_classification/1_1_classify_abstract.py \
  --input-name data/Full \
  --model gpt-4o-mini
```

PDF-based screening:

```bash
python step_1_literature_classification/1_2_classify_pdf.py \
  --input-folder data/downloaded \
  --model gpt-5 \
  --effort low
```

### Download PDFs and SI files

Step 2 uses desktop automation in Chrome and requires a visible desktop session. Access to the target articles requires the appropriate institutional access or browser login.

```bash
python step_2_fetching/2_1_fetch_paper.py
python step_2_fetching/2_2_fetch_si.py
```

Both tools open a Tkinter UI, remember the last selected workbook, and update download status columns in the workbook.

### Match PDFs/SI and extract syntheses

Build the DOI/Main File/SI File workbook for extraction:

```bash
python step_3_mining/3_1_match_and_count.py \
  --excel data/"SELECTED 7000 SI - Copy.xlsx" \
  --main-folder data/downloaded \
  --si-folder data/"SI downloaded"
```

Extract successful synthesis records:

```bash
python step_3_mining/3_2_mine_synthesis.py \
  --excel data/"SELECTED 7000 SI - Copy - simple.xlsx" \
  --csv-out data/mof_extraction.csv \
  --json-dir data/mof_json_store \
  --model gpt-5 \
  --concurrency 5
```

Rebuild the CSV from saved JSON without API calls:

```bash
python step_3_mining/3_2_mine_synthesis.py --backfill
```

Negative mining is split into a planning pass and an enumeration pass. The default command runs both:

```bash
python step_3_mining/3_3_mine_negative.py \
  --task all \
  --positive-csv data/mof_extraction.csv \
  --success-dir data/mof_json_store
```

### Clean extraction tables

Run the positive branch end to end using files under `data/`:

```bash
python step_4_cleansing/run_cleansing.py --branch positive
```

Run positive cleaning on a custom directory, such as `Demo/`:

```bash
python step_4_cleansing/run_cleansing.py --branch positive --data-dir Demo
```

Other branches are available for negative data:

```bash
python step_4_cleansing/run_cleansing.py --branch negative-plans
python step_4_cleansing/run_cleansing.py --branch negative-basic
```

Those branches require the corresponding negative raw CSVs from Step 3.3.

### Prepare model-ready JSONL files

The checked-in classifier JSONL files are already available under `data/`. To regenerate the classifier JSONL from cleaned positive and negative records, run the demo notebook:

```bash
cd Demo
python -m jupyter nbconvert --to notebook --execute demo_02_prepare_json_for_fine_tuning.ipynb --output demo_02_prepare_json_for_fine_tuning_executed.ipynb
cd ..
```

Required inputs:

```text
Demo/mof_extraction_1_2_3_4_5_6.csv
Demo/mof_extraction_failures_enum_1_2_3_4_5_6.csv
Demo/Full.xlsx
```

The repository also contains the Step 5 assembly runner:

```bash
python step_5_assembly/run_assembly.py
python step_5_assembly/run_assembly.py --option d
```

When regenerating classifier datasets with the Step 5 runner, the cleaned negative CSV is required:

```text
data/mof_extraction_failures_enum_1_2_3_4_5_6.csv
```

### Resolve chemical names to SMILES

`SMILESearcher/` is a separate resolver submodule used to fill linker, modulator, and related SMILES columns with a persistent JSON cache.

```bash
cd SMILESearcher
pip install -r requirements.txt
python app.py --csv ../data/mof_extraction_1_2_3_4_5_6.csv \
  --cache ../data/name_SMILES_mappers/name2smiles_1222.json \
  --headless
```

On Windows, `SMILESearcher/start.bat` launches the interactive workflow. See `SMILESearcher/README.md` for resolver details.

### Evaluation and plots

Evaluation wrappers in `eval/` call `eval/eval_engine.py`. They contain fixed model IDs, holdout paths, and output paths for the historical experiments. Edit the constants at the top of each runner before launching a new evaluation.

Examples:

```bash
python eval/run_pn_full.py
python eval/run_20q_challenge.py
```

Plotting scripts in `visualization/` accept command-line input and output paths:

```bash
python visualization/plot_metal_linker_heatmaps.py --help
python visualization/plot_human_llm_performance.py --help
```


Open-weight model
-----------------

In addition to the JSONL files in this repository, the trained open-weight model is available on Hugging Face:

```text
StarLiu714/GPT-oss-MOF
```

Use cases:

- Optional local inference with the trained P/N reaction-outcome model
- Comparison with API-based gpt-4.1 runs
- Reproducing open-weight model evaluation workflows

Notes:

- This model is optional and is not required for the offline demo.
- Local inference requires hardware suitable for a 20B-parameter checkpoint.
- The Hugging Face model card should be kept in sync with this repository, including the repository name, dataset description, license, and example P/N input-output format.


Reproduction instructions
-------------------------

### Offline reproduction of the data-processing demo

```bash
pip install -e ".[legacy,notebook]" nbconvert ipykernel
cd Demo
python -m jupyter nbconvert --to notebook --execute demo_01_clean_data.ipynb --output demo_01_clean_data_executed.ipynb
python -m jupyter nbconvert --to notebook --execute demo_02_prepare_json_for_fine_tuning.ipynb --output demo_02_prepare_json_for_fine_tuning_executed.ipynb
cd ..
```

### API-based extraction or evaluation

API-based LLM runs require an OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

The optional API-based gpt-4.1 JSON run took approximately 1 hour in author tests. The exact time can vary with dataset size, model availability, API rate limits, and network conditions.



License and citation
--------------------

The main MOFinder codebase is licensed under the MIT License. See `LICENSE` for details.

`SMILESearcher/` is included as a Git submodule and is distributed under its own license by its authors. Users should consult the `SMILESearcher` repository and license file before redistributing that component.

If you use MOFinder, the workflow, the dataset, or the public database in your research, please cite the project and link to:

```text
https://mofinder.chemistry.wustl.edu/
```
