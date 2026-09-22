# MOF Quest benchmark

The benchmark contains two recorded question panels and deidentified human responses.

| File | Contents |
| --- | --- |
| `questions.json` | The 22 conditions and labels used in the model-evaluation notebook |
| `human_questions.csv` | The 22 conditions, labels, reaction IDs, source DOIs and selection strata recorded in the human-response workbook |
| `human_responses.csv` | 2,156 responses from 98 participants, with experience and original confidence categories |
| `human_manifest.json` | Source and export hashes and field definitions |

`participant_id` is a sequential anonymous identifier. Contact information is excluded. The original workbook remains a local input and is not distributed here.

Responses are joined to questions using `reaction_id`. Question numbering follows each source panel; presentation order does not determine the answer key. The four response categories map to binary predictions as follows:

| Response | Prediction |
| --- | --- |
| Very Confident Success | P |
| Likely Success | P |
| Likely Fail | N |
| Very Confident Fail | N |

Run the analysis from the repository root:

```bash
python -m mofinder.evaluation.human_quest analyse
```

See the [evaluation overview](../../docs/evaluation.md), [human benchmark analysis](../../docs/human_benchmark.md), and [model evaluation](../../docs/quest_evaluation.md) for the workflows.
