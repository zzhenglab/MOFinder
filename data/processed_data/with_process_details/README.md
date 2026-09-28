# Process-detail tables

These optional control tables add three cleaned process features to every original synthesis record. They do not filter on process-field availability.

| File | Rows | Columns |
| --- | ---: | ---: |
| [Process_detail_positive.csv](Process_detail_positive.csv) | 15,340 | 86 |
| [Process_detail_negative.csv](Process_detail_negative.csv) | 15,063 | 79 |

Original `vessel_type` and `stirring` columns are renamed `vessel_type_raw` and `stirring_raw`. Their exact strings, all other source cells, and row order are preserved. Three columns are appended: `vessel_type`, `vessel_volume`, and `stirring`. Both files use UTF-8 with a byte-order mark.

| Added field | Representation |
| --- | --- |
| `vessel_type` | Controlled category based on the recorded vessel description; missing or equipment-only descriptions are `Not reported` |
| `vessel_volume` | A positive numeric vessel capacity in mL, `Not reported`, or `Ambiguous` |
| `stirring` | Controlled agitation/stage description, `Not reported`, or `Unclear / ambiguous` |

## Reproduce

From the repository root, with the package installed (`python -m pip install -e ".[curation,datasets]"`):

```bash
python -m mofinder.curation.process_details --config configs/process_details.json
```

For other processed inputs:

```bash
python -m mofinder.curation.process_details --positive path/to/processed_positive.csv --negative path/to/processed_negative.csv --output results/process_details
```

The command regenerates the derived tables and audit files. It checks exact preservation of source cells and row order and never overwrites either input CSV. [Configuration](../../../configs/process_details.json), [table builder](../../../src/mofinder/curation/process_details.py), [vessel rules](../../../src/mofinder/curation/process_vessels.py), and [stirring rules](../../../src/mofinder/curation/process_stirring.py) are included.

## Normalization and audit

Unicode compatibility characters, dash and whitespace variants, case, and explicit metric volume units are normalized. Vessel-body material is distinguished from cap, septum, gasket, seal, spacer, and stirrer material. A glass vial with a PTFE cap remains a vial. Vessel forms, pressure-vessel wording, and PTFE liners are classified conservatively; steel alone does not establish pressurization. Named but underspecified vessels retain explicit shape/type-unspecified categories. A broad `Other vessel` bin is not used.

Capacity conversion supports mL, L, microlitres, cm³, and cc. A reaction charge or solvent volume is not substituted for capacity; dimensions are not converted into a volume. Ranges, multiple/nested vessels, corrupted units, and unspecified dram conventions remain ambiguous. The two liter-scale vial descriptions are also quarantined as ambiguous pending source verification. Other uncommon but explicit capacities are retained and flagged. No missing value is set to zero.

Stirring classes distinguish explicit static conditions, agitation before static synthesis, agitation during preparation with later conditions unknown, and agitation explicitly during synthesis. Unqualified “stirred” does not establish stirring throughout heating. Sonication and other agitation remain distinguishable. Non-agitation text and contradictory alternatives are explicitly unresolved.

The complete corpus audit covers **1,926 unique vessel strings** and **890 unique stirring strings**, including all low-frequency descriptions. Iterative corrections addressed PTFE accessories, nested vessels, plurals and synonyms, split unit typography, corrupted micro-unit symbols, and charge-volume wording. All vessel strings resolve to a defined category or `Not reported`; **21 positive stirring records** remain `Unclear / ambiguous` because they report centrifugation, addition, reflux, microwave irradiation, or alternative stirring states. This audit evaluates the extracted strings, not the source publications.

- [Every raw-to-clean mapping](audit/all_raw_value_mappings.csv), with separate positive/negative frequencies.
- [Rare mappings](audit/rare_value_mappings.csv), occurring at most five times across both datasets.
- [Mappings requiring review](audit/review_required_mappings.csv), including conservative unresolved capacities and retained rare sizes.
- [Every source row and rule](audit/record_process_audit.csv), kept outside model input.
- [Full category counts](audit/feature_counts.csv), [independent vessel review](audit/vessel_independent_review.md), and [stirring audit](audit/stirring_audit_notes.md).
- [Manifest](manifest.json), with input/output and implementation hashes.

## Matched training control

The [process-enriched JSONL](../../final_json/processed_enrich/README.md) is nested beneath the standard training folder. It preserves the existing split, labels, order, and original eight inputs, then adds these three fields and the corresponding system prompt. See [preparation and training instructions](../../../docs/process_enrich_training.md) and [distribution figures](../../../docs/process_details/README.md).

Negative process descriptions can be inherited from successful parent protocols. Normalization does not verify that these process conditions were independently observed in a failed attempt. Outcome properties, raw descriptions, rationales, source identifiers, washing, and activation are excluded from the enriched model input. The original split's DOI overlap also remains unchanged; this is a matched representation control, not a new independent-paper evaluation.
