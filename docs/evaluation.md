# Reaction and human benchmark evaluation

The evaluation modules score model predictions on the reaction holdout and 22-question panel and analyze anonymous human responses. Live model calls, saved-result analysis, and human calculations have separate commands.

Install the dependencies from the repository root:

```bash
python -m pip install -e ".[evaluation]"
```

## Workflows

| Workflow | Input | Entry point | Guide |
| --- | --- | --- | --- |
| Holdout model evaluation | Final holdout JSONL, 2,595 reactions | `mofinder.evaluation.holdout` | [Holdout](holdout_evaluation.md) |
| Question-panel model evaluation | 22 configured reaction conditions | `mofinder.evaluation.quest` | [Question panel](quest_evaluation.md) |
| Human benchmark analysis | Anonymous answers and human question definitions | `mofinder.evaluation.human_quest` | [Human benchmark](human_benchmark.md) |

The training set is `data/final_json/train.jsonl`, and the validation set is `data/final_json/holdout.jsonl`. Both preserve the original experiment records byte for byte. Their identities are recorded in `data/final_json/manifest.json`, and their record assignments are in `data/final_json/split_assignments.csv`.

## Offline checks

```bash
python -m mofinder.evaluation.holdout validate --config configs/holdout_evaluation.json
python -m mofinder.evaluation.quest validate --config configs/quest_evaluation.json
python -m mofinder.evaluation.human_quest analyze
```

These commands do not contact a model. Human reports are saved under `results/evaluation/human_quest/`. Responses are aligned by reaction ID, not randomized presentation position. The exports contain anonymous participant identifiers and omit emails.

## Live model evaluation

Set `OPENAI_API_KEY` in your environment, verify the configured model identifiers, and run:

```bash
python -m mofinder.evaluation.holdout run --config configs/holdout_evaluation.json
python -m mofinder.evaluation.quest run --config configs/quest_evaluation.json --group latest_fine_tuned
```

The configurations record model IDs and run settings. Fine-tuned model access depends on the account. The holdout evaluator supports a ten-pending-record check with `--test-mode`. The question evaluator retains named model groups and repeated rounds. Details of source API branches and their settings are in the individual guides.

The [source code map](source_to_code.md) links each command to its Python implementation. Human benchmark analysis runs locally without an API key.

Model requests exclude reference answers. Reference labels and benchmark metadata remain local for scoring. New responses must contain only `P` or `N` after case and whitespace normalization; ordinary prose is no longer parsed for embedded label characters. Metric definitions are unchanged, and reports expose attempted, scored, failed, and invalid counts so the denominator is explicit. The parsing protocol is recorded in each new run's manifest. Existing CSV analysis uses its recorded labels without reparsing historical text; earlier holdout runs need a fresh output name for new requests.

## Saved model predictions

Existing prediction CSVs can be analyzed without repeating model calls:

```bash
python -m mofinder.evaluation.holdout analyze --csv results/evaluation/holdout/holdout_mofinder.csv
python -m mofinder.evaluation.quest analyze path/to/saved_question_predictions.csv
```

Use the filenames produced by the configured run. The stage guides describe output columns, run manifests, resume behavior, and per-round metrics.

## Subsequent evaluation stages

Separate positive and negative extraction-evaluation workflows are planned. They require their own reference records and scoring definitions. Model-performance results require corresponding saved predictions.
