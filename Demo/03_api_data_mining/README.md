# Data mining demo (API required)

This demonstration runs abstract triage, positive extraction, and negative
reconstruction through the same Python modules used in the main
workflow. Model calls require an API key and access to the configured models.

Start with [mof_api_data_mining_demo.ipynb](mof_api_data_mining_demo.ipynb). It displays four complete abstracts,
previews the exact requests, and compares GPT predictions with human labels.
Continue in the same notebook to extract positive synthesis records from the
included article/SI pair and reconstruct negative conditions from the extracted
evidence. Each extraction section displays its saved JSON after a live run.
The corresponding terminal commands use [mof_api_data_mining_demo.py](mof_api_data_mining_demo.py).

There are three demonstration DOI slots in [literature_input/](literature_input/README.md).
All supplied PDFs are placeholders: the `10.1021/jacs.2c09756` pair contains
synthetic illustrative text, and the other two pairs are blank templates. These
files demonstrate input handling and extraction without distributing the original
publications. The default notebook selects only the illustrative pair; its
extracted records are demonstration outputs, not scientific results.

The notebook starts with empty outputs and all live switches set to `False`.
Run the preview cells to inspect the abstracts, requests, and document validation
without making API calls.
After a live triage run, the notebook's comparison section shows the predictions,
human references, agreement, request status, and errors, and saves that table in
the run folder.

The two offline demonstrations remain in [`Demo/01_data_curation`](../01_data_curation/README.md)
and [`Demo/02_dataset_preparation`](../02_dataset_preparation/README.md).

## Install and check the inputs

From the repository root:

```bash
python -m pip install -e ".[mining,notebook]"
python Demo/03_api_data_mining/mof_api_data_mining_demo.py
jupyter lab Demo/03_api_data_mining/mof_api_data_mining_demo.ipynb
```

The default command makes no API requests. It checks the triage inputs, matches
the sample article/SI pair, and reads both document texts. Before positive extraction
has run, the negative reconstruction report lists the positive extraction CSV as a missing
input. That CSV and its synthesis JSON files are created by positive extraction.

Commands also work from this folder using `python mof_api_data_mining_demo.py`, or from another
directory with an absolute path to the script. Configuration paths are resolved
relative to the repository, independently of the current working directory.

To check only the triage inputs, run `python Demo/03_api_data_mining/mof_api_data_mining_demo.py triage`.
The included tables contain 12 abstracts and reference labels (8 Y and 4 N).
The configuration schedules the first four abstracts (2 Y and 2 N). The validation
summary counts the eight unscheduled references under `missing_reference_publications`;
their abstracts are present, but outside the configured four-paper subset.

## Run the model-assisted workflows

The notebook has three switches, each initially `False`: `RUN_TRIAGE`,
`RUN_POSITIVE_EXTRACTION`, and `RUN_NEGATIVE_RECONSTRUCTION`. Enable the desired workflow and
run its cell. Run positive extraction before negative reconstruction. Use an existing
`OPENAI_API_KEY` or enter the key through the hidden prompt. Live requests send
the selected text to OpenAI and incur API charges. Previewing inputs and prompts
does not generate predictions.

If the triage configuration, input tables, or prompt changes after previewing,
rerun the preview cells before enabling requests. The notebook checks their
identities before dispatch and compares predictions with the reference labels
saved for that run.

Enable model requests explicitly with `--live`. An existing `OPENAI_API_KEY`
environment variable is reused; otherwise, the script requests the key through
a hidden prompt. The key is not written to the configuration files.

```bash
python Demo/03_api_data_mining/mof_api_data_mining_demo.py triage --live
python Demo/03_api_data_mining/mof_api_data_mining_demo.py positive --live
python Demo/03_api_data_mining/mof_api_data_mining_demo.py negative --live
```

Run positive extraction before negative reconstruction. The last command generates modification
plans and then enumerates their saved options locally. To inspect eligible
documents without model calls, run the negative command without `--live` after
positive extraction has finished.

| Example | Input and size | Default configuration |
| --- | --- | --- |
| Abstract triage | Four abstracts selected from the 12-paper subset in `inputs/` | GPT-5; high reasoning effort; one round; one request at a time |
| Positive extraction | One illustrative article/SI pair in [`inputs/extraction/`](inputs/extraction/README.md) | GPT-5; one document at a time |
| Negative reconstruction | Positive CSV, synthesis JSON files, and the same article/SI pair | GPT-5; medium reasoning effort; at most one eligible document |
| Local paper extraction | Three DOI slots in `literature_input/main/` and `literature_input/si/`: one illustrative pair and two blank pairs | Separate `configs/local_papers/`; up to five papers; one request at a time |

