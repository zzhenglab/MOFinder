# Reaction-condition holdout

The final holdout dataset is [data/processed_data_json/holdout.jsonl](../../data/processed_data_json/holdout.jsonl), beside its companion [training set](../../data/processed_data_json/train.jsonl). It contains 2,595 records: 1,320 P and 1,275 N. File hashes are recorded in [the dataset manifest](../../data/processed_data_json/manifest.json).

[Split assignments and parameters](../../data/processed_data_json/README.md) identify the source rows and chemical groups in each partition.

The evaluator reads the assistant label as the reference answer and excludes it from model requests. See [the evaluation guide](../../docs/holdout_evaluation.md).

### Claude evaluation

Install the optional SDK with `python -m pip install anthropic` and set `ANTHROPIC_API_KEY` in your environment. In a copy of `configs/holdout_evaluation.json` kept in `configs/`, replace `models` with the following entry and set `max_concurrency` to `3`:

```json
"models": [{"provider": "anthropic", "model_id": "claude-opus-5-5", "output_name": "holdout_opus55", "request_parameters": {"max_tokens": 2048, "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}}]
```

Run `python -m mofinder.evaluation.holdout validate --config configs/holdout_claude.json` first, then `python -m mofinder.evaluation.holdout run --config configs/holdout_claude.json --model holdout_opus55`. Add `--test-mode` to the run command to evaluate at most ten pending records.

The [Claude Messages API](https://platform.claude.com/docs/en/api/messages) receives the original system and user text; reference labels stay local. Only a standalone P/N text response is scored, and probability fields remain empty. Re-running resumes unattempted records; previously saved errors and invalid answers are retained. Model, provider, input and generation-setting changes require a new output name. Existing OpenAI configurations and the OpenAI `sanity-test` are unchanged.
