# Literature metadata

`literature_metadata.csv` selects the six fields used by abstract screening from the literature bibliography workbook. It preserves all 13,773 rows, their order, and the selected cell text. Additional author/contact columns are not part of this screening input. The manifest records a descriptive source identifier and the workbook's SHA-256 hash.

| Field | Role |
| --- | --- |
| DOI | Match bibliographic records to the reference |
| Article Title | Prompt input |
| Source Title | Prompt input |
| Author Keywords | Prompt input |
| Keywords Plus | Prompt input |
| Abstract | Prompt input; required to schedule screening |

The file contains 13,770 normalized unique DOIs. Three groups have conflicting bibliography text:

| DOI | Conflicting fields |
| --- | --- |
| `10.1021/acs.chemmater.2c00846` | Abstract; Keywords Plus |
| `10.1021/acs.inorgchem.2c04233` | Abstract; Keywords Plus |
| `10.1039/c2sc20344h` | Abstract |

All are outside the 478-paper reference, so the default benchmark scope is unaffected. Whole-corpus screening stops with a duplicate-conflict error until these records are reconciled.

To reproduce the export from the original workbook, choose a new destination:

```bash
python tools/export_triage_metadata.py Full.xlsx literature_metadata.csv
```

[`data/manifest.json`](../manifest.json) records the source filename, source hash, output hash, row counts, and transformation.

## Publication years

`publication_years.csv` exports `DOI` and `Publication Year` from the same bibliography workbook, preserving all 13,773 source rows. It is a separate input for dataset preparation; the six-field triage export remains unchanged. There are no missing years in this export. Checksums and source identity are in `data/manifest.json`. Dataset preparation resolves duplicate DOI years using its documented modal-year rule.
