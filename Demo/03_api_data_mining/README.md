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

The [literature_input/](literature_input/README.md) folder contains three DOI slots:
one synthetic article/SI pair (`10.1021/jacs.2c09756`) and two blank templates.
The default notebook uses the synthetic pair. Replace these PDFs with source
documents for research extraction.

The notebook starts with empty outputs and all live switches set to `False`.
Preview cells show inputs and requests. After a live triage run, the notebook
saves predictions, human labels, agreement, request status, and errors.

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

Configuration paths are resolved relative to the repository.

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

Rerun the preview cells after changing the configuration, inputs, or prompt.

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

The triage model, reasoning effort, token limit, and timeout are set in
[`configs/triage.json`](configs/triage.json). Adjust them before previewing requests.

Triage metadata and human labels are joined by DOI. Reference labels are used
to compare results and are excluded from model requests.

Negative reconstruction uses the positive extraction's `YES` flag and supporting
notes to select trial or failure evidence. It may produce no records when that
evidence is absent. Its outputs are combinations reconstructed from the evidence.

## Extract from three to five local papers

Place article/SI pairs in the literature input folder and list their DOIs in
`literature_input/inventory.csv`. Supply readable documents for each selected pair.

From the repository root:

```bash
python Demo/03_api_data_mining/mof_api_data_mining_demo.py validate --config-dir Demo/03_api_data_mining/configs/local_papers
python Demo/03_api_data_mining/mof_api_data_mining_demo.py positive --config-dir Demo/03_api_data_mining/configs/local_papers --live
python Demo/03_api_data_mining/mof_api_data_mining_demo.py negative --config-dir Demo/03_api_data_mining/configs/local_papers --live
```

Validation identifies blank PDFs. Replace them or remove their entries from the
inventory before live extraction. Outputs are stored under
`results/examples/03_api_data_mining/local_papers/`.

The DOI inventory controls which papers are processed. The local configuration
accepts at most five rows (`max_papers` in `document_matching.json`), and negative
reconstruction selects at most five eligible papers (`quick_run_n` in
`negative_reconstruction.json`). Both extraction and reconstruction use concurrency 1. Edit these
settings for a larger run. `--config-dir` selects extraction and reconstruction configurations only;
abstract triage continues to use `configs/triage.json`.

## Inputs, prompts, and outputs

The JSON files in `configs/` control models, limits, and paths. They reference
the prompts under `prompts/`, including separate system and user templates for
positive extraction and negative reconstruction.

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

See the [triage](../../docs/triage.md),
[positive extraction](../../docs/positive_extraction.md), and
[negative reconstruction](../../docs/negative_reconstruction.md) guides for the full
methods and resume behavior.
