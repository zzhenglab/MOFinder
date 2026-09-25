# Local article and supporting-information inputs

Place a main article PDF in `main/` and its supporting-information PDF in `si/`.
The folder contains three demonstration DOI slots. All supplied PDFs are
placeholders rather than copies of the original publications: the JACS pair
contains synthetic illustrative text, and the other two pairs are blank templates.
The illustrative pair can demonstrate extraction, but its output is not a
scientific result. The default notebook uses a copy of this same pair in
[`inputs/extraction/`](../inputs/extraction/README.md).

| DOI | Main article filename | Supporting-information filename | Included content |
| --- | --- | --- | --- |
| `10.1021/jacs.2c09756` | `main/10.1021_jacs.2c09756.pdf` | `si/10.1021_jacs.2c09756_SI.pdf` | Synthetic illustrative text |
| `10.1002/adfm.200600944` | `main/10.1002_adfm.200600944.pdf` | `si/10.1002_adfm.200600944_SI.pdf` | Blank templates |
| `10.1002/adfm.201002517` | `main/10.1002_adfm.201002517.pdf` | `si/10.1002_adfm.201002517_SI.pdf` | Blank templates |

These DOIs are examples from the included literature inventory. To demonstrate
all three slots, replace the two blank pairs with readable documents. For research
extraction, replace all three pairs with your own source documents. To use different
papers, edit `inventory.csv` and replace the files in both folders. One row
corresponds to one paper. The `DOI` column is required; publisher and DOI-link
columns are optional. Replace the slash in each DOI with `_`; add `_SI` before
the supporting-information extension. Use PDF files with extractable text.
Scanned PDFs need OCR before this workflow can read their text.

Start with three to five papers. The local configuration accepts up to five
inventory rows and uses one API request at a time. Increase `max_papers` in
`../configs/local_papers/document_matching.json` to accept a larger inventory,
and update `quick_run_n` in `negative_reconstruction.json` to match the desired negative
reconstruction limit. Positive extraction reads all rows in the matched manifest.

From the repository root, validate the filenames and document text:

```bash
python Demo/03_api_data_mining/mof_api_data_mining_demo.py validate --config-dir Demo/03_api_data_mining/configs/local_papers
```

Validation lists the remaining blank templates under `placeholder_documents`. A
valid filename alone does not make a blank template ready for extraction. Live
extraction stops until both selected blank pairs have been replaced or removed
from the inventory. The synthetic JACS pair has extractable text and can be used
for demonstration. If your documents have no extractable text, inspect the PDFs
before continuing.

Run positive extraction and then negative reconstruction:

```bash
python Demo/03_api_data_mining/mof_api_data_mining_demo.py positive --config-dir Demo/03_api_data_mining/configs/local_papers --live
python Demo/03_api_data_mining/mof_api_data_mining_demo.py negative --config-dir Demo/03_api_data_mining/configs/local_papers --live
```

An existing `OPENAI_API_KEY` is reused; otherwise the script requests the key
through a hidden prompt. Negative reconstruction reads the positive CSV and synthesis
JSON files, selects documents with trial or failure evidence, and enumerates
saved modification plans. It can return no negative records when the documents
contain no eligible evidence.

Outputs are saved under `results/examples/03_api_data_mining/local_papers/`.
Positive records and synthesis JSON files are in `positive/`; negative plans,
parent records, and enumerated conditions are in `negative/`. Keep these outputs
together. The default one-pair demonstration has a separate output directory.

When changing the paper set, prompts, or models, choose a fresh output directory
in all three configuration files. Extraction and reconstruction resume from saved
records and otherwise skip DOIs that already have outputs.
