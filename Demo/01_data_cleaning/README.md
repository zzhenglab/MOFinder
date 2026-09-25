# Data cleaning demo

Clean 174 positive extraction records from 38 publications using the main MOFinder curation functions. The demo includes raw records, the supplied cleaned records for the same publications, and expected output from the current code.

## Run

From the repository root, with Python 3.10 or later:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_cleaning/mof_cleaning_demo.py --check
```

The script runs on a standard CPU and requires no API key or article PDFs. It normalizes reagent names, formulas, amounts, temperatures, and durations to produce the processed positive table. A typical run takes less than one minute.

For an interactive walkthrough with saved outputs, install `python -m pip install -e ".[curation,datasets,notebook]"` and open [clean and verify positive synthesis records](mof_cleaning_demo.ipynb). The implementation is in [the demo script](mof_cleaning_demo.py) and [the main curation functions](../../src/mofinder/curation/pipeline.py); the [curation guide](../../docs/curation.md) describes their use.

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

Each run writes intermediate CSVs, compact raw and cleaned previews, and `demo_summary.json` to `outputs/`. It also preserves a separate output snapshot and run record under `run_history/<timestamp>/`. The record identifies the inputs, settings, outputs, and verification results. Local run history is excluded from Git by default.

## Verify and inspect a saved run

The notebook's **Verify against expected output** section is a separate, rerunnable check. Its table shows expected rows, actual rows, **PASS** or **FAIL**, and comparison details. The check compares the contents of the processed positive CSV with `expected/`, as well as its row count. The command-line `--check` option performs the same verification.

Open the checked-in [saved run record](saved_run/run_record.json) and [saved output files](saved_run/) to inspect the recorded example on GitHub. The notebook also retains its executed tables. A new run updates `outputs/` and adds a timestamped history folder, preserving earlier runs.

## Input provenance

The `has_main_document` and `has_supporting_document` flags preserve the original document-availability filter. The script supplies temporary presence values to the curation functions; it does not read the documents. Local PDF paths and raw model responses are omitted from the distributed tables.

The bundled input uses uppercase `TRUE` document flags and explicitly records 72 hours for the first record's `48–72 h` duration. This produces the same cleaned result as the duration parser's upper-range rule. The source manifest distinguishes this demo input from its original source and retains the source row positions and hashes.

Frequency and outlier filters are computed on the demo records. The supplied full-corpus reference and the regenerated demo output thus have separate roles: use `expected/` to verify this run. The current formula and linker-normalization rules are described in [the curation guide](../../docs/curation.md).

## Duration parsing

The demo calls the same duration parser as both positive and negative curation. Existing numeric `time_h` values are retained. Missing or nonnumeric values can be filled from ranges and qualitative duration text; the original `time_text` is preserved. See [the curation guide](../../docs/curation.md) for the conversion rules.

## Continue to JSON preparation

```bash
python Demo/02_json_preparation/mof_json_preparation_demo.py --positive-csv Demo/01_data_cleaning/outputs/mof_extraction_6.csv --check
```

For another input table, update `config.json` or pass `--config`. Paths in the configuration are relative to that file. Use `--output-dir` to write a separate run. The expected-output check applies to the bundled demo inputs.
