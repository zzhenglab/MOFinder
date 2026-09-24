# Notebook and Python code map

The notebooks call the Python implementation in `src/mofinder/`. The command-line workflows and demonstrations use the same functions. Prompts, model settings, file locations, and benchmark records are stored separately so they can be inspected without searching through notebook cells.

Cell numbers below are zero-based positions in the source notebooks, including Markdown cells. They are not Jupyter execution counts.

| Source workflow and cells | Current notebook or entry point | Python implementation |
| --- | --- | --- |
| Abstract triage: cells 2, 4, 6–10 | [01_abstract_triage.ipynb](../notebooks/01_abstract_triage.ipynb) | [literature/triage.py](../src/mofinder/literature/triage.py): `validate_inputs`, `classify_one`, `prepare_screening`, `screen_all` |
| Triage statistics and annotation agreement: cells 12, 14, 16 | Same notebook | [evaluation/triage.py](../src/mofinder/evaluation/triage.py): `evaluate_counts`, `evaluate_run`; [literature/triage.py](../src/mofinder/literature/triage.py): `agreement_values` |
| Triage figures: cell 18 | Same notebook | [plotting/triage.py](../src/mofinder/plotting/triage.py): `plot_results` |
| Main-article retrieval: cell 0 | [fetch_papers.py](../tools/literature_retrieval/fetch_papers.py) | [literature_retrieval/papers.py](../src/mofinder/literature_retrieval/papers.py): `App`, `run_actions_then_save`, `run_icons_then_save` |
| SI retrieval: cell 0 | [fetch_si.py](../tools/literature_retrieval/fetch_si.py) | [literature_retrieval/si.py](../src/mofinder/literature_retrieval/si.py): `App`, `publisher_a_si_flow`, `publisher_w_si_flow`, `publisher_r_si_flow`, `publisher_s_si_flow`, `publisher_e_si_flow` |
| Article/SI matching and counts: cell 3 | [02_document_matching.ipynb](../notebooks/02_document_matching.ipynb) | [literature/match_documents.py](../src/mofinder/literature/match_documents.py): `match_documents`, `count_documents`, `plot_counts` |
| Positive extraction: cell 1 | [03_positive_extraction.ipynb](../notebooks/03_positive_extraction.ipynb) | [extraction/positive.py](../src/mofinder/extraction/positive.py): `extract_one`, `flatten_row`, `save_json_payloads`, `run`; [extraction/schemas.py](../src/mofinder/extraction/schemas.py): `ArticleExtraction` and its component models |
| Recovery from saved positive JSON: cell 8 | Same notebook | [extraction/backfill.py](../src/mofinder/extraction/backfill.py): `flatten_rows_from_article_dir`, `backfill_from_json` |
| Negative plan mining: cell 1 | [04_negative_reconstruction.ipynb](../notebooks/04_negative_reconstruction.ipynb) | [extraction/negative.py](../src/mofinder/extraction/negative.py): `_neg_build_plan`, `flatten_plan_rows`, `process_negative_item_yes`, `run_negative` |
| Negative enumeration: cell 3 | Same notebook | [extraction/enumerate_failures.py](../src/mofinder/extraction/enumerate_failures.py): `read_success_syn`, `enumerate_failures`, `apply_option_corrections` |
| Positive/negative initial cleaning: cell 0 in each notebook | [05_data_curation.ipynb](../notebooks/05_data_curation.ipynb) | [curation/initial.py](../src/mofinder/curation/initial.py): `clean_positive`, `clean_negative`; [curation/times.py](../src/mofinder/curation/times.py): `parse_time_hours`, `normalize_time_hours` |
| Metal cleaning: positive cell 3; negative cell 2 | Same notebook | [curation/metals.py](../src/mofinder/curation/metals.py): `clean`; [curation/formula.py](../src/mofinder/curation/formula.py): `parse_formula_counts`, `molar_mass` |
| Linker cleaning: positive cell 5; negative cell 3 | Same notebook | [curation/linkers.py](../src/mofinder/curation/linkers.py): `clean_positive`, `clean_negative` |
| Solvent cleaning: positive cell 6; negative cell 4 | Same notebook | [curation/solvents.py](../src/mofinder/curation/solvents.py): `clean` |
| Ratios and concentration: positive cell 7; negative cell 5 | Same notebook | [curation/features.py](../src/mofinder/curation/features.py): `clean` |
| Connectivity: positive cell 8; negative cell 6 | Same notebook | [curation/connectivity.py](../src/mofinder/curation/connectivity.py): `clean` |
| Descriptions: positive cell 9; negative cell 7 | Same notebook | [curation/descriptions.py](../src/mofinder/curation/descriptions.py): `clean_positive`, `clean_negative` |
| Summary tables and positive trimming: positive cells 10–11 | Same notebook | [curation/reporting.py](../src/mofinder/curation/reporting.py): `summarize`; [curation/trimming.py](../src/mofinder/curation/trimming.py): `apply_p_trimming` |
| Dataset preparation: cells 1–2 | [06_dataset_preparation.ipynb](../notebooks/06_dataset_preparation.ipynb) | [datasets/prepare.py](../src/mofinder/datasets/prepare.py): `row_to_conditions`, `build_cluster_key`, `choose_holdout_clusters`, `enforce_equal_pn_ratio`, `prepare` |
| HPC records and prompt: `hpc/legacy_0920.py` | [prepare_hpc.py](../tools/training/prepare_hpc.py), [train_hpc.py](../tools/training/train_hpc.py) | [training/records.py](../src/mofinder/training/records.py): `read_message_rows`, `read_manual_rows`, `render_prompt`; [training/prepare.py](../src/mofinder/training/prepare.py): `prepare_bundle`, `validate_bundle` |
| HPC LoRA and P/N loss: `hpc/legacy_0920.py` | Same entry points | [training/modeling.py](../src/mofinder/training/modeling.py): `make_dataset`, `PnDataCollator`, `NativeLmClassifier`, `classification_loss`, `make_lora_config` |
| HPC training loop and scheduled evaluations: `hpc/train_one.py` | [train_hpc.py](../tools/training/train_hpc.py) | [training/train.py](../src/mofinder/training/train.py): `run`; [training_hpc.json](../configs/training_hpc.json): training recipe and evaluation schedule |
| HPC validation and prediction exports: `hpc/common.py` | Same entry points | [training/common.py](../src/mofinder/training/common.py): `inspect_jsonl`, `binary_metrics`, `export_predictions` |
| Holdout evaluation: cells 1, 3, 4 | [07_holdout_evaluation.ipynb](../notebooks/07_holdout_evaluation.ipynb) | [evaluation/holdout.py](../src/mofinder/evaluation/holdout.py): `build_messages`, `extract_logprobs_for_label`, `evaluate_holdout`, `sanity_test` |
| MOF Quest conditions, evaluation, and model groups: cells 0–7 | [08_quest_evaluation.ipynb](../notebooks/08_quest_evaluation.ipynb) | [evaluation/quest.py](../src/mofinder/evaluation/quest.py): `build_messages_from_question`, `call_model_generic`, `evaluate_mof_classifier`, `analyze_results` |
| Human response workbook and calculations | [09_human_benchmark.ipynb](../notebooks/09_human_benchmark.ipynb) | [evaluation/human_quest.py](../src/mofinder/evaluation/human_quest.py): `read_workbook`, `export_workbook`, `analyse` |