The triage settings are in [`configs/triage.json`](configs/triage.json):
`model: "gpt-5"`, `reasoning_effort: "high"`, `max_output_tokens: 25000`, and
`request_timeout: 600` seconds. GPT-5 supports high reasoning effort; see the
[model documentation](https://developers.openai.com/api/docs/models/gpt-5).
The token limit covers reasoning and the final answer, which must still be a
single `Y` or `N`; it is a ceiling, not a requested answer length. See the
[reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#allocating-space-for-reasoning)
for token-budget behavior. Adjust these settings before previewing requests.

Triage metadata and human labels are joined by DOI. Reference labels are used
only to compare results and are never sent to the model. The notebook shows each
prediction's request status and any error, so failed requests remain visible.
These small inputs demonstrate the workflow and do not form a performance benchmark.

The demonstration PDFs contain illustrative synthesis conditions. Negative reconstruction uses
the positive extraction's `YES` flag and supporting notes to select trial or
failure evidence. Depending on the extracted evidence, it may produce no eligible
documents or no enumerated records. Enumerated combinations are reconstructed
conditions and are not individually verified experimental failures. The demonstration
uses no corpus-specific manual enumeration corrections.

## Extract from three to five local papers

The [literature input folder](literature_input/README.md) contains three DOI-named
article/SI pairs and a matching inventory. The JACS pair contains synthetic
illustrative content; the other two pairs are blank templates. For a demonstration
with all three slots, supply readable documents for both blank pairs. For research
extraction, replace all three pairs with your own source documents. Update
`literature_input/inventory.csv` if choosing different papers. The default
demonstration uses the same illustrative JACS pair under `inputs/extraction/`.

From the repository root:

```bash
python Demo/03_api_data_mining/mof_api_data_mining_demo.py validate --config-dir Demo/03_api_data_mining/configs/local_papers
python Demo/03_api_data_mining/mof_api_data_mining_demo.py positive --config-dir Demo/03_api_data_mining/configs/local_papers --live
python Demo/03_api_data_mining/mof_api_data_mining_demo.py negative --config-dir Demo/03_api_data_mining/configs/local_papers --live
```

The validation report identifies the blank placeholder PDFs. Live extraction
with the local configuration stops until both blank pairs have been replaced or
removed from the selected inventory. The selected configurations preserve the same
prompts and scientific extraction logic, with outputs stored separately under
`results/examples/03_api_data_mining/local_papers/`.

The DOI inventory controls which papers are processed. The local configuration
accepts at most five rows (`max_papers` in `document_matching.json`), and negative
reconstruction selects at most five eligible papers (`quick_run_n` in
`negative_reconstruction.json`). Both extraction and reconstruction use concurrency 1. Edit these
settings for a larger run. `--config-dir` selects extraction and reconstruction configurations only;
abstract triage continues to use `configs/triage.json`.

## Inputs, prompts, and outputs

The four default JSON files in `configs/` control the models, limits, and paths. They
reference the canonical prompts under `prompts/`, including the separate system
and user templates for positive extraction and negative reconstruction. The demonstration uses the
sample documents under `inputs/extraction/` and keeps its triage subset separate from the
research datasets.

All generated files are written under
`results/examples/03_api_data_mining/`, which is excluded from Git:

- `triage/run_001/`, `triage/run_002/`, and so on: predictions and run metadata for each invocation.
- `extraction/`: the matched document manifest and input summary.
- `extraction/positive/`: extracted CSV records and the synthesis JSON store.
- `extraction/negative/`: modification plans, parent snapshots, and enumerated records.
- `local_papers/`: matched inputs and positive/negative outputs for the local PDF workflow.

Positive extraction and negative reconstruction resume from their saved artifacts. A repeated
command may skip completed documents. To rerun with different models or prompts,
set fresh output paths in the configurations and keep the negative inputs linked
to the corresponding positive output. Each triage invocation creates the next
available numbered run folder. Execution times remain in the run metadata.

Negative reconstruction also checks that every positive DOI marked `YES` belongs to the
selected document manifest. A mismatch stops the demonstration so an output from another
paper set cannot be treated as an empty negative result.

See the [triage](../../docs/triage.md),
[positive extraction](../../docs/positive_extraction.md), and
[negative reconstruction](../../docs/negative_reconstruction.md) guides for the full
methods and resume behavior.
