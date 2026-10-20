# Positive extraction reference

`ground_truth.xlsx` contains 1,087 synthesis records from 200 publications.
Use `Ground_truth_A1toA4` as the answer key. The other four sheets, `A1`–`A4`,
contain the records available for each annotation group.

The reference evaluates 26 fields: reagent names and amounts, synthesis
temperature and time, decomposition temperature, BET surface area, crystal
code, and topology. Paper and record IDs link the sheets; MOF names support
record matching.

Accepted alternatives use ` | `; `not reported` accepts an empty value.
Keep `reference_rules.json` beside the workbook: it preserves coupled reagent
names and amounts and explicit record-specific equivalences.

The [prediction CSV](../../data/processed_data/positive_extraction_200.csv)
contains 913 model extraction records for the same publications. File hashes
are recorded in [data/manifest.json](../../data/manifest.json).
See the [evaluation guide](../../docs/positive_extraction.md#benchmark-evaluation)
for commands and metric definitions.
