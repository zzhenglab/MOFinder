# Agitation normalization audit

Parser: `process-agitation-v5`. Model field: `agitation`; source field: `stirring`.

Enumerated all 890 unique extracted strings across 15,340 positive and 15,063 negative records. See `stirring_all_raw_values.csv` for exact raw text and matched rules. These filenames refer to the original extraction column.

Nine final classes consolidate non-sonication methods by reported stage, while retaining the three observed sonication stages separately. Final labels contain two to five words. Every original method and stage remains in `detailed_value`, alongside the raw text and consolidation rule. No frequency threshold determines these classes. A newly observed supported state outside this nine-class schema raises an error requiring class-map review; it is not silently recoded as missing. Preparation does not establish agitation during later heating; unqualified stirring does not establish continuous synthesis stirring. Explicit static synthesis takes precedence over preparation. When both initial stirring and sonication are named, stirring is the primary detailed label and raw text retains both. Rotation is retained in the detailed label when a separate prestir is reported. Final `Agitated` classes combine stirring, shaking, rotation, vortexing, homogenization, mixing, and agitation without a specified method; they preserve the reported stage. Bare speeds or intensity adjectives do not establish a method. Heating, centrifugation, and reagent addition alone do not establish synthesis agitation. Missing or unresolved descriptions use `Not reported`; unresolved nonempty text remains distinguished by its audit reason.

The same deterministic rules apply to positive and negative records before JSONL preparation. The original eight model inputs, labels, split assignments, and row order remain unchanged.

## Final class counts

| Class | Positive | Negative | Unique raw strings |
|---|---:|---:|---:|
| No stirring | 6,522 | 6,609 | 38 |
| Not reported | 3,886 | 3,987 | 7 |
| Agitated before static synthesis | 1,792 | 1,869 | 426 |
| Agitated during preparation | 479 | 568 | 140 |
| Agitated during synthesis | 15 | 18 | 9 |
| Agitated; stage not reported | 2,223 | 1,740 | 137 |
| Sonicated before static synthesis | 377 | 232 | 118 |
| Sonicated during preparation | 22 | 1 | 9 |
| Sonicated; stage not reported | 24 | 39 | 6 |

## Unresolved descriptions: 21 records / 5 strings

Associated tabular context is retained in `stirring_review_context.csv`. Targeted publication checks are documented separately; this is not a full source-publication verification.

| Raw string | Positive | Negative | Reason |
|---|---:|---:|---|
| centrifuged at 10,000 rpm | 12 | 0 | Centrifugation alone does not establish a stirring or static state; its stage is not inferred. |
| dropwise addition under Ar | 4 | 0 | Reagent addition alone does not specify agitation. |
| reflux | 3 | 0 | Heating or irradiation alone does not specify agitation. |
| microwave irradiation | 1 | 0 | Heating or irradiation alone does not specify agitation. |
| with or without stirring | 1 | 0 | The extraction lists alternative agitation states, not a unique record-specific state. |
