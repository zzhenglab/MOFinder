# Release audit — 22 September 2026

This audit covers the current documentation, demonstrations, execution logic, and bundled datasets. The checks below were run locally on Windows using the isolated Python 3.11 demo environment. Historical integration reports retain their original results; they are separate from this audit.

## Corrections reviewed

- Demonstrations now comprise offline cleaning, offline JSON preparation, and one [API notebook](../Demo/03_api_demo/api_demo.ipynb). Its triage preview shows the selected abstracts and exact requests, rejects changed inputs or settings before dispatch, and compares predictions with the run's saved reference labels. Model calls remain disabled by default.
- New reaction evaluations accept only standalone P/N responses after case and whitespace normalization. The `standalone_pn_v1` protocol and corrected label-token probability attribution prevent ordinary prose from becoming a prediction. Saved CSV analysis retains recorded labels; earlier holdout runs require fresh outputs for new requests. See [evaluation](evaluation.md).
- Negative mining rejects unreadable saved plan CSVs before requests and correctly replaces prior DOI rows during explicit in-place reruns. The API demo also rejects YES-labelled positive DOIs missing from its selected document manifest.
- Dataset preparation, question-panel evaluation, and HPC training use the full [reaction-prediction prompt](../prompts/training/reaction_prediction.txt). HPC bundles use schema version 2; the default 512-token limit raises an error for overlength inputs. Older bundles must be rebuilt. Displayed paths are shortened without changing file-access paths or saved provenance.
- Demo paths, installation dependencies, interpreter/kernel instructions, and validation notes were reconciled. Demo01 preserves the edited input's uppercase availability flags and explicit 72-hour first-record duration, with separate bundled-input provenance. Byte-preservation rules protect hashed prompt and data files across checkouts.

## Current verification

| Check | Result |
| --- | --- |
| Offline regression suite | All 201 tests passed |
| Command-line workflow checks | All 16 checks passed, including dependency consistency, input validation, both offline demos, and training-bundle preparation/validation |
| Notebook execution | All 12 notebooks executed successfully, with live requests disabled |
| Documentation | 54 Markdown files checked; 305 local links/anchors, 48 notebook links, and 16 source-map module paths resolve; all three documentation JSON files parse |
| Provenance hashes | All 16 checked hashes match their distributed artifacts and recorded provenance |
| Final JSONL integrity | All 26,123 records contain the canonical full prompt, eight reaction fields, and manifest-consistent P/N labels |
| Final split integrity | Unique source-row IDs; no shared chemical clusters or exact condition inputs; reserved question conditions absent from training |
| Processed dataset reproduction | 23,528 training and 2,595 holdout records; regenerated training/holdout JSONL are byte-identical to the bundled files |
| Corrected dataset reproduction | 23,436 training and 2,604 holdout records; configured preparation completed successfully |

The 16 hash checks cover five files in [the data manifest](../data/manifest.json), two in [the training manifest](../data/final_json/manifest.json), two in [the processed-table manifest](../data/processed_data/manifest.json), six preparation inputs/configuration/prompt entries in [the split summary](../data/final_json/split_summary.json), and its split-assignment CSV.

Cluster and exact-condition separation do not imply publication separation. The bundled split has **864 shared DOIs**, as documented in [dataset preparation](datasets.md). The corrected dataset is a separate version and retains its own assignments.

## Reproduce and interpret the checks

Install the verification dependencies and run the commands in [the pre-upload checklist](preupload_checklist.md). Keep fresh output directories for dataset reproduction and HPC bundles. Run notebook cells in order with the selected environment and all live switches disabled for an offline check.

Live API calls, desktop downloading, and GPU training were **not executed** in this audit. Mocked responses verify request and scoring behavior, not model performance. GPU tokenization, memory use, and training still require checks in the target environment. GitHub Actions results must be inspected for the published commit; local results do not establish remote CI status.

The earlier [triage](validation.md), [retrieval](literature_retrieval_validation.md), [mining](mining_validation.md), and [evaluation](evaluation_validation.md) reports remain historical evidence of their respective integration checkpoints.
