# Analysis and publication mapping

Descriptive analysis identifiers remain stable while manuscript and supplementary figure numbers are finalized.

| Analysis | Reference/input | Implementation | Result archive |
| --- | --- | --- | --- |
| Abstract-screening classification | Saved screening run; `benchmarks/abstract_triage/ground_truth.xlsx` | `python -m mofinder.literature.triage analyze`; statistics in `src/mofinder/evaluation/triage.py` | Complete model-run files pending |
| Abstract-screening figures | The same saved run and reference | `src/mofinder/plotting/triage.py`, called by `analyze` | Figure generation awaits the complete model-run files |
| Human annotation agreement | `benchmarks/abstract_triage/ground_truth.xlsx` | `python -m mofinder.literature.triage human-agreement` | Locally reproducible from the human reference |
| Positive extraction | Extraction reference records pending | `src/mofinder/extraction/positive.py`; reference-based scoring pending | Pending |
| Negative reconstruction | Reconstruction reference records pending | `src/mofinder/extraction/negative.py` and `enumerate_failures.py`; reference-based scoring pending | Pending |
| Reaction holdout classification | `data/training/holdout.jsonl` | `python -m mofinder.evaluation.holdout` | Saved model predictions pending |
| MOF Quest model evaluation | `benchmarks/mof_quest/questions.json` | `python -m mofinder.evaluation.quest` | Saved model predictions pending |
| MOF Quest human benchmark | `benchmarks/mof_quest/human_questions.csv` and `human_responses.csv` | `python -m mofinder.evaluation.human_quest` | Locally reproducible from the anonymous responses |

The optional triage notebook calls these Python implementations to display results. Each completed paper result will identify its final figure/table number, dataset and split version, effective configuration, prediction archive, and exact reproduction command.
