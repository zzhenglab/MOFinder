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
| `agitation` | Nine categories with two-to-five-word labels; stirring and sonication retain supported stage distinctions, related mechanical methods share a separate category, and unavailable or unresolved information uses `Not reported` |

## Reproduce

From the repository root, with the package installed (`python -m pip install -e ".[curation,datasets]"`):

```bash
python -m mofinder.curation.process_details --config configs/process_details.json
```

For other processed inputs:

```bash
python -m mofinder.curation.process_details --positive path/to/processed_positive.csv --negative path/to/processed_negative.csv --output results/process_details
```

The command regenerates the derived tables and checks their provenance. It checks exact preservation of source cells and row order and never overwrites either input CSV. [Configuration](../../../configs/process_details.json), [table builder](../../../src/mofinder/curation/process_details.py), [vessel rules](../../../src/mofinder/curation/process_vessels.py), and [agitation rules](../../../src/mofinder/curation/process_stirring.py) are included. The agitation-rule module retains the original extraction-field name.

## Normalization

Unicode compatibility characters, dash and whitespace variants, case, and explicit metric volume units are normalized. Vessel-body material is distinguished from cap, septum, gasket, seal, spacer, and stirrer material. A glass vial with a PTFE cap remains a vial. Vessel forms, pressure-vessel wording, and PTFE liners are classified conservatively; steel alone does not establish pressurization. Material-only categories are named `Glass vessel`, `Polymer vessel`, and `Metal vessel`. The shortened `PTFE-lined autoclave` retains the membership of the former autoclave / pressure vessel class. Unspecified vessel types are merged into `Not reported`.

The fixed consolidation policy uses synthesis-record frequencies in the full positive reference dataset and applies the same mapping to both classes and both model splits. Vessel classes with fewer than 10 positive records—Crucible (1), Dialysis bag (3), and Rotor insert (1)—are pooled into `Not reported` as requested. That label therefore includes five reported rare vessels as well as missing or unspecified types; it is not a pure missingness indicator. Original descriptions remain in the raw CSV columns; the normalization functions also return detailed classifications and rule identifiers. The class map is frozen, not refitted separately on negative records or holdout data.

Capacity conversion supports mL, L, microlitres, cm³, and cc. A reaction charge or solvent volume is not substituted for capacity; dimensions are not converted into a volume. Ranges, multiple/nested vessels, corrupted units, and unspecified dram conventions remain ambiguous. The two liter-scale vial descriptions are also quarantined as ambiguous pending source verification. Other uncommon but explicit capacities are retained and flagged. No missing value is set to zero.

The nine final categories in `agitation` use two-to-five-word labels. `Stirred before static synthesis` requires an explicitly reported stirring-then-static sequence. `Stirred before main synthesis` means stirring during initial mixing or dissolution before the main heating, aging, or reaction step; subsequent stirring or static conditions are unspecified. `Stirring reported` does not imply that stirring continued throughout synthesis; specific reported timing remains in the original descriptions and source-review rules. Sonication uses separate before-static, before-main-synthesis, and reported categories. `Shaking, vortexing, rotation and mixing` includes related mechanical methods and homogenization, with individual methods and stages preserved in the original descriptions and source-review rules. `No stirring` denotes explicitly static or unstirred conditions, and `Not reported` is used when no unique state is specified.

| Final agitation category | Positive records | Negative records |
| --- | ---: | ---: |
| `No stirring` | 6,522 | 6,609 |
| `Not reported` | 3,886 | 3,987 |
| `Stirred before static synthesis` | 1,759 | 1,815 |
| `Stirred before main synthesis` | 495 | 567 |
| `Stirring reported` | 2,190 | 1,756 |
| `Sonicated before static synthesis` | 377 | 232 |
| `Sonicated before main synthesis` | 22 | 1 |
| `Sonication reported` | 24 | 39 |
| `Shaking, vortexing, rotation and mixing` | 65 | 57 |

This fixed mapping is applied to both positive and negative records before JSONL preparation. It uses no agitation-frequency threshold or unspecified catch-all class.

The [source-review registry](../../../src/mofinder/curation/agitation_source_reviews.py) documents 17 description-specific clarifications affecting 50 positive and eight negative records. These include nine positive records whose ultrasonic wording supports `Sonicated before main synthesis` and 17 whose source protocols place stirring before the main synthesis step. Original extracted strings remain unchanged; reviewed interpretations are matched by DOI and normalized raw value before classification.

Normalization was checked against **1,926 unique vessel strings** and **890 unique strings from the original stirring field**, including all low-frequency descriptions. Iterative corrections addressed PTFE accessories, nested vessels, plurals and synonyms, split unit typography, corrupted micro-unit symbols, and charge-volume wording. The **21 unresolved positive agitation records** were checked with their associated fields: centrifugation (12), addition (4), reflux (3), microwave irradiation (1), and alternative stirring states (1) do not specify a unique stirring/static state. Their model value remains `Not reported`; the normalization code records the reason for each classification. The corpus-wide checks inspect extracted strings and associated tabular context; the source-review registry identifies the subset also checked against original documents.

The [manifest](manifest.json) records input/output and implementation hashes. The [positive-dataset distribution tables](../../../docs/process_details/category_counts.csv) provide category counts for the accompanying figures.

## Matched training control

The [process-enriched JSONL](../../processed_data_json/processed_enrich/README.md) is nested beneath the standard training folder. It preserves the existing split, labels, order, and original eight inputs, then adds these three fields and the corresponding system prompt. See [preparation and training instructions](../../../docs/process_enrich_training.md), the [positive-dataset figure gallery](../../../docs/process_details/README.md#figures), and the updated [Section S5 draft](../../../docs/process_details/Section_S5_process_details.md). Each figure pairs record counts with unique DOI counts and uses the gradient style of the primary-modulator figure.

Negative process descriptions can be inherited from successful parent protocols. Normalization does not verify that these process conditions were independently observed in a failed attempt. Outcome properties, raw descriptions, rationales, source identifiers, washing, and activation are excluded from the enriched model input. The original split's DOI overlap also remains unchanged; this is a matched representation control, not a new independent-paper evaluation.
