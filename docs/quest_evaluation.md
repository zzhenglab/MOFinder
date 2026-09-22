# MOF Quest model evaluation

This stage evaluates a fixed panel of 22 reaction conditions with 11 positive and 11 negative reference labels. Each configured model is evaluated over repeated rounds using the same classification prompt and metric definitions.

## Inputs and model configuration

- `benchmarks/mof_quest/questions.json` contains the fixed model panel, reference labels, reaction IDs, and difficulty metadata.
- `prompts/dataset_classification.txt` is the exact classification prompt shared with dataset preparation.
- `configs/quest_evaluation.json` defines the model groups and output directory.

Only the eight reaction-condition fields are sent to a model. Question numbers, reaction IDs, difficulty, and reference labels are used for analysis and are excluded from requests. Missing conditions remain JSON `null`.

| Configuration group | Models | Rounds | Reasoning | Web setting |
| --- | --- | ---: | --- | --- |
| `latest_fine_tuned` | Revised MOFinder fine-tuned model | 20 | `none` | False |
| `fine_tuned_comparison` | Four configured fine-tuned models | 20 | `none` | False |
| `fine_tuned_baseline` | Single fine-tuned baseline | 20 | `none` | False |
| `nonreasoning` | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o` | 20 | `none` | False |
| `nonreasoning_web` | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o` | 20 | `none` | True |
| `reasoning` | `gpt-6-astra`, `gpt-5` | 20 | `high` | False |

`latest_fine_tuned` is selected by default and uses `ft:gpt-4.1-2025-04-14:deep-synthesis-lab:mofinder-re:EQdimPJB`. Fine-tuned model IDs are account-specific. Replace model IDs when evaluating models available to another account. The configuration records experiment settings and does not establish current API availability.

Validation checks the configured model and reasoning combinations before making requests. Unsupported settings are reported; no alternative reasoning effort is selected automatically.

The Chat Completions branch does not send web-search tools, even when `use_web_search` is true. Thus `nonreasoning_web` does not perform web search in this implementation. Validation reports this behavior. For Responses models, true adds `{"type": "web_search"}` to the request. Saved rows distinguish the requested `use_web_search` flag from the actual `web_search_enabled` flag.

## Run and analyze

Install the evaluation dependencies:

```bash
python -m pip install -e ".[evaluation]"
python -m mofinder.evaluation.quest validate
python -m mofinder.evaluation.quest validate --group latest_fine_tuned
```

Provide `OPENAI_API_KEY` in the environment, or use the hidden key prompt in `notebooks/08_quest_evaluation.ipynb`. The notebook starts with `RUN_EVALUATION = False`.

```bash
python -m mofinder.evaluation.quest run --group latest_fine_tuned
python -m mofinder.evaluation.quest run --group reasoning
```

Each invocation creates a timestamped directory under `results/evaluation/mof_quest/<group>/`. An explicit `--output-dir` must be empty. The directory contains an input-hash manifest, a metrics summary, and one combined CSV per model. Each CSV contains all rounds. The workflow saves a model's predictions after completing all its rounds and does not resume interrupted runs.

Saved CSVs can be analyzed without an API key:

```bash
python -m mofinder.evaluation.quest analyze path/to/mof_manual_eval_MODEL_reason_none_20rounds.csv --output results/evaluation/mof_quest/reanalysis.json
```

## Request and metric definitions

Chat Completions requests use `temperature=0`, `top_p=1`, `max_tokens=2`, `logprobs=True`, `top_logprobs=5`, and `seed=7`. Responses requests combine the prompt and reaction JSON into one input string. A reasoning object is sent only when the configured effort differs from `none`; the Responses request does not send temperature, top-p, seed, or an output-token limit. The default concurrency is 25, with six attempts per request and capped exponential backoff.

The label parser preserves the first `P` or `N` character in the uppercased response text. The prompt requests exactly one uppercase label. Keep the raw output when auditing responses because longer explanations can satisfy this permissive parser unintentionally. A response without any text is marked empty: response metadata is never parsed as an answer.

Accuracy, precision, recall, and F1 are calculated only from rows with valid `P`/`N` reference and predicted labels. `P` is the positive class, with zero-division metrics set to zero. Reanalysis reports total, scored, and unscored counts for every round. Means and standard deviations summarize per-round metrics; standard deviations use `ddof=0`.

For Chat Completions responses containing both label log probabilities, `prob_P` and `prob_N` normalize the two exponentiated values to sum to one. These are probabilities conditional on the two retrieved label tokens. The Responses branch does not request log probabilities and leaves these fields empty.

## Validation

Offline tests check condition-only requests, Chat and Responses request parameters, label-token normalization, repeated-round metrics, invalid-response counts, empty responses, retry behavior, and input validation. No API requests or fine-tuning jobs are needed for these checks.
