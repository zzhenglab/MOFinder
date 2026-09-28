# Data curation demonstration

Curate 174 positive extraction records from 38 publications using the main MOFinder curation functions. The demonstration includes raw records, the supplied processed records for the same publications, and expected output from the current code.

## Run

From the repository root, with Python 3.10 or later:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_curation/mof_data_curation_demo.py --check
```

The script runs on a standard CPU and requires no API key or article PDFs. It normalizes reagent names, formulas, amounts, temperatures, and durations to produce the processed positive table. A typical run takes less than one minute.

For an interactive walkthrough with saved outputs, install `python -m pip install -e ".[curation,datasets,notebook]"` and open [curate and verify positive synthesis records](mof_data_curation_demo.ipynb). The implementation is in [the demonstration script](mof_data_curation_demo.py) and [the main curation functions](../../src/mofinder/curation/pipeline.py); the [curation guide](../../docs/curation.md) describes their use.

## Files

| Location | Contents |
| --- | --- |
| [input/mof_extraction.csv](input/mof_extraction.csv) | Raw extraction records with document-availability flags |
| [input/linker_molecular_weights.csv](input/linker_molecular_weights.csv) | Headerless linker-name/MW lookup used for amount conversion |
| [../../data/organic_linker_info/linker_prime_corrections.json](../../data/organic_linker_info/linker_prime_corrections.json) | Exact DOI/name prime restorations shared with the main curation workflow |
| [input/source_manifest.json](input/source_manifest.json) | Source hashes, selected DOIs, and original zero-based row positions |
| [reference/processed_positive_supplied.csv](reference/processed_positive_supplied.csv) | Corresponding records from the supplied full-corpus processed positive table |
| [expected/mof_extraction_6.csv](expected/mof_extraction_6.csv) | Regenerated processed positive output, containing 146 records |
| [config.json](config.json) | Input paths and output directory |

Each run writes intermediate CSVs, data previews, and `demo_summary.json` to `outputs/`. A numbered `run_history/` folder saves the output snapshot, settings, hashes, and verification results.

## Verify and inspect a saved run

The notebook's **Verify against expected output** section and the command-line `--check` option compare CSV contents and row counts with `expected/`. Example outputs and verification results are available in [recorded runs](recorded_runs/README.md).

## Input provenance

The `has_main_document` and `has_supporting_document` flags provide document availability for filtering; the script does not read PDFs.

The bundled input records 72 hours for the first record's `48–72 h` duration, following the parser's upper-range rule. The source manifest retains the original row positions and hashes.

Frequency and outlier filters are computed on the demonstration records, so use `expected/` to verify this run. The supplied reference was processed with the full dataset.

## Duration parsing

The demonstration calls the same duration parser as data curation of positive and negative records. Existing numeric `time_h` values are retained. Missing or nonnumeric values can be filled from ranges and qualitative duration text; the original `time_text` is preserved. See [the curation guide](../../docs/curation.md) for the conversion rules.

## Continue to dataset preparation

```bash
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --positive-csv Demo/01_data_curation/outputs/mof_extraction_6.csv --check
```

For another input table, update `config.json` or pass `--config`. Paths in the configuration are relative to that file. Use `--output-dir` to write a separate run. The expected-output check applies to the bundled demonstration inputs.
