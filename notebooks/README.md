# Notebook walkthroughs

The notebooks call the Python modules used by the command-line workflow. Scientific rules and model calls are implemented in `src/mofinder/`; prompts and settings have separate files.

| Notebook | Purpose |
| --- | --- |
| `01_abstract_triage.ipynb` | Triage validation, screening, and saved-run analysis |
| `02_document_matching.ipynb` | Match article/SI files and inspect optional document counts |
| `03_positive_extraction.ipynb` | Validate documents, mine positive records, and recover CSVs from JSON |
| `04_negative_reconstruction.ipynb` | Validate eligible positives, mine negative plans, and enumerate conditions |
| `05_data_curation.ipynb` | Validate the molecular-weight lookup and run positive/negative curation |
| `06_dataset_preparation.ipynb` | Use the included processed positive/negative records to prepare final JSONL and split records |
| `07_holdout_evaluation.ipynb` | Validate the holdout dataset and evaluate configured models |
| `08_quest_evaluation.ipynb` | Evaluate the 22-question panel over repeated rounds |
| `09_human_benchmark.ipynb` | Analyze anonymous human responses |

Install the dependencies for the stages being used and `.[notebook]`, then start Jupyter from the repository root. Each walkthrough resolves the repository root when opened from `notebooks/` as well.

The matching walkthrough runs the included local demonstration directly. Live screening/mining, curation, and dataset-preparation runs are disabled initially. Review the configuration and validation results before enabling their explicit run switches. Local input validation reports missing files without dispatching model calls. See [workflow](../docs/workflow.md) for terminal equivalents and required inputs.

Dataset preparation defaults to the bundled CSVs and publication years in `data/processed_data/`. It writes to `results/datasets/conditions/`; the bundled final JSONL and assignments are in `data/final_json/`. Select `configs/dataset_preparation_from_curation.json` after running curation, or `configs/dataset_preparation_corrected.json` for the linker-corrected negative data.

The earlier numbered scripts are available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a); their historical counts and settings are documented separately in the [historical workflow](../docs/legacy_workflow.md).

Live API notebooks prompt for a key through hidden input when their run switch is enabled and `OPENAI_API_KEY` is unset. The key is kept in the active process environment. The human benchmark walkthrough runs entirely offline.
