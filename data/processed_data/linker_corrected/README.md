# Corrected linker spellings

`processed_negative.csv` restores documented prime glyphs in 1,551 linker-name or abbreviation cells across 1,458 records. All 15,063 rows and 89 columns are retained. Other fields, including existing descriptions, are unchanged. Positive linker fields do not require these corrections.

The [correction lookup](../../organic_linker_info/linker_prime_corrections.json) contains 167 spellings supported by intact records from the same publication. Each rule matches the complete DOI and field value. The distinct single, double, triple, and quadruple prime glyphs are retained. Unresolved spellings and non-prime symbols are unchanged.

Apply the spelling corrections to the current processed negative table from the repository root:

```bash
python -m mofinder.curation.linker_primes data/processed_data/processed_negative.csv data/processed_data/linker_corrected/processed_negative.csv --lookup data/organic_linker_info/linker_prime_corrections.json
```

Use `configs/dataset_preparation_corrected.json` to prepare new datasets from the corrected table:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_corrected.json
```

Dataset preparation recalculates grouped partitions and writes to `results/datasets/corrected_conditions/`. Linker spellings affect grouping, so corrected conditions require new split assignments. Use `configs/dataset_preparation.json` for the standard dataset.

`manifest.json` records source, lookup, and output checksums. Both CSV reading and writing use `utf-8-sig`.
