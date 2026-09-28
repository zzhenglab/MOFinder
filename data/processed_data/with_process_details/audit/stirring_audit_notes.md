# Stirring normalization audit

Parser: `process-stirring-v1`. Inputs: `processed_positive.csv` (15,340 records) and `processed_negative.csv` (15,063 records).

All 890 unique extracted strings were enumerated and reviewed by category, including 657 strings occurring in at most five combined records. The complete mapping, frequencies, normalized text and matching rule are in `stirring_all_raw_values.csv`. This is a review of extracted text; source publications were not re-read.

Rules normalize Unicode width, dashes, whitespace and case before classification. Explicit static synthesis takes priority over initial mixing. Stirring, sonication and other initial agitation remain separate; when both stirring and sonication are specified, the class records stirring and the raw field retains both. Preparation followed by heating does not establish static heating. Bare `stirred`, speeds, intensity adjectives and even `continuous stirring` do not identify the synthesis stage and remain stage-not-reported. Only explicit reaction-stage wording supports `Stirred during synthesis`. These text classes summarize what is reported; they are not validated measurements of agitation.

Audit refinements included recognizing `left standing` and `aged without stirring` as static; retaining rotation despite a separate prestir; handling Unicode range symbols and nonbreaking hyphens; recognizing `pre-stir/sonication`; retaining unknown later agitation after sealing, heating, reflux or diffusion; and resolving the rare `vigorous 5 min before heating` as preparation agitation without inventing a stirring mechanism. Post-cooling stirring does not count as preparation. Reagent addition, reflux, microwave irradiation and centrifugation alone are not assigned to a synthesis-agitation method.

| Class | Positive | Negative | Unique raw strings |
|---|---:|---:|---:|
| Not reported | 3,865 | 3,987 | 2 |
| Static / no stirring | 6,522 | 6,609 | 38 |
| Stirred before static synthesis | 1,758 | 1,815 | 411 |
| Sonicated before static synthesis | 377 | 232 | 118 |
| Other agitation before static synthesis | 34 | 54 | 15 |
| Stirred during preparation; later agitation not reported | 482 | 567 | 138 |
| Sonicated during preparation; later agitation not reported | 13 | 1 | 8 |
| Other agitation during preparation; later agitation not reported | 5 | 1 | 2 |
| Stirred during synthesis | 4 | 10 | 4 |
| Stirred; stage not reported | 2,194 | 1,738 | 120 |
| Sonicated; stage not reported | 24 | 39 | 6 |
| Shaken / rotated; stage not reported | 29 | 2 | 18 |
| Other agitation; stage not reported | 12 | 8 | 5 |
| Unclear / ambiguous | 21 | 0 | 5 |

## Residual ambiguity: 21 records / 5 unique strings

These remain `Unclear / ambiguous`, distinct from `Not reported`, with an explicit review reason. Do not silently recode these phrases as static, stirred, or missing.

| Raw string | Positive | Negative | Reason |
|---|---:|---:|---|
| centrifuged at 10,000 rpm | 12 | 0 | Centrifugation alone is not evidence of synthesis-stage stirring. |
| dropwise addition under Ar | 4 | 0 | Reagent addition alone does not specify agitation. |
| reflux | 3 | 0 | Heating or irradiation alone does not specify agitation. |
| microwave irradiation | 1 | 0 | Heating or irradiation alone does not specify agitation. |
| with or without stirring | 1 | 0 | The extraction lists alternative agitation states, not a unique record-specific state. |
