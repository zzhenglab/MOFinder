MOFinder:  TO DO: For DATA Folder, the csv files and training needs updates
========

This repository is the research codebase for MOFinder, where the pipeline mines Metal-Organic Framework (MOF) synthesis recipes from the chemistry literature and assembling datasets for LLM-based MOF synthesis prediction.

<p align="center">
  <img src="data/TOC%20Figure.png" alt="TOC Figure" width="500">
</p>


Checked-In Data
---------------

The current repository includes cleaned extraction tables, SMILES caches, and assembled JSONL datasets.

### Cleaned extraction tables and caches

| File | Description |
| --- | --- |
| `data/mof_extraction.csv` | Raw positive synthesis extraction table from Step 3.2. |
| `data/mof_extraction_1.csv` ... `data/mof_extraction_1_2_3_4_5_6.csv` | Successive Step 4 cleaning outputs. The final CSV has 13,182 data rows. |
| `data/name_SMILES_mappers/*.json` | Persistent name/SMILES caches generated and used by `SMILESearcher`. |

### Assembled JSONL datasets ready for LLM use

These files are already assembled for fine-tuning, preference optimization, or
downstream evaluation:

| File | Description |
| --- | --- |
| `data/mof_sft_train.jsonl` | SFT training set for condition prediction, 28,320 records. |
| `data/mof_sft_holdout.jsonl` | SFT holdout set, 2,034 records. |
| `data/mof_sft_train_pos_only.jsonl` | SFT training set restricted to successful syntheses. |
| `data/mof_cls_train.jsonl` | Binary synthesizability classifier training set, 27,585 records. |
| `data/mof_cls_holdout.jsonl` | Binary classifier holdout set, 2,922 records. |
| `data/mof_dpo_pairs.jsonl` | DPO preference pairs, 2,215 records. |

These records follow the OpenAI chat fine-tuning style:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```


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
       run PN/PU classifiers, ablations, OOD probes, and screening
  -> visualization/
       generate result figures
```

The cumulative CSV suffixes in `data/` show the cleaning chain. For example,
`mof_extraction_1_2_3_4_5_6.csv` is the positive extraction table after all
currently scripted Step 4 cleaning passes.




Installation
------------

Python 3.10 or newer is required.

```bash
git clone --recurse-submodules <repo-url>
cd MOFinder

# Core runtime dependencies
pip install -e .

# Full research environment: GUI downloader, Selenium, RDKit, notebooks
pip install -e ".[all]"
```

If the repository was cloned without submodules, initialize `SMILESearcher`:

```bash
git submodule update --init --recursive
```

Useful optional extras:

```bash
pip install -e ".[fetch-gui]"   # Tk/PyAutoGUI downloader tools
pip install -e ".[fetch-web]"   # Selenium-backed web resolvers
pip install -e ".[chem]"        # RDKit-backed SMILES validation
pip install -e ".[notebook]"    # JupyterLab / notebook UI
```

Set your OpenAI API key before running Step 1, Step 3, or `eval/` scripts:

```bash
# PowerShell
$env:OPENAI_API_KEY = "sk-..."

# bash/zsh
export OPENAI_API_KEY="sk-..."
```


Codebase Usage
----------------

### Run Step 1 paper classification

Step 1 scripts are resume-safe and write Excel outputs.

```bash
# Abstract-only screening; reads data/Full.xlsx
python step_1_literature_classification/1_1_classify_abstract.py \
  --input-name data/Full \
  --model gpt-4o-mini

# PDF-based screening; reads PDFs from data/downloaded/
python step_1_literature_classification/1_2_classify_pdf.py \
  --input-folder data/downloaded \
  --model gpt-5 \
  --effort low
```

### Download PDFs and SI files

Step 2 is desktop automation, not a headless scraper. It requires Chrome, a visible desktop session, and whatever institutional access or browser login is needed for the target publishers.

```bash
python step_2_fetching/2_1_fetch_paper.py
python step_2_fetching/2_2_fetch_si.py
```

Both tools open a Tkinter UI, remember the last selected workbook, and update download status columns in the workbook.

### Match PDFs/SI and extract syntheses

```bash
# Build the 3-column DOI/Main File/SI File workbook for extraction
python step_3_mining/3_1_match_and_count.py \
  --excel data/"SELECTED 7000 SI - Copy.xlsx" \
  --main-folder data/downloaded \
  --si-folder data/"SI downloaded"

# Extract successful synthesis records
python step_3_mining/3_2_mine_synthesis.py \
  --excel data/"SELECTED 7000 SI - Copy - simple.xlsx" \
  --csv-out data/mof_extraction.csv \
  --json-dir data/mof_json_store \
  --model gpt-5 \
  --concurrency 5

# Rebuild the CSV from saved JSON without API calls
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

Step 4 can run the positive branch end to end using the files under `data/`:

```bash
python step_4_cleansing/run_cleansing.py --branch positive
```

Other branches are available for negative data:

```bash
python step_4_cleansing/run_cleansing.py --branch negative
python step_4_cleansing/run_cleansing.py --branch negative-basic
```

Those branches require the corresponding negative raw CSVs from Step 3.3.

### Assemble classifier datasets

Step 5 builds clustered train/holdout files. Its default option is `d`, the current best strategy in the code: 
year-wise splits, fine lamellae positive/negative interleaving.

```bash
python step_5_assembly/run_assembly.py
python step_5_assembly/run_assembly.py   # default to --option d
```

When regenerating classifier datasets, requires the
cleaned negative CSV:

- `data/mof_extraction_failures_enum_1_2_3_4_5_6.csv`

The checked-in `data/mof_cls_*.jsonl`, `data/mof_sft_*.jsonl`, and
`data/mof_dpo_pairs.jsonl` are already assembled outputs.

### Resolve chemical names to SMILES

`SMILESearcher/` is a separate resolver submodule used to fill linker,
modulator, and related SMILES columns with a persistent JSON cache.

```bash
cd SMILESearcher
pip install -r requirements.txt
python app.py --csv ../data/mof_extraction_1_2_3_4_5_6.csv \
  --cache ../data/name_SMILES_mappers/name2smiles_1222.json \
  --headless
```

On Windows, `SMILESearcher/start.bat` launches the interactive workflow. 
See `SMILESearcher/README.md` for resolver details.


Evaluation and Plots
--------------------

Evaluation wrappers live in `eval/`. 
They are thin scripts around `eval/eval_engine.py` and contain hard-coded model IDs, holdout paths, and output paths for the experiments used in this project. 
Edit the constants at the top of each runner before launching a new evaluation.

Examples:

```bash
python eval/run_pn_full.py
python eval/run_20q_challenge.py
```

Plotting scripts live in `visualization/` and accept CLI inputs/outputs:

```bash
python visualization/plot_metal_linker_heatmaps.py --help
python visualization/plot_human_llm_performance.py --help
```


License and Citation
--------------------

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for details.

If you use the workflow or [database](MOFinder.chemistry.wustl.edu) in your research, please cite the project.

The arXiv link will be available soon.
```bibtex
@article{mofinder2026,
  title = {},
  journal = {arXiv},
  year = {2026}
}
```