## Prompts and configuration

| Material | Location |
| --- | --- |
| Abstract-screening prompt | [abstract_triage.txt](../prompts/abstract_triage.txt) |
| Positive-extraction prompts | [positive_system.txt](../prompts/positive_system.txt), [positive_user.txt](../prompts/positive_user.txt) |
| Negative-plan prompts | [negative_system.txt](../prompts/negative_system.txt), [negative_user.txt](../prompts/negative_user.txt) |
| Shared reaction-prediction prompt for datasets, MOF Quest, and HPC training | [reaction_prediction.txt](../prompts/training/reaction_prediction.txt) |
| Publication-specific linker prime corrections | [linker_prime_corrections.json](../data/organic_linker_info/linker_prime_corrections.json) |
| Paths, model groups, and run settings | [configs/](../configs/) |
| Manual negative-enumeration rules | [negative_corrections.json](../configs/negative_corrections.json) |
| MOF Quest condition records and human responses | [benchmarks/mof_quest/](../benchmarks/mof_quest/) |
| Source cell checksums | [workflow_sources.json](workflow_sources.json) |

## Reading the implementation

Most cleaning helpers retain their original names inside the relevant `clean` function. For example, `normalize_entry` is in `curation/metals.py`, `convert_row` is in `curation/linkers.py`, and `classify` is in `curation/connectivity.py`. The stage order and output paths are defined in [curation/pipeline.py](../src/mofinder/curation/pipeline.py).

The [curation guide](curation.md) documents branch-specific filters, formula-mass calculations, the H3BTB alias, and time-text conventions. The [dataset guide](datasets.md) defines the input fields, clustering, label conflicts, and split settings. Request parameters and metric definitions are described in the [triage](triage.md), [holdout](holdout_evaluation.md), and [MOF Quest](quest_evaluation.md) guides.

The [HPC training guide](training_hpc.md) describes the single-dataset GPT-oss-20B recipe. Dataset preparation copies the existing train/holdout split and generates the 22-question input from the current panel. The training command retains the source loss, LoRA settings, fixed threshold, and evaluation schedule. The final adapter can be saved explicitly with `--save-adapter`.
