# Process-detail tables

These optional control tables add three cleaned process features to every original synthesis record. They do not filter on process-field availability.

| File | Rows | Columns |
| --- | ---: | ---: |
| [Process_detail_positive.csv](Process_detail_positive.csv) | 15,340 | 86 |
| [Process_detail_negative.csv](Process_detail_negative.csv) | 15,063 | 79 |

Original `vessel_type` and `stirring` columns are renamed `vessel_type_raw` and `stirring_raw`. Their exact strings, all other source cells, and row order are preserved. Three columns are appended: `vessel_type`, `vessel_volume_mL`, and `agitation`. Both files use UTF-8 with a byte-order mark.

| Added field | Representation |
| --- | --- |
| `vessel_type` | Controlled vessel category; `Not reported` includes missing/unspecified types and the explicitly pooled rare classes described below |
| `vessel_volume_mL` | A positive numeric vessel capacity in mL, `Not reported`, or `Ambiguous` |
| `agitation` | Nine stage-based categories with two-to-five-word labels; sonication remains distinct, and unavailable or unresolved information uses `Not reported` |

## Reproduce

From the repository root, with the package installed (`python -m pip install -e ".[curation,datasets]"`):

```bash
python -m mofinder.curation.process_details --config configs/process_details.json
```

For other processed inputs:

```bash
python -m mofinder.curation.process_details --positive path/to/processed_positive.csv --negative path/to/processed_negative.csv --output results/process_details
```

The command regenerates the derived tables and audit files. It checks exact preservation of source cells and row order and never overwrites either input CSV. [Configuration](../../../configs/process_details.json), [table builder](../../../src/mofinder/curation/process_details.py), [vessel rules](../../../src/mofinder/curation/process_vessels.py), and [agitation rules](../../../src/mofinder/curation/process_stirring.py) are included. The module and `stirring_*` audit filenames retain the original extraction-field name.

## Normalization and audit

Unicode compatibility characters, dash and whitespace variants, case, and explicit metric volume units are normalized. Vessel-body material is distinguished from cap, septum, gasket, seal, spacer, and stirrer material. A glass vial with a PTFE cap remains a vial. Vessel forms, pressure-vessel wording, and PTFE liners are classified conservatively; steel alone does not establish pressurization. Material-only categories are named `Glass vessel`, `Polymer vessel`, and `Metal vessel`. The shortened `PTFE-lined autoclave` retains the membership of the former autoclave / pressure vessel class. Unspecified vessel types are merged into `Not reported`.

The fixed consolidation policy uses synthesis-record frequencies in the full positive reference dataset and applies the same mapping to both classes and both model splits. Vessel classes with fewer than 10 positive records—Crucible (1), Dialysis bag (3), and Rotor insert (1)—are pooled into `Not reported` as requested. That label therefore includes five reported rare vessels as well as missing or unspecified types; it is not a pure missingness indicator. Original descriptions and fine-grained classes remain in the audits. The class map is frozen, not refitted separately on negative records or holdout data.

Capacity conversion supports mL, L, microlitres, cm³, and cc. A reaction charge or solvent volume is not substituted for capacity; dimensions are not converted into a volume. Ranges, multiple/nested vessels, corrupted units, and unspecified dram conventions remain ambiguous. The two liter-scale vial descriptions are also quarantined as ambiguous pending source verification. Other uncommon but explicit capacities are retained and flagged. No missing value is set to zero.

The nine final agitation categories combine stirring, shaking, rotation, vortexing, mixing, and homogenization by process stage, while retaining sonication separately. Each label contains two to five words. `Agitated before static synthesis` preserves an explicitly reported preparation-to-static sequence; `Agitated during preparation` leaves later agitation unknown. `Agitated during synthesis` requires evidence for synthesis-stage agitation, and `Agitated; stage not reported` makes no stage assumption. The term `Agitated` does not imply a particular mechanism when the source does not specify one. `No stirring` denotes explicitly static or unstirred conditions, and `Not reported` is used when no unique agitation state is specified. Reported methods remain available in the raw text and detailed audit categories.

