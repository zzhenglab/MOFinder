# Local article and supporting-information inputs

Place a main article PDF in `main/` and its supporting-information PDF in `si/`.
The three supplied pairs are blank document templates. Replace all six files with
real documents before extraction, keeping their filenames. The templates contain
no published article content or extraction records.

| DOI | Main article filename | Supporting-information filename |
| --- | --- | --- |
| `10.1021/jacs.2c09756` | `main/10.1021_jacs.2c09756.pdf` | `si/10.1021_jacs.2c09756_SI.pdf` |
| `10.1002/adfm.200600944` | `main/10.1002_adfm.200600944.pdf` | `si/10.1002_adfm.200600944_SI.pdf` |
| `10.1002/adfm.201002517` | `main/10.1002_adfm.201002517.pdf` | `si/10.1002_adfm.201002517_SI.pdf` |

These DOIs are examples from the included literature inventory. To use different
papers, edit `inventory.csv` and replace the files in both folders. One row
corresponds to one paper. The `DOI` column is required; publisher and DOI-link
columns are optional. Replace the slash in each DOI with `_`; add `_SI` before
the supporting-information extension. Use PDF files with extractable text.
Scanned PDFs need OCR before this workflow can read their text.

Start with three to five papers. The local configuration accepts up to five
inventory rows and uses one API request at a time. Increase `max_papers` in
`../configs/local_papers/document_matching.json` to accept a larger inventory,
and update `quick_run_n` in `negative_mining.json` to match the desired negative
mining limit. Positive extraction reads all rows in the matched manifest.

From the repository root, validate the filenames and document text:

```bash
python Demo/03_api_demo/run_demo.py validate --config-dir Demo/03_api_demo/configs/local_papers
```

Validation lists any remaining templates under `placeholder_documents`. A valid
filename alone does not make a template ready for extraction. Live mining stops
until every selected template has been replaced. If real documents have no
extractable text, inspect the PDFs before continuing.

Run positive extraction and then negative extraction:

```bash
python Demo/03_api_demo/run_demo.py positive --config-dir Demo/03_api_demo/configs/local_papers --live
python Demo/03_api_demo/run_demo.py negative --config-dir Demo/03_api_demo/configs/local_papers --live
```

An existing `OPENAI_API_KEY` is reused; otherwise the script requests the key
through a hidden prompt. The negative stage reads the positive CSV and synthesis
JSON files, selects documents with trial or failure evidence, and enumerates
saved modification plans. It can return no negative records when the documents
contain no eligible evidence.

Outputs are saved under `results/examples/03_api_demo/local_papers/`.
Positive records and synthesis JSON files are in `positive/`; negative plans,
parent records, and enumerated conditions are in `negative/`. Keep these outputs
together. The default one-pair demonstration has a separate output directory.

When changing the paper set, prompts, or models, choose a fresh output directory
in all three configuration files. The extraction stages resume from saved
records and otherwise skip DOIs that already have outputs.
