# Source code and workflow guides

The working Python implementation is in [`src/mofinder/`](../src/mofinder/). Each guide below explains its inputs, commands, expected outputs, and saved records. Run commands from the repository root after [installation](installation.md). Interactive examples with saved output and verification live under [`Demo/`](../Demo/README.md).

## Current implementation

| Task | Python source | Markdown instructions |
| --- | --- | --- |
| Abstract triage and resume | [literature/triage.py](../src/mofinder/literature/triage.py): `validate_inputs`, `classify_one`, `screen` | [Abstract triage](triage.md) |
| Triage statistics and figures | [evaluation/triage.py](../src/mofinder/evaluation/triage.py): `evaluate_run`; [plotting/triage.py](../src/mofinder/plotting/triage.py): `plot_results` | [Saved-run analysis](triage.md#saved-run-analysis) and [human agreement](triage.md#human-agreement) |
| Literature retrieval | [literature_retrieval/papers.py](../src/mofinder/literature_retrieval/papers.py), [literature_retrieval/si.py](../src/mofinder/literature_retrieval/si.py) | [Literature retrieval](literature_retrieval.md); launchers in [tools/literature_retrieval/](../tools/literature_retrieval/) |
| Document matching and counts | [literature/match_documents.py](../src/mofinder/literature/match_documents.py): `match_documents`, `count_documents`, `plot_counts` | [Document matching](document_matching.md) |
| Positive extraction and response schema | [extraction/positive.py](../src/mofinder/extraction/positive.py): `extract_one`, `flatten_row`, `save_json_payloads`, `run`; [schemas.py](../src/mofinder/extraction/schemas.py): `ArticleExtraction` | [Positive extraction](positive_extraction.md) |
| Recover CSV rows from saved positive JSON | [extraction/backfill.py](../src/mofinder/extraction/backfill.py): `backfill_from_json` | [Positive extraction](positive_extraction.md) |
| Negative reconstruction planning | [extraction/negative.py](../src/mofinder/extraction/negative.py): `_neg_build_plan`, `flatten_plan_rows`, `run_negative` | [Negative reconstruction](negative_reconstruction.md) |
| Negative enumeration and corrections | [extraction/enumerate_failures.py](../src/mofinder/extraction/enumerate_failures.py): `enumerate_failures`, `apply_option_corrections` | [Negative reconstruction](negative_reconstruction.md) |
| Data curation sequence and reports | [curation/pipeline.py](../src/mofinder/curation/pipeline.py), [reporting.py](../src/mofinder/curation/reporting.py): `summarize` | [Data curation](curation.md) |
| Initial curation and durations | [curation/initial.py](../src/mofinder/curation/initial.py): `clean_positive`, `clean_negative`; [times.py](../src/mofinder/curation/times.py): `parse_time_hours`, `normalize_time_hours` | [Curation operations](curation.md#operations-and-outputs) and [reaction times](curation.md#reaction-time-text) |
| Precursors and formula masses | [curation/metals.py](../src/mofinder/curation/metals.py): `clean`; [formula.py](../src/mofinder/curation/formula.py): `parse_formula_counts`, `molar_mass` | [Data curation](curation.md) |
| Linker and solvent normalization | [curation/linkers.py](../src/mofinder/curation/linkers.py): `clean_positive`, `clean_negative`; [solvents.py](../src/mofinder/curation/solvents.py): `clean` | [Branch-specific rules](curation.md#positive-and-negative-differences) |
| Ratios, concentration, connectivity, and descriptions | [curation/features.py](../src/mofinder/curation/features.py), [connectivity.py](../src/mofinder/curation/connectivity.py), [descriptions.py](../src/mofinder/curation/descriptions.py) | [Curation operations](curation.md#operations-and-outputs) |
| Dataset preparation: JSONL, grouped splits, and year subsets | [datasets/prepare.py](../src/mofinder/datasets/prepare.py): `row_to_conditions`, `build_cluster_key`, `choose_holdout_clusters`, `enforce_equal_pn_ratio`, `prepare` | [Dataset preparation](datasets.md) |
| HPC records and training bundles | [training/records.py](../src/mofinder/training/records.py): `read_message_rows`, `read_manual_rows`, `render_prompt`; [prepare.py](../src/mofinder/training/prepare.py): `prepare_bundle`, `validate_bundle` | [HPC training](training_hpc.md); [prepare_hpc.py](../tools/training/prepare_hpc.py) |
| HPC LoRA, P/N loss, and training loop | [training/modeling.py](../src/mofinder/training/modeling.py), [train.py](../src/mofinder/training/train.py), [common.py](../src/mofinder/training/common.py) | [HPC training](training_hpc.md); [train_hpc.py](../tools/training/train_hpc.py) |
| Model evaluation: reaction holdout | [evaluation/holdout.py](../src/mofinder/evaluation/holdout.py): `evaluate_holdout`, `sanity_test`, `analyze_saved` | [Holdout evaluation](holdout_evaluation.md) |
| Model evaluation: MOF Quest | [evaluation/quest.py](../src/mofinder/evaluation/quest.py): `run_evaluation`, `analyze_results` | [Question-panel evaluation](quest_evaluation.md) |
| Human benchmark analysis | [evaluation/human_quest.py](../src/mofinder/evaluation/human_quest.py): `load_benchmark`, `write_analysis`, `export_workbook` | [Human benchmark](human_benchmark.md) |

## Original research code

The original numbered scripts remain browsable at [commit `bb6502b`](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a). These links stay fixed to that implementation:

| Original code | Historical source |
| --- | --- |
| Abstract triage | [step_1_literature_classification/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_1_literature_classification) |
| Literature retrieval | [step_2_fetching/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_2_fetching) |
| Positive extraction and negative reconstruction | [step_3_mining/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_3_mining) |
| Data curation | [step_4_cleansing/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_4_cleansing) |
| Dataset preparation | [step_5_assembly/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/step_5_assembly) |
| Model evaluation | [eval/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/eval) |
| Plotting | [visualization/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/visualization) |
| Original demos and recorded notebook output | [Demo/](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a/Demo) |

[The historical workflow](legacy_workflow.md) documents commands and counts for that checkout. [workflow_sources.json](workflow_sources.json) separately records the supplied research notebooks and training scripts used during the Python migration, their hashes, active source-cell indices, and corresponding modules. That manifest identifies comparison sources; it does not imply that every supplied research notebook was committed in the historical GitHub tree.

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

Most curation helpers retain their original names inside the relevant `clean` function. For example, `normalize_entry` is in `curation/metals.py`, `convert_row` is in `curation/linkers.py`, and `classify` is in `curation/connectivity.py`. The stage order and output paths are defined in [curation/pipeline.py](../src/mofinder/curation/pipeline.py).

The [curation guide](curation.md) documents branch-specific filters, formula-mass calculations, the H3BTB alias, and time-text conventions. The [dataset guide](datasets.md) defines the input fields, clustering, label conflicts, and split settings. Request parameters and metric definitions are described in the [triage](triage.md), [holdout](holdout_evaluation.md), and [MOF Quest](quest_evaluation.md) guides.

The [HPC training guide](training_hpc.md) describes the single-dataset GPT-oss-20B recipe. Dataset preparation copies the existing training and holdout split and generates the 22-question input from the current panel. The training command retains the source loss, LoRA settings, fixed threshold, and evaluation schedule. The final adapter can be saved explicitly with `--save-adapter`.
