# Reaction holdout evaluation

`mofinder.evaluation.holdout` evaluates the reaction-classification holdout using the recorded request settings and statistical definitions. It reads the validation JSONL directly without retraining a model or generating a new split.

```bash
python -m pip install -e ".[evaluation]"
python -m mofinder.evaluation.holdout validate --config configs/holdout_evaluation.json
```

`validate` checks messages, reference labels, and file hashes without creating files or making API calls. The input is `data/training/holdout.jsonl`. The archived training set at `data/training/train.jsonl` is recorded for provenance. It is not sent to an evaluation model.

## Models and execution

The configuration retains both fine-tuned model IDs from the source notebook. A fine-tuned model is usable only by an account with access to that model. Set `model_id` to the intended accessible model before starting a new run and give it a distinct `output_name`.

The notebook [07_holdout_evaluation.ipynb](../notebooks/07_holdout_evaluation.ipynb) calls the Python implementation. Set `RUN_EVALUATION = True` and provide your API key at the hidden prompt. For command-line execution, set `OPENAI_API_KEY` in the current environment before running:

```bash
python -m mofinder.evaluation.holdout run --config configs/holdout_evaluation.json --model holdout_mofinder
```

Omit `--model` to run both configurations sequentially. Add `--test-mode` to evaluate the first ten pending records per model. The optional `sanity-test` command sends only the first record using the original separate `gpt-4.1` test settings; it is disabled initially in the notebook and does not write predictions.

Concurrent evaluation keeps `temperature=0`, `top_p=1`, `max_tokens=2`, `logprobs=True`, `top_logprobs=5`, and `seed=7`. The configuration uses concurrency 100 and six request attempts with the original exponential delays. Each request contains the record's system and user messages only. The assistant message remains local as the P/N reference label. No API parameters are silently removed or substituted when a model rejects them.

## Prediction and probability calculations

The original parser takes the first P or N character found in the uppercase response. It is a permissive parser, so text containing one of these letters can produce a label even when the response is not exactly P or N. This behavior is retained for comparison with previous evaluations.

For token probabilities, the evaluator first finds a token whose normalized text equals the parsed label, then reads P and N log probabilities at that token position. When both are available, the reported probability is `exp(logprob_P) / (exp(logprob_P) + exp(logprob_N))`, calculated after subtracting the larger log probability for numerical stability. This is a probability normalized over the two label tokens. Missing P/N token alternatives produce missing probabilities. The original fallback to the first P/N token is also retained if the parsed label has no matching token.

Accuracy, precision, recall, and F1 use only rows with valid P/N predictions and valid P/N references. P is the positive class, and undefined precision/recall/F1 values are zero. Coverage, error counts, and the number of unscored records are reported separately. Errors are saved as `no_choice_or_bad_label` following the source notebook. The progress display and invocation metrics summarize new rows; the saved metrics JSON summarizes the complete prediction CSV.

## Saved results and resume

Each model writes three files under `results/evaluation/holdout/`:

| File | Contents |
| --- | --- |
| `<output_name>.csv` | Reference and predicted labels, raw model text, aligned token probabilities, latency, and request status |
| `<output_name>.manifest.json` | Model, input hashes, request settings, and total reference count |
| `<output_name>.metrics.json` | Complete saved-row metrics and coverage |

A single writer saves each completed request, so completed results remain available after interruption. Repeating a run skips all recorded indices, including recorded failures, as in the source notebook. Changed input files, model IDs, or request settings require a new output name. Existing CSV rows are also checked against the model, reference label, and exact system/user input before reuse. A CSV without its run manifest remains available for offline analysis but cannot be resumed because its original request settings cannot be verified.

For offline analysis:

```bash
python -m mofinder.evaluation.holdout analyze \
  --csv results/evaluation/holdout/holdout_mofinder.csv \
  --output results/evaluation/holdout/holdout_mofinder.reanalysis.json
```

Offline tests cover controlled responses, retry failures, token log probabilities, valid-label metrics, and interrupted-run resume. Live verification of the packaged Python evaluator remains pending.
