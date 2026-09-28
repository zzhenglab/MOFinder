# Processed data

Start with the processed positive and negative synthesis records below to prepare the [final training and holdout JSONL](../processed_data_json/README.md). Literature metadata and publication years are kept alongside these inputs.

| File or folder | Contents | Rows |
| --- | --- | ---: |
| [processed_positive.csv](processed_positive.csv) | Processed positive synthesis records | 15,340 |
| [processed_negative.csv](processed_negative.csv) | Processed negative synthesis records, including reconstructed conditions | 15,063 |
| [publication_years.csv](publication_years.csv) | DOI-to-year input for dataset preparation | 13,773 |
| [literature_metadata.csv](literature_metadata.csv) | Six bibliographic fields used for abstract screening | 13,773 |
| [literature_retrieval/](literature_retrieval/README.md) | Article and supporting-information inventories | 7,437 each |
| [linker_corrected/](linker_corrected/README.md) | Optional negative table with documented linker prime glyphs restored | 15,063 |
| [with_process_details/](with_process_details/README.md) | Positive/negative tables with cleaned vessel type, capacity, and agitation | 15,340 / 15,063 |

## Dataset analysis

The [figure gallery](../../docs/dataset_analysis/README.md) and [executed notebook](../../Demo/04_dataset_analysis/dataset_analysis.ipynb) cover metals, linkers, solvents, modulators, topology, BET, TGA, and air/water stability in the positive dataset. Panels show synthesis records above unique DOI counts; property panels use one median eligible value per DOI. Pairwise condition plots use both the positive and negative datasets.

The notebook also draws the final training/test t-SNE.

## Prepare the final JSONL

From the repository root:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

The default configuration reads `processed_positive.csv`, `processed_negative.csv`, and `publication_years.csv` from this folder. It writes training and holdout JSONL, split assignments, preparation summaries, and publication-year subsets to `results/datasets/conditions/`.

For new curation outputs, use [dataset_preparation_from_curation.json](../../configs/dataset_preparation_from_curation.json), which writes to `results/datasets/curated_conditions/`. Original extraction JSON stores are needed for negative reconstruction before curation. The optional [linker-corrected input](linker_corrected/README.md) has its own preparation configuration and output directory because changed linker spellings affect chemical grouping.

## Schema and provenance

The counts above are before dataset-preparation filtering. The positive table has 83 columns and the negative table has 76. Negative records include reconstruction rationales, parent indices, and modified-class fields. Neither table includes local file paths.

The negative table excludes product-property columns: `crystal_morphology`, `yield_percent`, `crystal_size`, `topology_code`, `metal_cluster_connectivity`, `metal_cluster_connectivity_classified`, `unit_cell_short`, `pore_diameter_A`, `BET_surface_area_m2g`, `air_stable`, `water_stable`, `tga_decomposition_temp_c`, and `applications`.

Dataset preparation selects eight synthesis-condition fields. The optional linker-corrected copy retains its earlier 89-column schema; applying its correction lookup to the current negative table retains the current 76-column schema.

Both synthesis CSVs use UTF-8 with a byte-order mark (`utf-8-sig`) for spreadsheet compatibility. Python readers can use `encoding="utf-8-sig"`; the byte-order mark is not part of the first column name.

[manifest.json](manifest.json) records source and export checksums for the synthesis tables. [Literature metadata details](literature_metadata.md) explain the bibliography fields, duplicate DOI records, and publication years; their provenance is recorded in [data/manifest.json](../manifest.json).
