# Literature retrieval input format

`input_template.csv` illustrates the columns and neutral publisher identifiers
used by the literature retrieval tools. All five rows are placeholders. The DOI values and
`example.invalid` links must be replaced with real input records before downloading.
This file is not a live download test.

| Column | Meaning |
| --- | --- |
| `DOI` | Article DOI used to open the landing page and construct a filename |
| `Publisher` | A configured neutral publisher identifier |
| `DOI Link` | Landing-page URL |
| `Downloaded` | Recorded paper download state: `1`, `0`, or empty |
| `SI Downloaded` | Recorded SI download state: `1`, `0`, or empty |

Use [`data/metadata/literature_retrieval`](../../data/metadata/literature_retrieval/README.md) for
the archived literature retrieval inventories. Neither the examples nor those tables include
article or SI document contents.

The `articles/` and `supporting_information/` directories contain documentation
placeholders only. Configure the download directories to match the local
literature retrieval setup.
