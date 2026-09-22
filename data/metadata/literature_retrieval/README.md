# Literature retrieval input tables

These CSV exports retain the source literature retrieval inventories and their recorded
download states. Each file contains all 7,437 source rows in their original order.
There are 7,435 distinct DOI values in each table; duplicate rows have not been
removed. Source and export checksums are recorded in `manifest.json`.

| File | Source workbook | Columns |
| --- | --- | --- |
| `papers.csv` | `SELECTED 7000.xlsx` | DOI, Publisher, DOI Link, Downloaded |
| `supporting_information.csv` | `SELECTED 7000 SI.xlsx` | DOI, Publisher, DOI Link, Downloaded, SI Downloaded |

The exports contain only literature retrieval fields. The source workbooks are unchanged.
The `Publisher` column uses the neutral identifiers consumed by the literature retrieval
code. Unsupported values are represented as `unmapped`.

## Publisher resolution

The two source workflows used different publisher matching rules. The paper
workflow matched canonical prefixes, while the SI workflow also recognized aliases
and matches within the publisher field. The exports preserve those routing results
before replacing the resolved keys with neutral identifiers. No previously
unsupported entry has been assigned to a supported paper flow.

| Publisher identifier | Paper input | SI input |
| --- | ---: | ---: |
| `publisher_A` | 1,770 | 1,770 |
| `publisher_E` | 1,714 | 2,345 |
| `publisher_R` | 2,038 | 2,038 |
| `publisher_S` | 262 | 292 |
| `publisher_W` | 989 | 989 |
| `unmapped` | 664 | 3 |
| Total | 7,437 | 7,437 |

## Recorded download states

Status values are preserved as `1`, `0`, or an empty CSV field. These are saved
states from the source workflow, not an independent check that the corresponding
files are available on the current computer.

| Input and status field | `1` | `0` | Empty |
| --- | ---: | ---: | ---: |
| Paper input: `Downloaded` | 6,164 | 851 | 422 |
| SI input: `Downloaded` | 294 | 3 | 7,140 |
| SI input: `SI Downloaded` | 5,707 | 1,255 | 475 |

The two `Downloaded` columns come from separate workbook snapshots and are not
merged. In the SI input, `SI Downloaded` is the SI literature retrieval state. Preserve a
copy of each table before resetting states for a new literature retrieval run.

## Local documents

Article PDFs and supporting-information documents are not included. Store
downloaded copies in the configured local directories. Examples of the table
format and document-directory placeholders are in
[`Demo/04_literature_retrieval`](../../../Demo/04_literature_retrieval/README.md).
