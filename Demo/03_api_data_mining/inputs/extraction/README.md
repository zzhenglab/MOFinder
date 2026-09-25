# Sample documents for the data mining demo

The sample article and supporting information provide inputs for document matching and synthesis extraction. The supplied PDFs are information-containing placeholders with synthetic illustrative content. They use DOI `10.1021/jacs.2c09756` as a demonstration identifier and are the same files as the JACS pair in [`literature_input/`](../../literature_input/README.md).

The original publication and its supporting information are not included. These placeholders demonstrate the workflow; extracted records are not scientific results. Example extraction outputs are stored separately from research datasets. The other two DOI slots in `literature_input/` contain blank templates.

| File | Role |
| --- | --- |
| `articles/10.1021_jacs.2c09756.pdf` | Main demonstration document |
| `supporting_information/10.1021_jacs.2c09756_SI.pdf` | Supporting-information demonstration document |
| `inventory.csv` | One-row input for document matching |
| `manifest.json` | Document identity and byte checksums |

The filenames follow literature retrieval naming: replace the DOI slash with an underscore and append `_SI` for supporting information. [manifest.json](manifest.json) records document provenance, byte sizes, and SHA-256 checksums.

Use these inputs in [mof_api_data_mining_demo.ipynb](../../mof_api_data_mining_demo.ipynb). The notebook displays the saved JSON after positive extraction and negative reconstruction. The [data mining demo instructions](../../README.md) give the commands for validation, positive extraction, and negative reconstruction. Model calls require API access; reference extraction outputs are not included. To try your own papers, use the separate [local PDF input folder](../../literature_input/README.md).
