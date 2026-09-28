# Agitation normalization audit

Parser: `process-agitation-v6`. Model field: `agitation`; source field: `stirring`.

Enumerated all 890 unique extracted strings across 15,340 positive and 15,063 negative records. See `stirring_all_raw_values.csv` for exact raw text and matched rules. These filenames refer to the original extraction column.

Nine final classes distinguish stirring, sonication, and shaking or mixing methods. Labels contain two to five words. `Stirred before main synthesis` denotes initial stirring before the main heating or aging step, with later conditions unspecified. `Stirred before static synthesis` requires explicit static conditions after preparation. The equivalent distinction applies to sonication. `Stirring reported` does not assert stirring throughout the reaction: it includes unqualified stirring and explicitly reported reaction-stage stirring, distinguished in `detailed_value`. `Sonication reported` uses the same reporting convention. Shaking, vortexing, rotation, homogenization, and mixing share one named method group; their exact method and stage remain in the detailed audit. They are not relabeled as stirring. No frequency threshold defines these classes. When initial stirring and sonication are both stated, stirring remains the primary detailed label and the raw text retains both; rotation is retained in the detailed label when accompanied by a separate prestir. Bare speeds or intensity adjectives do not establish a method. Heating, centrifugation, and reagent addition alone do not establish synthesis agitation. Missing or unresolved descriptions use `Not reported`; unresolved nonempty text remains distinguished by its audit reason.

The same deterministic rules apply to positive and negative records before JSONL preparation. The original eight model inputs, labels, split assignments, and row order remain unchanged.

## Final class counts

| Class | Positive | Negative | Unique raw strings |
|---|---:|---:|---:|
| No stirring | 6,522 | 6,609 | 38 |
| Not reported | 3,886 | 3,987 | 7 |
| Stirred before static synthesis | 1,759 | 1,815 | 412 |
| Stirred before main synthesis | 495 | 567 | 141 |
| Stirring reported | 2,190 | 1,756 | 126 |
| Sonicated before static synthesis | 377 | 232 | 118 |
| Sonicated before main synthesis | 22 | 1 | 9 |
| Sonication reported | 24 | 39 | 6 |
| Shaking, vortexing, rotation and mixing | 65 | 57 | 34 |

## Unresolved descriptions: 21 records / 5 strings

Associated tabular context is retained in `stirring_review_context.csv`. Targeted publication checks are documented separately; this is not a full source-publication verification.

| Raw string | Positive | Negative | Reason |
|---|---:|---:|---|
| centrifuged at 10,000 rpm | 12 | 0 | Centrifugation alone does not establish a stirring or static state; its stage is not inferred. |
| dropwise addition under Ar | 4 | 0 | Reagent addition alone does not specify agitation. |
| reflux | 3 | 0 | Heating or irradiation alone does not specify agitation. |
| microwave irradiation | 1 | 0 | Heating or irradiation alone does not specify agitation. |
| with or without stirring | 1 | 0 | The extraction lists alternative agitation states, not a unique record-specific state. |
