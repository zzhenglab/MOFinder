# Additional demonstrations requiring API access

These examples run literature triage, positive synthesis extraction, and negative
condition reconstruction through the same Python modules used in the main
workflow. Model calls require an API key and access to the configured models.

## Install and check the inputs

From the repository root:

```bash
python -m pip install -e ".[mining,notebook]"
python Demo/additional_demo_api_needed/run_demo.py
```

The default command makes no API requests. It checks the triage inputs, matches
the sample article/SI pair, and reads both document texts. Before positive mining
has run, the negative-stage report lists the positive extraction CSV as a missing
input. That CSV and its synthesis JSON files are created by the positive stage.

Commands also work from this folder using `python run_demo.py`, or from another
directory with an absolute path to the script. Configuration paths are resolved
relative to the repository, independently of the current working directory.

## Run the examples

Enable model requests explicitly with `--live`. An existing `OPENAI_API_KEY`
environment variable is reused; otherwise, the script requests the key through
a hidden prompt. The key is not written to the configuration files.

```bash
python Demo/additional_demo_api_needed/run_demo.py triage --live
python Demo/additional_demo_api_needed/run_demo.py positive --live
python Demo/additional_demo_api_needed/run_demo.py negative --live
```

Run positive mining before negative mining. The last command mines modification
plans and then enumerates their saved options locally. To inspect eligible
documents without model calls, run the negative command without `--live` after
positive extraction has finished.

| Example | Input and size | Default configuration |
| --- | --- | --- |
| Literature triage | Three abstracts and reference labels in `inputs/` | GPT-4o; one round; one request at a time |
| Positive data mining | One article/SI pair in `Demo/05_data_mining/` | GPT-5; one document at a time |
| Negative data mining | Positive CSV, synthesis JSON files, and the same article/SI pair | GPT-5; medium reasoning effort; at most one eligible document |
| Local paper extraction | Three to five article/SI pairs in `literature_input/main/` and `literature_input/si/` | Separate `configs/local_papers/`; one request at a time |

The triage inputs select the first two Y papers and the first N paper from
`Demo/03_abstract_triage/ground_truth.csv`, with metadata joined by DOI. The validation
reports three scheduled papers, two Y labels, one N label, and no missing
reference abstracts. Reference labels are not sent to the model. These small
inputs demonstrate the workflow and do not form a new performance benchmark.

The mining PDFs contain illustrative synthesis conditions. Negative mining uses
the positive extraction's `YES` flag and supporting notes to select trial or
failure evidence. Depending on the extracted evidence, it may produce no eligible
documents or no enumerated records. Enumerated combinations are reconstructed
conditions and are not individually verified experimental failures. The demo
uses no corpus-specific manual enumeration corrections.

For an interactive walkthrough, open [api_demo.ipynb](api_demo.ipynb). Its three
live switches default to `False`; enable each desired stage and provide the API
key when prompted.

## Extract from three to five local papers

The [literature input folder](literature_input/README.md) contains three pairs of
DOI-named PDF templates and a matching inventory. Replace the main article
templates in `literature_input/main/` and SI templates in `literature_input/si/`
with the real PDFs. Update `literature_input/inventory.csv` if choosing different
papers. The templates contain no published text; the original illustrative
article/SI pair under `Demo/05_data_mining/` remains available for the default demo.

From the repository root:

```bash
python Demo/additional_demo_api_needed/run_demo.py validate --config-dir Demo/additional_demo_api_needed/configs/local_papers
python Demo/additional_demo_api_needed/run_demo.py positive --config-dir Demo/additional_demo_api_needed/configs/local_papers --live
python Demo/additional_demo_api_needed/run_demo.py negative --config-dir Demo/additional_demo_api_needed/configs/local_papers --live
```

The validation report identifies any placeholder PDFs. Live extraction stops
until they have been replaced. The selected configurations preserve the same
prompts and scientific extraction logic, with outputs stored separately under
`results/examples/additional_demo_api_needed/local_papers/`.

The DOI inventory controls which papers are processed. The local configuration
accepts at most five rows (`max_papers` in `document_matching.json`), and negative
mining selects at most five eligible papers (`quick_run_n` in
`negative_mining.json`). Both extraction stages use concurrency 1. Edit these
settings for a larger run. `--config-dir` selects mining configurations only;
literature triage continues to use `configs/triage.json`.

## Inputs, prompts, and outputs

The four default JSON files in `configs/` control the models, limits, and paths. They
reference the canonical prompts under `prompts/`, including the separate system
and user templates for positive and negative extraction. The examples reuse the
repository's sample documents and keep their triage subset separate from the
research datasets.

All generated files are written under
`results/examples/additional_demo_api_needed/`, which is excluded from Git:

- `triage/`: timestamped runs containing predictions and run metadata.
- `mining/`: the matched document manifest and input summary.
- `mining/positive/`: extracted CSV records and the synthesis JSON store.
- `mining/negative/`: modification plans, parent snapshots, and enumerated records.
- `local_papers/`: matched inputs and positive/negative outputs for the local PDF workflow.

Positive and negative extraction resume from their saved artifacts. A repeated
command may skip completed documents. To rerun with different models or prompts,
set fresh output paths in the configurations and keep the negative inputs linked
to the corresponding positive output. Each triage invocation creates a new run.

See the [triage](../../docs/triage.md),
[positive extraction](../../docs/positive_extraction.md), and
[negative extraction](../../docs/negative_extraction.md) guides for the full
methods and resume behavior.
