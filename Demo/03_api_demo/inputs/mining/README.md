# Sample documents for the API demo

The sample article and supporting information provide inputs for document matching and text mining. They describe MOF-303 and CAU-23 using illustrative synthesis conditions and placeholder figures. The article contains the synthesis procedures; the supporting information contains characterization methods. Both documents identify DOI `10.1021/jacs.2c09756` as their literature source.

The documents contain synthetic sample text, illustrative synthesis conditions, and no measured experimental data; they are not copies of the published article. Example extraction outputs are stored separately from research datasets.

| File | Role |
| --- | --- |
| `articles/10.1021_jacs.2c09756.pdf` | Main demonstration document |
| `supporting_information/10.1021_jacs.2c09756_SI.pdf` | Supporting-information demonstration document |
| `inventory.csv` | One-row input for document matching |
| `manifest.json` | Document identity and byte checksums |

The filenames follow literature retrieval naming: replace the DOI slash with an underscore and append `_SI` for supporting information. [manifest.json](manifest.json) records document provenance, byte sizes, and SHA-256 checksums.

Use these inputs in [api_demo.ipynb](../../api_demo.ipynb). The [API demo instructions](../../README.md) give the validation and positive/negative mining commands. Model calls require API access; reference extraction outputs are not included. To try your own papers, use the separate [local PDF input folder](../../literature_input/README.md).
