# Prompts

`abstract_triage.txt` contains the abstract-screening prompt. Each run records the prompt and its SHA256 digest.

## Document mining and classification

| Prompt files | Use |
| --- | --- |
| `positive_system.txt`, `positive_user.txt` | Structured positive synthesis extraction from article/SI text |
| `negative_system.txt`, `negative_user.txt` | Evidence-supported modification plans for successful syntheses |
| `dataset_classification.txt` | System message in condition-classification training/holdout JSONL |

The corresponding Python module formats the placeholders in each prompt. Prompt edits can change the scientific extraction or classification task and should be associated with a new recorded run.

Source notebook identities and active cells are recorded in `docs/workflow_sources.json`. Negative enumeration corrections are stored in `configs/negative_corrections.json`; the 22 forced benchmark conditions are in `configs/dataset_forced_questions.json`.
