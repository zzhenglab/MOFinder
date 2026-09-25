# Evaluation validation

The original evaluation-integration checkpoint passed **147 tests**. No live evaluation or training requests were made. Source notebook identities are recorded in [workflow_sources.json](workflow_sources.json); structured results are in [evaluation_validation.json](evaluation_validation.json). This historical checkpoint predates the stricter P/N response parsing described below; its source-equivalence results are retained unchanged.

| Check | Result |
| --- | --- |
| Final training and holdout JSONL | Exact byte matches to original source files and verified preparation outputs |
| Final split assignments | 26,123 retained records agree with the training and holdout JSONL; regenerated outputs are byte-identical and clusters do not overlap |
| Processed public tables | All retained values and row order match; four local-path columns removed and UTF-8 byte-order marks added |
| Dataset features after column removal | All 30,403 condition inputs, cluster keys, and DOI mappings unchanged |
| H3BTB correction | Both curation branches resolve the confirmed full name and reference lookup value of 438.4 g/mol |
| Holdout requests | Twelve captured requests and their scientific result rows match the source, including ten-record execution followed by two-record resume |
| Question-panel requests | All 22 conditions/labels match; 46 helper comparisons and 26 request payloads match source behavior |
| Reference-label isolation | No assistant reference answers, gold labels, or difficulty metadata in captured model requests |
| Human benchmark inputs | 98 participants, 22 questions, 2,156 answers |
| Notebook validation | All nine notebooks pass format checks; updated API and new evaluation walkthroughs execute offline from both supported working directories |
| Anonymous exports | No email addresses in the public human benchmark files |

The public table exports retain scientific values from the original processed datasets. New curation runs apply the corrected H3BTB mapping. The bundled JSONL inputs remain unchanged.

## Operational corrections

The holdout workflow records request/input identity and rejects attempts to resume a CSV without a matching manifest. It still permits independent analysis of existing CSVs. Recorded failed attempts remain recorded, following the source resume behavior.

The question evaluator treats a response with no output text as empty; it does not derive a prediction from serialized response metadata. At the checkpoint, the original parser, token-probability calculations, and valid-label metric denominators were preserved. Attempted/scored/failed counts were reported alongside metrics.

New holdout and question-panel requests now accept only a standalone `P` or `N` after case and whitespace normalization. Explanations and other invalid text remain unscored, with raw responses retained. Token-probability fallback uses the actual retrieved label token. Saved CSV analysis continues to use the recorded predictions; it does not silently reparse historical answers. Start a fresh holdout output when moving from the earlier parsing protocol. See [holdout evaluation](holdout_evaluation.md) and [question-panel evaluation](quest_evaluation.md).

## Execution boundary

The source API parameters and fine-tuned model identifiers are preserved; access and live behavior still require an account-specific run. At this checkpoint, notebook API prompts required their live execution switch, and GitHub Actions was configured for offline tests and notebook execution. The validation reported here was performed locally; current commands and demo checks are listed in [the pre-upload checklist](preupload_checklist.md).

The separate positive extraction and negative reconstruction evaluation workflows await their source code and ground-truth files.
