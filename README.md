MOFinder
================================

**LLM-based literature-mining pipeline for Metal–Organic Framework (MOF) synthesis prediction.**

MOFinder is the research codebase accompanying our work on extracting MOF synthesis recipes from the chemistry literature and fine-tuning large language models to:
- classify whether a hypothetical MOF is synthesizable and 
- propose plausible reaction conditions


## Pipeline Overview

```
abstracts (WoS export)
        │
        ▼ step_1_literature_classification/  (1.1 / 1.2)   ─► Y/N: "is this a traditional MOF synthesis paper?"
        │
        ▼   (1.3)         ─► classification metrics vs. expert labels
        │
filtered DOI list
        │
        ▼ step_2_fetching/                    ─► main PDFs + Supporting Information
        │
        ▼ step_3_mining/  (3.1)              ─► main+SI file pairing
        │
        ▼  (3.2)              ─► GPT-5 schema-constrained extraction
        │
        ▼  (3.3)              ─► negative-example mining (failed conditions)
        │
data/mof_extraction*.csv  (+ mof_json_store/)
        │
        ▼ step_4_cleansing/                    ─► rule-based cleaning & synonym merging
        │
data/mof_extraction_1_2_3_4_5_6.csv      (final cleaned table)
        │
        ▼ step_5_assembly/                     ─► SFT / CLS / DPO JSONL, cluster-aware split
        │
data/training/{mof_sft_*,mof_cls_*,mof_dpo_*}.jsonl
        │
        ▼ eval/  (PN / PU / ablations / A,AB,ABC,ABH)   ─► async eval
        ▼ eval/  (6b)               ─► 20-question OOD probe
        ▼ eval/  (6c)               ─► synthesis screening of novel MOFs
        │
        ▼ visualization/            ─► plot figures from our results
```

A separate agentic assistant lives under [`SMILESearcher/`](https://github.com/StarLiu714/SMILESearcher/) submodule which queries public databases and retrieval engine/LLM (PubChem, OPSIN, Wikipedia/Wikidata and ChemSpider databases with a Google/Gemini searching fallback). 
The cleaned-up name-SMILES mapping full metadata lives in [`data/name_SMILES_mappers/`](data/name_SMILES_mappers/). See [`SMILESearcher/README.md`](SMILESearcher/README.md).

The cumulative cleaning suffix (`_1`, `_1_2`, …, `_1_2_3_4_5_6`) on the extraction CSVs shows the data after each step's cleansing.

## Data Description

### `data/mof_extraction*.csv`

Each row is **one synthesis condition for one MOF**, taken from a single paper. The cumulative-cleaning convention is that filename suffixes `_1`, `_1_2`, …, `_1_2_3_4_5_6` indicate which cleaning passes from step 4 have been applied. The final cleaned table is `data/mof_extraction_1_2_3_4_5_6.csv`.

Key column groups (≈90 columns):

| Group | Examples |
|---|---|
| Paper metadata | `DOI`, main PDF path, SI path, journal/publisher |
| Metals | `metal_1`, `metal_1_amount`, `metal_1_unit`, … up to `metal_3` |
| Linkers | `linker_1`, `linker_1_amount`, `linker_1_unit`, …, `linker_n_SMILES_*` |
| Modulators | `modulator_1`, …, `modulator_n_SMILES_*` |
| Solvents | composition and volumes |
| Conditions | temperature, time, vessel, stirring |
| Product | topology, yield %, BET surface area, pore diameter, applications |
| Flags | `synthesizable` (positive / negative), processing notes |

### `data/*.jsonl`

* `mof_sft_train.jsonl`, `mof_sft_holdout.jsonl` — instruction-style SFT records (`{system, user, assistant}`) for **condition prediction**.
* `mof_sft_train_pos_only.jsonl` — same, restricted to successful syntheses.
* `mof_cls_train.jsonl`, `mof_cls_holdout.jsonl` — binary **synthesizability classification** records (positives + step-3.3 negatives).
* `mof_dpo_pairs.jsonl` — Direct Preference Optimization pairs.

### `data/`

* `mof_cls_holdout_metrics.json` — held-out evaluation metrics, written by step 6 notebooks.

### `data/name_SMILES_mappers`

A growing JSON cache mapping cleaned chemical names ⇄ SMILES, produced by `SMILESearcher` and reused across runs.


## Method Notes

* **LLM extraction (step 3.2).** Each paper's main text + SI is fed to GPT-5 under a strict Pydantic schema (`ArticleExtraction`) enforcing one record per unique reaction condition, excluding post-synthetic modifications and non-traditional methods (microwave, mechanochemical). 
* **Negative mining (step 3.3).** Many MOF papers describe condition screens — temperatures, solvents, linker variants — where only one combination yields the framework. We guide the LLM to enumerate the *explicitly tested but unsuccessful* siblings of each successful recipe, producing labeled negatives without hallucinating failures the paper never reported.
* **Cluster-aware splitting (step 5).** Holdout is constructed by clustering on (metal, linker) signatures so that the train and holdout sets do not share the same MOF identity. 
* **Evaluation (step 6).** Two evaluation regimes are supported: **PN** (positive + negative classification) and **PU** (positive-only) as controlled comparison. 


## Reproducing

To reproduce in order:

1. **Install.** From the repo root:

```bash
pip install -e ".[all]"            # core + GUI downloader + Selenium + RDKit + notebook
# or, lighter:
pip install -e .                   # core only
pip install -e ".[fetch-web,chem]" # add what you actually need
```

Either `pyproject.toml` (PEP 517) or `setup.py` (legacy) will produce the same install — see the docstring at the top of [setup.py](setup.py).

2. **Configure.** Set `OPENAI_API_KEY` in your environment. Step 2.1 (paper download) additionally needs a working Chrome plus a logged-in browser session for institutional PDF access. Step 3.2 uses model `gpt-5` (or the latest reasoning model you have access to).

3. **Run notebooks in numerical order.** Open each `stepN_*/` folder in turn. The step 4 and step 5 notebooks resolve CSV and JSONL names relative to Jupyter's working directory, so **launch Jupyter from the `data/` directory** (or set the kernel working directory to `data/`) before running them:

```bash
cd data
jupyter lab   # or: jupyter notebook
```

4. **SMILES resolution.** At any point after step 3, run `SMILESearcher/app.py` (or `start.bat` on Windows) on the current `data/mof_extraction*.csv`, pointing it at `data/name_SMILES_mappers/name2smiles_1222.json` as the persistent cache.


## License and Citation

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

If you use our workflow or our [database](MOFinder.chemistry.wustl.edu) in your research or re-development, please cite:

```bibtex
@article{mofinder2026,
  title={},
  journal={arXiv},
  year={2026}
}
```

