# Literature retrieval

The inventories list the 7,435 papers retained by abstract triage from 13,770
starting papers; 6,335 papers were excluded. Paper counts use distinct normalized
DOIs. The article and supporting-information inventories contain the same DOI set.

| File | Contents |
| --- | --- |
| [papers.csv](papers.csv) | Article inventory with DOI, Publisher, and DOI Link |
| [supporting_information.csv](supporting_information.csv) | Supporting-information inventory with the same columns |

Each table retains 7,437 source rows, representing 7,435 distinct DOIs. The two
repeated DOIs are `10.1021/acs.chemmater.2c00846` and
`10.1021/acs.inorgchem.2c04233`; each appears twice. The starting bibliography
similarly retains 13,773 rows representing 13,770 papers.

## Paper and record counts

| Collection | Papers (unique DOIs) | Stored rows or synthesis records |
| --- | ---: | ---: |
| [Starting bibliography](../literature_metadata.csv) | 13,770 | 13,773 rows |
| Retained article and SI inventories | 7,435 | 7,437 rows in each inventory |
| Excluded by abstract triage | 6,335 | Starting DOI set minus retained DOI set |
| [Human triage reference](../../../benchmarks/abstract_triage/README.md) | 478 | 478 annotation rows |
| [Processed positive records](../processed_positive.csv) | 4,568 | 15,340 synthesis records |
| [Positive extraction reference](../../../benchmarks/positive_extraction/README.md) | 200 | 1,086 synthesis records |

The published inventories omit `Downloaded` and `SI Downloaded` statuses.
Their DOI lists describe the retained corpus; file availability is a separate
count from the local download inventory or document-matching output.

Of the 4,568 DOIs in the processed positive table, 4,567 occur in the starting
bibliography and retained inventory. DOI `10.1021/jacs.5c08726` contributes one
positive record but is absent from both lists. Its missing publication year is
also noted in the [dataset guide](../../../docs/datasets.md).

See the [retrieval guide](../../../docs/literature_retrieval.md)
for usage and [manifest.json](manifest.json) for file provenance.
