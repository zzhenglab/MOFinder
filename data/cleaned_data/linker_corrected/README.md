# Corrected linker spellings

`negative_stage6_v3.csv` restores documented prime glyphs in 1,551 linker-name or abbreviation cells across 1,458 records. All 15,063 rows and 89 columns are retained. Other fields, including existing descriptions, are unchanged. Positive linker fields do not require these corrections.

The [correction lookup](../../organic_linker_info/linker_prime_corrections.json) contains 167 spellings supported by intact records from the same publication. Each rule matches the complete DOI and field value. The distinct single, double, triple, and quadruple prime glyphs are retained. Unresolved spellings and non-prime symbols are unchanged.

Regenerate this table from the repository root:

```bash
python -m mofinder.curation.linker_primes data/cleaned_data/archived/negative_stage6_v3.csv data/cleaned_data/linker_corrected/negative_stage6_v3.csv --lookup data/organic_linker_info/linker_prime_corrections.json
```

Use `configs/dataset_preparation_corrected.json` to prepare new datasets from the corrected table:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_corrected.json
```

The command recalculates grouped partitions and writes to `results/datasets/corrected_conditions/`. Linker spellings contribute to grouping, so the existing split assignments cannot be transferred to corrected conditions. The archived inputs in [`../archived/`](../archived/), training/holdout JSONL files, and split assignments retain the exact data used for the reported runs. Use `configs/dataset_preparation_archived.json` for those records.

`manifest.json` records source, lookup, and output checksums. Both CSV reading and writing use `utf-8-sig`.
