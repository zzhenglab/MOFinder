# Archived cleaned records

These tables archive the positive and negative stage-6 records used for dataset preparation. Four local-path columns are omitted: `main_pdf`, `si_pdf`, `raw_output`, and `parsed_json`. All other cell values and the row order are preserved. `manifest.json` records the source and export checksums.

Both CSVs use UTF-8 with a byte-order mark (`utf-8-sig`) so spreadsheet applications can recognize Unicode formula symbols. Python readers can use `encoding="utf-8-sig"`; the byte-order mark is not part of the first column name.

| File | Input identity | Rows |
| --- | --- | ---: |
| `positive_stage6.csv` | Positive records after stage 6 | 15,340 |
| `negative_stage6_v3.csv` | Versioned negative records after stage 6 | 15,063 |

These are input counts before dataset-preparation filtering. Negative records include reconstructed conditions and retain their rationale, parent indices, and modified-class fields.

Use `configs/dataset_preparation_archived.json` to prepare datasets from these archived records. The default configuration reads newly generated curation outputs. Original extraction JSON stores remain necessary for negative reconstruction before curation.

The archived training and validation JSONL files are distributed separately without changes. The corrected H3BTB mapping applies to new curation runs; this export retains the chemical values in the source records.
