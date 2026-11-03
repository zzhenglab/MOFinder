# Process-detail tables

These tables add cleaned vessel type, vessel capacity, and agitation to the processed synthesis records.

| File | Rows | Columns |
| --- | ---: | ---: |
| [Process_detail_positive.csv](Process_detail_positive.csv) | 15,340 | 86 |
| [Process_detail_negative.csv](Process_detail_negative.csv) | 15,063 | 79 |

All source rows and values are preserved. Original `vessel_type` and `stirring` descriptions are retained as `vessel_type_raw` and `stirring_raw`. Both CSVs use UTF-8 with a byte-order mark.

| Added field | Contents |
| --- | --- |
| `vessel_type` | Cleaned vessel category. Unspecified types and categories with fewer than 10 positive records use `Not reported`. |
| `vessel_volume_mL` | Vessel capacity in mL, `Not reported`, or `Ambiguous`. |
| `agitation` | One of the nine categories below. |

## Normalization

Vessel names are consolidated across spelling, punctuation, and material variants. Capacity values are converted to mL using explicit vessel sizes. Ranges, unclear units, and descriptions with multiple possible capacities use `Ambiguous`.

The same category rules apply to positive and negative records:

| Agitation category | Positive records | Negative records |
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

Before main synthesis means preparation before the main heating or aging step, with later conditions unspecified. Before static synthesis requires an explicitly static subsequent stage. `Stirring reported` and `Sonication reported` leave the stage unspecified. `No stirring` describes explicitly static or unstirred conditions; missing or unresolved descriptions use `Not reported`.

Some negative records carry process descriptions inherited from their source synthesis. Original descriptions remain available in the raw columns.

## Reproduce

From the repository root, after installing `python -m pip install -e ".[curation,datasets]"`:

```bash
python -m mofinder.curation.process_details --config configs/process_details.json
```

For other processed inputs:

```bash
python -m mofinder.curation.process_details --positive path/to/processed_positive.csv --negative path/to/processed_negative.csv --output results/process_details
```

See the [classification code](../../../src/mofinder/curation/process_details.py), [process-enriched training files](../../processed_data_json/processed_enrich_11field/README.md), and [positive-data distributions](../../../docs/process_details/README.md).
