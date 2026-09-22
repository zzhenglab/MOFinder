# Reaction and human benchmark evaluation

The evaluation modules score model predictions on the reaction holdout and 22-question panel and analyze anonymous human responses. Live model calls, saved-result analysis, and human calculations have separate commands.

Install the dependencies from the repository root:

```bash
python -m pip install -e ".[evaluation]"
```

## Workflows

| Workflow | Input | Entry point | Guide |
| --- | --- | --- | --- |
| Holdout model evaluation | Archived validation JSONL, 2,595 reactions | `mofinder.evaluation.holdout` | [Holdout](holdout_evaluation.md) |
| Question-panel model evaluation | 22 configured reaction conditions | `mofinder.evaluation.quest` | [Question panel](quest_evaluation.md) |
| Human benchmark analysis | Anonymous answers and human question definitions | `mofinder.evaluation.human_quest` | [Human benchmark](human_benchmark.md) |

The training set is `data/training/train.jsonl`, and the validation set is `data/training/holdout.jsonl`. Both preserve the archived experiment records byte for byte. Their identities are recorded in `data/training/manifest.json`, and their record assignments are in `data/splits/split_assignments.csv`.

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

The optional notebooks `07_holdout_evaluation.ipynb` and `08_quest_evaluation.ipynb` request a key through a hidden prompt when a live run is enabled and no environment key is set. Live execution is disabled initially. `09_human_benchmark.ipynb` performs local analysis without a key.

Model requests exclude reference answers. Reference labels and benchmark metadata remain local for scoring. The original prediction parser and metric definitions are retained; reports also expose attempted, scored, failed, and invalid counts so the metric denominator is explicit.

## Saved model predictions

Existing prediction CSVs can be analyzed without repeating model calls:

```bash
python -m mofinder.evaluation.holdout analyze --csv results/evaluation/holdout/holdout_mofinder.csv
python -m mofinder.evaluation.quest analyze path/to/saved_question_predictions.csv
```

Use the filenames produced by the configured run. The stage guides describe output columns, run manifests, resume behavior, and per-round metrics.

## Subsequent evaluation stages

Separate positive and negative extraction-evaluation workflows are planned. They require their own reference records and scoring definitions. Model-performance results require corresponding saved predictions.
