# Abstract triage reference

`ground_truth.xlsx` contains the human reference annotations, preserved byte for byte from the source workbook. It contains one sheet, `Ground truth`, with 478 unique DOIs and 13 columns. Source identity and SHA256 are recorded in [`data/manifest.json`](../../data/manifest.json).

| Reference property | Count |
| --- | ---: |
| Publications | 478 |
| Consensus Y | 293 |
| Consensus N | 185 |
| Complete four-binary-rating rows | 474 |
| Binary ratings | 1,908 |
| Ambiguous `Y/N` ratings | 4 |

The consensus column is authoritative. It incorporates the recorded rubric decisions and overrides; it is not recomputed from the annotator majority. Resolution methods and source comments are preserved without editing.

All 478 DOIs have one nonempty abstract in the associated metadata CSV. Labels and comments are excluded from screening requests and retained for analysis.

The complete screening predictions and run manifests are pending. Files under `data/Section S2/` in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a) describe earlier experiments and are not automatically paired with this reference.
