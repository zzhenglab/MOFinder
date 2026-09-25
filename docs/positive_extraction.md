# Primary synthesis extraction

`mofinder.extraction.positive` extracts primary MOF syntheses from the article and supporting-information texts. The structured schema defines the extracted fields, and the prompts specify the extraction criteria. `prompts/positive_system.txt` and `prompts/positive_user.txt` contain the complete prompt texts; `src/mofinder/extraction/schemas.py` defines the structured response.

The input manifest must contain `DOI`, `Main File` and `SI File`. CSV and Excel inputs are supported. An empty document field is allowed when the other document has readable text. Bare filenames resolve within the configured article or supporting-information directory; absolute document paths are accepted. Existing project-relative paths also work. Conflicting paths for one DOI, blank DOIs and colliding JSON directory names are rejected. Identical repeated DOI/document pairs produce one extraction job.

Install the `mining` extra and review `configs/positive_extraction.json`. Its model, concurrency of 100 and flush threshold of 50 follow the revised full-corpus invocation; lower concurrency if required by the available API limits. The `validate` command reads local documents and reports missing files and text lengths without sending model requests:

```bash
python -m mofinder.extraction.positive validate --config configs/positive_extraction.json
```

Set `OPENAI_API_KEY` in the environment, then start extraction:

```bash
python -m mofinder.extraction.positive run --config configs/positive_extraction.json
```

For the demonstration article/SI pair, create the example document manifest
with `configs/example_document_matching.json`, then validate its extraction
inputs:

```bash
python -m mofinder.extraction.positive validate --config configs/example_positive_extraction.json
```

`configs/example_positive_extraction.json` writes to
`results/examples/mining/positive/` and uses concurrency 2. To extract the
example through the API, set `OPENAI_API_KEY` in the terminal environment and
replace `validate` with `run`. That command sends the example document texts
to the configured model and incurs the corresponding API usage.

Each request includes the DOI and up to 400,000 characters from each document. Text extraction uses `pypdf` for PDF files, XML extraction for DOCX and optional `textract` for legacy DOC files. Image-only documents require a separate OCR step. No request is made when both documents have no readable text. The runner uses structured responses and retries an unsuccessful extraction once after 0.5 seconds; SDK retries may occur separately.

The output CSV has the original 83 columns. It represents up to three metals, three linkers, two modulators and the main and secondary solvents. The JSON payload retains all schema fields and list items, including additional reagents and solvent roles. Each DOI has a directory under `results/extraction/positive/mof_json_store/` containing the raw response, `article_extraction.json` and numbered `synthesis_001.json` files. CSV columns `raw_output` and `parsed_json` contain paths, not embedded JSON. Retain both the CSV and JSON store for negative mining.

A valid response with no syntheses produces a single empty synthesis row with `status=ok`. Its article trial flag and notes remain blank in the CSV, following the revised extraction logic; the article JSON retains the response flag and notes. A failed extraction produces `status=failed` with an error. Resume skips every DOI already present in the CSV, including failed rows. To retry selected failed DOIs, create a separate manifest and output location, then inspect and reconcile the resulting records.

Rows with a different column set are reported and skipped. JSON is persisted before the CSV is flushed, so a stopped run can leave saved JSON for DOIs absent from the CSV. Rebuild those rows offline:

```bash
python -m mofinder.extraction.backfill --config configs/positive_extraction.json
```

Backfill appends only unrecorded DOIs. It uses valid `article_extraction.json` as the authoritative payload and recovers from individual synthesis files when that article file is missing or corrupt. Invalid payloads are reported without marking their DOI complete. Missing JSON directories are listed in `missing_json_dois.txt` beside the output CSV. The command makes no model requests.

Payload files are replaced after complete writes. When a DOI is rerun with fewer syntheses, obsolete numbered synthesis files are removed after the new article payload is saved. This prevents stale records entering downstream synthesis indexing. Run only one process per output CSV and JSON store; concurrent independent runners are not supported.

The [API demo](../Demo/03_api_demo/README.md) provides an interactive example. The sample PDFs illustrate file matching and local text extraction; their illustrative outcomes are not evidence of experimentally observed syntheses or failures.

Offline tests compare all 83 flattened fields against the original active extraction function on synthetic records, verify schema and prompt hashes, inspect mocked request payloads, and exercise retries, resume, duplicate handling and JSON recovery. They do not validate live model responses.
