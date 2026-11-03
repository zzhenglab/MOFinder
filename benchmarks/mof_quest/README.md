# MOF Quest benchmark

`22_questions.json` is the shared source for dataset preparation, model evaluation, and the MOF-Quest website. It contains 22 reactions: 11 positive and 11 negative.

| File | Contents |
| --- | --- |
| `22_questions.json` | Current conditions, labels, reaction IDs, source DOIs, selection strata, and website notes |
| `human_questions.csv` | CSV export of `22_questions.json` for the human-response analysis |
| `human_responses.csv` | 2,156 responses from 98 participants, with experience and original confidence categories |
| `human_manifest.json` | Source and export hashes and field definitions |

`participant_id` is a sequential anonymous identifier.

The current panel follows SI Table S41, with the complete Q9 co-linker name and full-precision M:L ratios. Q2 is 144 hours. Historical human responses and model outputs retain their original values; correcting the question definitions does not create new observations. Use the original workbook and saved run inputs when checking what was presented during a past evaluation.

Update the JSON first, then regenerate the CSV and website constants:

```bash
python tools/sync_quest_questions.py --quest-dir MOF-Quest
python tools/sync_quest_questions.py --quest-dir MOF-Quest --check
```

Pass the path to a separate MOF-Quest checkout when it is not installed as a submodule. Without `--quest-dir`, the command updates or checks the CSV export only. Reaction IDs stay fixed when names or conditions are corrected.

Responses are joined to questions using `reaction_id`; presentation order does not determine the answer key. The four response categories map to binary predictions as follows:

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

See [human benchmark analysis](../../docs/human_benchmark.md) and [model evaluation](../../docs/quest_evaluation.md) for the workflows.
