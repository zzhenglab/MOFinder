# Sample documents for the data mining demo

These synthetic article and supporting-information PDFs demonstrate document matching and synthesis extraction. They use DOI `10.1021/jacs.2c09756` as an example identifier and are copies of the synthetic pair in [`literature_input/`](../../literature_input/README.md). Replace them with source documents for research extraction.

| File | Role |
| --- | --- |
| `articles/10.1021_jacs.2c09756.pdf` | Main demonstration document |
| `supporting_information/10.1021_jacs.2c09756_SI.pdf` | Supporting-information demonstration document |
| `inventory.csv` | One-row input for document matching |
| `manifest.json` | Document identity and byte checksums |

The filenames replace the DOI slash with an underscore and append `_SI` for supporting information.

Open [mof_api_data_mining_demo.ipynb](../../mof_api_data_mining_demo.ipynb) or follow the [data mining commands](../../README.md) to validate inputs, extract positive records, and reconstruct negative conditions. Model calls require API access.
