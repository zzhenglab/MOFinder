# Processed data

Start with the processed positive and negative synthesis records below to prepare the [final training and holdout JSONL](../final_json/README.md). Literature metadata and publication years are kept alongside these inputs.

| File or folder | Contents | Rows |
| --- | --- | ---: |
| [processed_positive.csv](processed_positive.csv) | Processed positive synthesis records | 15,340 |
| [processed_negative.csv](processed_negative.csv) | Processed negative synthesis records, including reconstructed conditions | 15,063 |
| [publication_years.csv](publication_years.csv) | DOI-to-year input for dataset preparation | 13,773 |
| [literature_metadata.csv](literature_metadata.csv) | Six bibliographic fields used for abstract screening | 13,773 |
| [literature_retrieval/](literature_retrieval/README.md) | Article and supporting-information inventories | 7,437 each |
| [linker_corrected/](linker_corrected/README.md) | Optional negative table with documented linker prime glyphs restored | 15,063 |

## Prepare the final JSONL

From the repository root:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

The default configuration reads `processed_positive.csv`, `processed_negative.csv`, and `publication_years.csv` from this folder. It writes a new run to `results/datasets/conditions/`, including training and holdout JSONL, split assignments, preparation summaries, and publication-year subsets. The distributed [final_json/](../final_json/README.md) folder contains the prepared records and their split information together.

For new curation outputs, use [dataset_preparation_from_curation.json](../../configs/dataset_preparation_from_curation.json), which writes to `results/datasets/curated_conditions/`. Original extraction JSON stores are needed for negative reconstruction before curation. The optional [linker-corrected input](linker_corrected/README.md) has its own preparation configuration and output directory because changed linker spellings affect chemical grouping.

## Record preservation and provenance

The positive and negative counts above are before dataset-preparation filtering. Negative records retain their rationale, parent indices, and modified-class fields. Four local-path columns are omitted from the supplied synthesis tables: `main_pdf`, `si_pdf`, `raw_output`, and `parsed_json`. All other cell values and the source row order are preserved. These tables retain the chemical values used for the reported datasets; the corrected H3BTB mapping applies to new curation runs.

Both synthesis CSVs use UTF-8 with a byte-order mark (`utf-8-sig`) for spreadsheet compatibility. Python readers can use `encoding="utf-8-sig"`; the byte-order mark is not part of the first column name.

[manifest.json](manifest.json) records source and export checksums for the synthesis tables. [Literature metadata details](literature_metadata.md) explain the bibliography fields, duplicate DOI records, and publication years; their provenance is recorded in [data/manifest.json](../manifest.json).
