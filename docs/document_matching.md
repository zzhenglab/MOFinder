# Document matching

Document matching connects the literature retrieval inventory to local article and
supporting-information files. The implementation is in
[`src/mofinder/literature/match_documents.py`](../src/mofinder/literature/match_documents.py).

## Inputs and filenames

The default inventory is
`data/processed_data/literature_retrieval/supporting_information.csv`. A CSV or XLSX file with a
`DOI` column can be selected in `configs/document_matching.json` or specified with
`--input-file`. Additional columns and repeated DOI rows are retained.

Place articles in `data/local/articles` and supporting information in
`data/local/supporting_information`. Filenames use underscores in place of DOI
slashes:

| Document | Example filename |
| --- | --- |
| Article | `10.1021_jacs.2c09756.pdf` |
| Supporting information | `10.1021_jacs.2c09756_SI.pdf` |

Matching removes `doi:` and DOI URL prefixes and ignores filename case. Main
articles must be PDFs. SI candidates are checked in this order: `_SI.pdf`,
`_SI.docx`, `_SI.doc`. Only the immediate directory is searched. Case collisions
between two filenames are reported as ambiguous rather than choosing one.
The SI directory must exist; a missing article directory produces a warning
and permits SI-only matching.

## Run matching

From the repository root:

```bash
python -m mofinder.literature.match_documents match --config configs/document_matching.json
```

For the demonstration documents:

```bash
python -m mofinder.literature.match_documents match --config configs/example_document_matching.json
```

The example PDFs are demonstration documents. Their illustrative conditions
and outcomes are not a transcription of the publication associated with the
example DOI.

The production configuration writes:

| Output | Contents |
| --- | --- |
| `results/extraction/document_manifest.csv` | `DOI`, `Main File`, `SI File`, with absolute local file paths |
| `results/extraction/matched_inventory.csv` | All inventory metadata, reconciled presence flags and matched filenames |
| `results/extraction/document_matching_summary.json` | Both/main-only/SI-only/neither counts and files without an inventory DOI |

The literature retrieval inventory is read without modification. Presence flags in the
matched copy are recalculated for every row: `1` when a file is found and blank
otherwise. A blank DOI clears all matched fields. These flags describe current
files and do not retain literature retrieval failure or skip statuses. The manifest
retains all rows, including unmatched rows and duplicate DOIs.

Unmatched-file reporting uses the same case-insensitive DOI bases as matching.
Its list describes filenames with no corresponding inventory DOI; alternative
SI formats sharing a known DOI are not listed as unmatched.

## Optional word and token counts

Counting is a separate local analysis step and is not required for extraction:

```bash
python -m mofinder.literature.match_documents count --config configs/document_matching.json --plots
```

Use `configs/example_document_matching.json` to count the demonstration pair.
Counting requires `tiktoken` and `pdfminer.six` (or the `PyPDF2` fallback).
Saving the optional plots also requires `matplotlib`. The tokenizer requests
the `gpt-4o` encoding and falls back to `cl100k_base`.
Tokenizer assets may be downloaded on first use; there are no model
API calls.

The six count columns are `Main Words`, `SI Words`, `Combined Words`,
`Main Tokens`, `SI Tokens`, and `Combined Tokens`. Words use the Unicode
regular expression `\b\w+\b`. **Combined uses SI when its count is present,
otherwise the main article. It is not a sum.** A zero SI count is present and
therefore remains the Combined count.

Only PDF text extraction is supported by this counting step; no OCR is run.
DOC and DOCX files can be matched, but their text is not extracted here.
To preserve the original counting convention, an existing non-PDF file or a
PDF with no extractable text receives zero for missing counts. The count
summary lists unsupported files, empty-text PDFs and missing files separately.
Missing paths leave counts empty. Check these diagnostics before interpreting
document-size statistics.

Counts are saved separately in `results/extraction/document_counts.csv` and
summary statistics in `document_counts_summary.json`. Existing nonempty counts
are retained. Reusing the count file requires identical DOI and path rows;
select a new `counts_file` when the matched inventory changes. Counts do not
track changes to file contents or tokenizer settings, so also select a new
count file when either changes. The original literature retrieval and matched
inventories remain unchanged. Optional figures use the original six 50-bin
histograms and are saved under `document_count_plots/`.
