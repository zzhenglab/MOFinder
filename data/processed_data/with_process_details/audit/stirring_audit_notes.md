# Agitation normalization audit

Parser: `process-agitation-v4`. Model field: `agitation`; source field: `stirring`.

Enumerated all 890 unique extracted strings across 15,340 positive and 15,063 negative records. See `stirring_all_raw_values.csv` for exact raw text and matched rules. These filenames refer to the original extraction column.

Methods and reported stages are retained regardless of frequency. Final labels contain two to five words. No catch-all method class is used. Preparation does not establish agitation during later heating; unqualified stirring does not establish continuous synthesis stirring. Explicit static synthesis takes precedence over preparation. When both initial stirring and sonication are named, stirring is the primary label and raw text retains both. Rotation is retained when a separate prestir is reported. `Agitated` is used only when agitation itself is stated without a more specific method. Bare speeds or intensity adjectives do not establish a method. Heating, centrifugation, and reagent addition alone do not establish synthesis agitation. Missing or unresolved descriptions use `Not reported`; unresolved nonempty text remains distinguished by its audit reason.

The same deterministic rules apply to positive and negative records before JSONL preparation. The original eight model inputs, labels, split assignments, and row order remain unchanged.

## Final class counts

| Class | Positive | Negative | Unique raw strings |
|---|---:|---:|---:|
| Not reported | 3,886 | 3,987 | 7 |
| No stirring | 6,522 | 6,609 | 38 |
| Stirred before static synthesis | 1,758 | 1,815 | 411 |
| Stirred during preparation | 478 | 567 | 139 |
| Stirred during synthesis | 13 | 18 | 7 |
| Stirred; stage not reported | 2,194 | 1,738 | 120 |
| Sonicated before static synthesis | 377 | 232 | 118 |
| Sonicated during preparation | 22 | 1 | 9 |
| Sonicated; stage not reported | 24 | 39 | 6 |
| Shaken before static synthesis | 12 | 27 | 4 |
| Shaken; stage not reported | 10 | 2 | 4 |
| Rotated before static synthesis | 4 | 0 | 1 |
| Rotated during synthesis | 2 | 0 | 2 |
| Rotated; stage not reported | 16 | 0 | 11 |
| Vortexed; stage not reported | 1 | 0 | 1 |
| Homogenized before static synthesis | 6 | 10 | 2 |
| Homogenized during preparation | 1 | 1 | 1 |
| Mixed before static synthesis | 10 | 17 | 6 |
| Mixed; stage not reported | 2 | 0 | 1 |
| Agitated before static synthesis | 2 | 0 | 2 |

## Unresolved descriptions: 21 records / 5 strings

Associated tabular context is retained in `stirring_review_context.csv`. Targeted publication checks are documented separately; this is not a full source-publication verification.

| Raw string | Positive | Negative | Reason |
|---|---:|---:|---|
| centrifuged at 10,000 rpm | 12 | 0 | Centrifugation alone does not establish a stirring or static state; its stage is not inferred. |
| dropwise addition under Ar | 4 | 0 | Reagent addition alone does not specify agitation. |
| reflux | 3 | 0 | Heating or irradiation alone does not specify agitation. |
| microwave irradiation | 1 | 0 | Heating or irradiation alone does not specify agitation. |
| with or without stirring | 1 | 0 | The extraction lists alternative agitation states, not a unique record-specific state. |
