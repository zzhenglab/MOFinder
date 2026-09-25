# Human benchmark analysis

The human benchmark contains 98 participants and 22 questions, with 11 positive and 11 negative reference labels. Each participant answered every question. Experience groups contain 30 participants with less than one year, 29 with one to three years, and 39 with more than three years.

## Run

From the repository root:

```bash
python -m pip install -e ".[evaluation]"
python -m mofinder.evaluation.human_quest analyse \
  --questions benchmarks/mof_quest/human_questions.csv \
  --responses benchmarks/mof_quest/human_responses.csv \
  --output-dir results/evaluation/human_quest
```

The implementation is in [evaluation/human_quest.py](../src/mofinder/evaluation/human_quest.py). Analysis is local and does not require an API key. It writes `summary.json` plus participant, question, experience and confidence CSV tables.

## Inputs and another cohort

| Input | Required columns |
| --- | --- |
| `benchmarks/mof_quest/human_questions.csv` | `question`, `reaction_id`, `label`, `difficulty`, `doi`, `conditions_json` |
| `benchmarks/mof_quest/human_responses.csv` | `participant_id`, `experience`, `reaction_id`, `response`, `stored_score` |

For another cohort, pass replacement anonymous tables with `--questions` and `--responses`, retaining reaction IDs and response-category spellings. Choose a new `--output-dir` to preserve the previous analysis.

## Plot per-question accuracy

After running the analysis, save this Python code to a local script and run it from the repository root. It reads the exported question table and saves a figure beside it. Install `.[plotting]` if needed. Bars use teal for reference-positive questions and grey for reference-negative questions; error bars are the reported 95% Wilson intervals.

```python
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

output_dir = Path("results/evaluation/human_quest")
items = pd.read_csv(output_dir / "questions.csv")
fig, ax = plt.subplots(figsize=(10, 4))
colors = ["#285953" if label == "P" else "#91999B" for label in items["label"]]
ax.bar(items["question"], items["accuracy"], color=colors)
ax.errorbar(
    items["question"], items["accuracy"],
    yerr=[items["accuracy"] - items["wilson_lower"],
          items["wilson_upper"] - items["accuracy"]],
    fmt="none", ecolor="#333333", capsize=2, linewidth=1,
)
ax.set(xlabel="Question", ylabel="Accuracy", ylim=(0, 1))
ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(output_dir / "question_accuracy.png", dpi=200)
plt.close(fig)
```

## Scoring and uncertainty

Each response is matched by the recorded reaction ID. Both success categories predict P; both failure categories predict N. Confidence is categorical and is not converted to a model probability. Unknown reaction IDs, duplicate participant/question pairs and inconsistent participant metadata raise an error.

Accuracy is the number of correct predictions divided by the number of recorded answers. Missing responses, when present in a later dataset, remain missing. The current dataset has no missing answers. A question's majority prediction is the more frequent binary choice. Ties are excluded from majority-vote accuracy and counted separately.

Per-question uncertainty uses a 95% Wilson interval. Experience-group intervals use a 95% t interval across participant accuracies on the fixed 22-question panel. The confidence table includes response counts, accuracy and the fraction of answers in each category. Its Wilson intervals describe pooled answer counts; they do not account for repeated answers from the same participant. Participant-level intervals should be used for uncertainty in overall human accuracy.

Binary interrater agreement includes the mean within-question pair agreement, Fleiss' kappa, Gwet's AC1 and nominal Krippendorff's alpha. Fleiss' kappa is calculated only when the included questions have equal numbers of ratings. These measures compare participant predictions and do not use the reference labels. The `difficulty` column retains the source selection strata, `easy`, `medium` and `hard`.

## Workbook input

The export reads the reaction definitions and scoring labels from `Sheet1` columns O:T. It reads the raw response JSON from column C of `Sheet1.1 Responses`; the JSON keys provide the reaction IDs and the `User_Experience` entry provides the experience category. Original stored scores come from column B. The exported participant IDs contain no contact information.

To recreate the deidentified export from a local copy of the same workbook:

```bash
python -m mofinder.evaluation.human_quest export-workbook \
  "path/to/MOF Synthesis Quest.xlsx" \
  --output-dir results/evaluation/human_export
```

The workbook reader requires `openpyxl`. It exports only the specified scientific fields; it does not copy the workbook or contact columns.
