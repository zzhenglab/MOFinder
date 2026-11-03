# Abstract triage reference

`ground_truth.xlsx` contains one sheet, `Ground truth`, with human reference annotations for 478 unique DOIs across 13 columns. Its source and SHA256 hash are recorded in [`data/manifest.json`](../../data/manifest.json).

| Reference property | Count |
| --- | ---: |
| Publications | 478 |
| Consensus Y | 314 |
| Consensus N | 164 |
| Complete four-binary-rating rows | 478 |
| Binary ratings | 1,912 |
| Ambiguous `Y/N` ratings | 0 |

Use the consensus column as the answer key. It incorporates recorded rubric decisions and overrides, so it can differ from the annotator majority. The workbook includes resolution methods and source comments.

All 478 DOIs have one nonempty abstract in the associated metadata CSV. Labels and comments are excluded from screening requests and retained for analysis.

See the [triage guide](../../docs/triage.md) for screening and analysis commands.