| Final agitation category | Positive records | Negative records |
| --- | ---: | ---: |
| `No stirring` | 6,522 | 6,609 |
| `Not reported` | 3,886 | 3,987 |
| `Agitated before static synthesis` | 1,792 | 1,869 |
| `Agitated during preparation` | 479 | 568 |
| `Agitated during synthesis` | 15 | 18 |
| `Agitated; stage not reported` | 2,223 | 1,740 |
| `Sonicated before static synthesis` | 377 | 232 |
| `Sonicated during preparation` | 22 | 1 |
| `Sonicated; stage not reported` | 24 | 39 |

This fixed mapping is applied to both positive and negative records before JSONL preparation. It groups related methods by stage without using a frequency threshold or an unspecified catch-all class.

The earlier combined category contained 121 positive records from 57 unique DOIs and 115 negative records. Its descriptions were resolved into supported method/stage categories, which are retained in the detailed audit and now mapped to the nine model categories above. A [targeted source audit](audit/AGITATION_SOURCE_AUDIT.md) documents 12 DOI-specific clarifications affecting 29 positive and eight negative records. These include nine positive records outside that earlier category whose ultrasonic wording supports `Sonicated during preparation`, rather than separate mechanical stirring. Original extracted strings remain unchanged; reviewed interpretations are matched by DOI and normalized raw value before classification.

The complete corpus audit covers **1,926 unique vessel strings** and **890 unique strings from the original stirring field**, including all low-frequency descriptions. Iterative corrections addressed PTFE accessories, nested vessels, plurals and synonyms, split unit typography, corrupted micro-unit symbols, and charge-volume wording. The **21 unresolved positive agitation records** were checked with their associated fields: centrifugation (12), addition (4), reflux (3), microwave irradiation (1), and alternative stirring states (1) do not specify a unique stirring/static state. Their model value remains `Not reported`, with reasons retained in the audit. The corpus-wide checks inspect extracted strings and associated tabular context; the targeted source audit identifies the subset also checked against original documents.

- [Every raw-to-clean mapping](audit/all_raw_value_mappings.csv), with separate positive/negative frequencies.
- [Rare mappings](audit/rare_value_mappings.csv), occurring at most five times across both datasets.
- [Mappings requiring review](audit/review_required_mappings.csv), including conservative unresolved capacities and retained rare sizes.
- [Every source row and rule](audit/record_process_audit.csv), kept outside model input.
- [Category consolidation](audit/category_consolidation.csv), including every fine-to-final mapping and its positive/negative counts, and [stirring review context](audit/stirring_review_context.csv).
- [Full category counts](audit/feature_counts.csv), [independent vessel review](audit/vessel_independent_review.md), [agitation normalization audit](audit/stirring_audit_notes.md), and [agitation source audit](audit/AGITATION_SOURCE_AUDIT.md).
- [Manifest](manifest.json), with input/output and implementation hashes.

## Matched training control

The [process-enriched JSONL](../../processed_data_json/processed_enrich/README.md) is nested beneath the standard training folder. It preserves the existing split, labels, order, and original eight inputs, then adds these three fields and the corresponding system prompt. See [preparation and training instructions](../../../docs/process_enrich_training.md), the [positive-dataset figure gallery](../../../docs/process_details/README.md#figures), and the updated [Section S5 draft](../../../docs/process_details/Section_S5_process_details.md). Each figure pairs record counts with unique DOI counts and uses the gradient style of the primary-modulator figure.

Negative process descriptions can be inherited from successful parent protocols. Normalization does not verify that these process conditions were independently observed in a failed attempt. Outcome properties, raw descriptions, rationales, source identifiers, washing, and activation are excluded from the enriched model input. The original split's DOI overlap also remains unchanged; this is a matched representation control, not a new independent-paper evaluation.
