# Chemical lookup tables

`linker_molecular_weights.csv` preserves the source lookup table byte for byte. It is the default linker lookup in `configs/curation.json`.

The UTF-8 CSV has no header. Its columns are linker name and molecular weight in g/mol. Names containing commas are quoted; matching ignores letter case and surrounding whitespace.

| Content | Count |
| --- | ---: |
| Rows | 591 |
| Rows with a numeric molecular weight | 217 |
| Rows with a blank molecular weight | 374 |
| Unique names with a molecular weight | 210 |
| Unique names without a molecular weight | 372 |

Blank weights are unresolved. They are not estimated or replaced. Linker amounts reported in molar units can still be processed. Mass amounts without a usable weight remain unconverted and are removed by the existing linker-unit filter.

`h3btb` and `H3BTB` normalize to `1,3,5-Tris(4-carboxyphenyl)benzene`; its case-insensitive lookup entry has a molecular weight of 438.4 g/mol. Alias normalization is part of the curation code, so the source lookup remains unchanged.

`manifest.json` records provenance and integrity information. See [curation](../../docs/curation.md) for the workflow and conversion rules.

`linker_prime_corrections.json` restores 167 documented linker spellings from intact records associated with the same DOI. It applies only to exact DOI/name pairs in the six linker-name and abbreviation fields. The default curation configuration applies this lookup before linker filtering and amount conversion. [Corrected stage-6 records](../processed/corrected/README.md) and a separate dataset-preparation configuration are also provided; archived model inputs retain their original values.
