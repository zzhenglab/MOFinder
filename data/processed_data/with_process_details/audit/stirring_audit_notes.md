# Stirring normalization audit

Parser: `process-stirring-v2`. Inputs: `processed_positive.csv` (15,340 records) and `processed_negative.csv` (15,063 records).

All 890 unique extracted strings were enumerated and reviewed by category, including 657 strings occurring in at most five combined records. The complete mapping, frequencies, normalized text and matching rule are in `stirring_all_raw_values.csv`. This is a review of extracted text; source publications were not re-read.

Rules normalize Unicode width, dashes, whitespace and case before classification. Explicit static synthesis takes priority over initial mixing. The detailed audit retains stirring, sonication and other initial agitation separately; when both stirring and sonication are specified, the detailed class records stirring and the raw field retains both. Preparation followed by heating does not establish static heating. Bare `stirred`, speeds, intensity adjectives and even `continuous stirring` do not identify the synthesis stage and remain stage-not-reported. Only explicit reaction-stage wording supports the detailed class `Stirred during synthesis`. These text classes summarize what is reported; they are not validated measurements of agitation.

Audit refinements included recognizing `left standing` and `aged without stirring` as static; retaining rotation despite a separate prestir; handling Unicode range symbols and nonbreaking hyphens; recognizing `pre-stir/sonication`; retaining unknown later agitation after sealing, heating, reflux or diffusion; and resolving the rare `vigorous 5 min before heating` as preparation agitation without inventing a stirring mechanism. Post-cooling stirring does not count as preparation. Reagent addition, reflux, microwave irradiation and centrifugation alone are not assigned to a synthesis-agitation method.

## Final class consolidation

The seven detailed agitation categories with fewer than 50 positive synthesis records in the fixed 15,340-record reference are merged into `Other reported agitation`. The same fixed mapping is used for positive and negative rows, future input batches, and model inputs. It is not recalculated per dataset or split. This broad class asserts that agitation was reported but does not imply a shared method or stage. `detailed_value`, `consolidation_rule`, the original rule, and raw text retain the specific evidence. Stage-aware detailed classes remain available for a future sensitivity analysis.

| Detailed class merged | Positive reference count |
|---|---:|
| Other agitation before static synthesis | 34 |
| Shaken / rotated; stage not reported | 29 |
| Sonicated; stage not reported | 24 |
| Sonicated during preparation; later agitation not reported | 13 |
| Other agitation; stage not reported | 12 |
| Other agitation during preparation; later agitation not reported | 5 |
| Stirred during synthesis | 4 |

## Final class counts

| Class | Positive | Negative | Unique raw strings |
|---|---:|---:|---:|
| Not reported | 3,886 | 3,987 | 7 |
| Static / no stirring | 6,522 | 6,609 | 38 |
| Stirred before static synthesis | 1,758 | 1,815 | 411 |
| Sonicated before static synthesis | 377 | 232 | 118 |
| Stirred during preparation; later agitation not reported | 482 | 567 | 138 |
| Stirred; stage not reported | 2,194 | 1,738 | 120 |
| Other reported agitation | 121 | 115 | 58 |

## Agitation not determinable: 21 records / 5 unique strings

The final class is `Not reported` because a unique supported agitation state is unavailable. The detailed audit retains `Unclear / ambiguous` and an explicit reason, distinguishing these nonempty descriptions from a blank source field. They are not recoded as static or stirred. Associated vessel, temperature, duration, washing, and activation fields for every affected row are in `stirring_review_context.csv`.

The reference audit inspected all 21 affected positive rows. The 12 centrifugation records from DOIs `10.1039/c4ta06820c` and `10.1016/j.matchemphys.2022.127039` tie centrifugation to their reported durations; this is not evidence that centrifugation was necessarily postprocessing, but it still does not identify a stirring/static state. Three reflux rows specify heating; one microwave row specifies irradiation; four addition rows specify reagent addition under argon. None supplies a separate agitation state in the available associated fields. The remaining row says `with or without stirring` and lacks a unique record-specific choice. The audit does not invent a choice or infer agitation from heating.

| Raw string | Positive | Negative | Reason |
|---|---:|---:|---|
| centrifuged at 10,000 rpm | 12 | 0 | Centrifugation alone does not establish a stirring or static state; its stage is not inferred. |
| dropwise addition under Ar | 4 | 0 | Reagent addition alone does not specify agitation. |
| reflux | 3 | 0 | Heating or irradiation alone does not specify agitation. |
| microwave irradiation | 1 | 0 | Heating or irradiation alone does not specify agitation. |
| with or without stirring | 1 | 0 | The extraction lists alternative agitation states, not a unique record-specific state. |
