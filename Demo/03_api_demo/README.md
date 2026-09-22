# API demo: abstract triage and data mining

This demo runs literature triage, positive synthesis extraction, and negative
condition reconstruction through the same Python modules used in the main
workflow. Model calls require an API key and access to the configured models.

Start with [api_demo.ipynb](api_demo.ipynb). It displays four complete abstracts,
previews the exact requests, and compares GPT predictions with human labels.
Continue in the same notebook to extract positive synthesis records from the
included article/SI pair and reconstruct negative conditions from the extracted
evidence. The corresponding terminal commands use [run_demo.py](run_demo.py).

The two offline demos remain in [`Demo/01_data_cleaning`](../01_data_cleaning/README.md)
and [`Demo/02_json_preparation`](../02_json_preparation/README.md).

## Install and check the inputs

From the repository root:

```bash
python -m pip install -e ".[mining,notebook]"
python Demo/03_api_demo/run_demo.py
jupyter lab Demo/03_api_demo/api_demo.ipynb
```

The default command makes no API requests. It checks the triage inputs, matches
the sample article/SI pair, and reads both document texts. Before positive mining
has run, the negative-stage report lists the positive extraction CSV as a missing
input. That CSV and its synthesis JSON files are created by the positive stage.

Commands also work from this folder using `python run_demo.py`, or from another
directory with an absolute path to the script. Configuration paths are resolved
relative to the repository, independently of the current working directory.

To check only the triage inputs, run `python Demo/03_api_demo/run_demo.py triage`.
The included tables contain 12 abstracts and reference labels (9 Y and 3 N).
The configuration schedules the first four abstracts (3 Y and 1 N). The validation
summary counts the eight unscheduled references under `missing_reference_publications`;
their abstracts are present, but outside the configured four-paper subset.

## Run the API stages

The notebook has three switches, each initially `False`: `RUN_TRIAGE`,
`RUN_POSITIVE_MINING`, and `RUN_NEGATIVE_MINING`. Enable the desired stage and
run its cell. Run positive mining before negative mining. Use an existing
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
python Demo/03_api_demo/run_demo.py triage --live
python Demo/03_api_demo/run_demo.py positive --live
python Demo/03_api_demo/run_demo.py negative --live
```

Run positive mining before negative mining. The last command mines modification
plans and then enumerates their saved options locally. To inspect eligible
documents without model calls, run the negative command without `--live` after
positive extraction has finished.

| Example | Input and size | Default configuration |
| --- | --- | --- |
| Literature triage | Four abstracts selected from the 12-paper subset in `inputs/` | GPT-4o; one round; one request at a time |
| Positive data mining | One illustrative article/SI pair in [`inputs/mining/`](inputs/mining/README.md) | GPT-5; one document at a time |
| Negative data mining | Positive CSV, synthesis JSON files, and the same article/SI pair | GPT-5; medium reasoning effort; at most one eligible document |
| Local paper extraction | Three to five article/SI pairs in `literature_input/main/` and `literature_input/si/` | Separate `configs/local_papers/`; one request at a time |

Triage metadata and human labels are joined by DOI. Reference labels are used
only to compare results and are never sent to the model. The notebook shows each
prediction's request status and any error, so failed requests remain visible.
These small inputs demonstrate the workflow and do not form a performance benchmark.

The mining PDFs contain illustrative synthesis conditions. Negative mining uses
the positive extraction's `YES` flag and supporting notes to select trial or
failure evidence. Depending on the extracted evidence, it may produce no eligible
documents or no enumerated records. Enumerated combinations are reconstructed
conditions and are not individually verified experimental failures. The demo
uses no corpus-specific manual enumeration corrections.

## Extract from three to five local papers

The [literature input folder](literature_input/README.md) contains three pairs of
DOI-named PDF templates and a matching inventory. Replace the main article
templates in `literature_input/main/` and SI templates in `literature_input/si/`
with the real PDFs. Update `literature_input/inventory.csv` if choosing different
papers. The templates contain no published text; the original illustrative
article/SI pair under `Demo/03_api_demo/inputs/mining/` remains available for the default demo.

From the repository root:

```bash
python Demo/03_api_demo/run_demo.py validate --config-dir Demo/03_api_demo/configs/local_papers
python Demo/03_api_demo/run_demo.py positive --config-dir Demo/03_api_demo/configs/local_papers --live
python Demo/03_api_demo/run_demo.py negative --config-dir Demo/03_api_demo/configs/local_papers --live
```

The validation report identifies any placeholder PDFs. Live extraction stops
until they have been replaced. The selected configurations preserve the same
prompts and scientific extraction logic, with outputs stored separately under
`results/examples/03_api_demo/local_papers/`.

The DOI inventory controls which papers are processed. The local configuration
accepts at most five rows (`max_papers` in `document_matching.json`), and negative
mining selects at most five eligible papers (`quick_run_n` in
`negative_mining.json`). Both extraction stages use concurrency 1. Edit these
settings for a larger run. `--config-dir` selects mining configurations only;
literature triage continues to use `configs/triage.json`.

## Inputs, prompts, and outputs

The four default JSON files in `configs/` control the models, limits, and paths. They
reference the canonical prompts under `prompts/`, including the separate system
and user templates for positive and negative extraction. The demo uses the
sample documents under `inputs/mining/` and keeps its triage subset separate from the
research datasets.

All generated files are written under
`results/examples/03_api_demo/`, which is excluded from Git:

- `triage/`: timestamped runs containing predictions and run metadata.
- `mining/`: the matched document manifest and input summary.
- `mining/positive/`: extracted CSV records and the synthesis JSON store.
- `mining/negative/`: modification plans, parent snapshots, and enumerated records.
- `local_papers/`: matched inputs and positive/negative outputs for the local PDF workflow.

Positive and negative extraction resume from their saved artifacts. A repeated
command may skip completed documents. To rerun with different models or prompts,
set fresh output paths in the configurations and keep the negative inputs linked
to the corresponding positive output. Each triage invocation creates a new run.

Negative mining also checks that every positive DOI marked `YES` belongs to the
selected document manifest. A mismatch stops the demo so an output from another
paper set cannot be treated as an empty negative result.

See the [triage](../../docs/triage.md),
[positive extraction](../../docs/positive_extraction.md), and
[negative extraction](../../docs/negative_extraction.md) guides for the full
methods and resume behavior.
