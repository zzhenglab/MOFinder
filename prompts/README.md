# Prompts

`abstract_triage.txt` contains the abstract-screening prompt. Each run records the prompt and its SHA256 digest.

## Document mining and classification

| Prompt files | Use |
| --- | --- |
| `positive_system.txt`, `positive_user.txt` | Structured positive synthesis extraction from article/SI text |
| `negative_system.txt`, `negative_user.txt` | Evidence-supported modification plans for successful syntheses |
| `training/reaction_prediction.txt` | Shared instructions for reaction prediction in training/holdout JSONL, MOF Quest evaluation, and GPT-oss-20B training |
| `training/reaction_prediction_process_enrich_11field.txt` | Eleven-field control adding vessel type, vessel capacity in mL, and agitation to the eight baseline inputs |
| `training/reaction_prediction_process_enrich_9field.txt` | Nine-field control adding `stirring`, with definitions of `yes`, `no`, and `not reported` |

The corresponding Python module formats the placeholders in each prompt. Saved run manifests record the prompt used.

Dataset preparation stores `training/reaction_prediction.txt` as the system message; evaluation and local training supply the eight reaction-condition fields separately. The HPC renderer appends `Reaction conditions:`, the condition JSON, and `Label:` to these instructions.

`training/reaction_prediction_process_enrich_11field.txt` changes only that prompt's input list to include `vessel_type`, `vessel_volume_mL`, and `agitation`. It is the canonical prompt source for the [process-enriched JSONL](../data/processed_data_json/processed_enrich_11field/README.md).

Negative enumeration corrections are stored in `configs/negative_corrections.json`; the 22 forced benchmark conditions are in `configs/dataset_forced_questions.json`.
