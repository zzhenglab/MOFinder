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

The walkthrough is `notebooks/09_human_benchmark.ipynb`. Analysis is local and does not require an API key. It writes `summary.json` plus participant, question, experience and confidence CSV tables.

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
