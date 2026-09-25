# Experiment configurations

`abstract_triage.json` records the settings used by the Python screening command. Each run writes its effective settings and input hashes to a manifest.

| Setting | Purpose |
| --- | --- |
| `project_root` | Base directory, resolved relative to the configuration file; `".."` selects the repository root |
| `input_file`, `input_sheet` | Bibliographic table and optional worksheet |
| `ground_truth_file` | Human annotation reference |
| `prompt_file` | Screening prompt template |
| `output_root` | Default parent directory for new screening runs |
| `models` | Named model and reasoning settings |
| `benchmark_only`, `max_papers` | Publication selection |
| `n_rounds` | Number of independent prediction rounds |
| `max_concurrent`, `max_output_tokens`, `request_timeout`, `save_every` | Request scheduling and output limits |
| `bootstraps`, `statistics_seed` | Default statistical settings |

Input, prompt, and default output paths are resolved from `project_root`. Run screening with:

```bash
python -m mofinder.literature.triage screen --config configs/abstract_triage.json
```

Store personal configurations in `configs/local/`, which is excluded from Git. When copying a configuration from `configs/` directly into `configs/local/`, change `project_root` from `".."` to `"../.."` so its paths still resolve from the repository root. Use a fresh output directory when changing inputs, prompts, or model settings.

An explicit `--output-dir` selects a run directory. Add `--resume` only when continuing that existing run with the same configuration and inputs. Resume retains recorded attempts, including failures, and schedules only requests without a saved record. The [triage guide](../docs/triage.md) describes saved-run analysis and its statistical overrides.

Configurations for the downstream stages are listed below. Training settings are described in the [HPC training guide](../docs/training_hpc.md). The historical numbered scripts and their settings are available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a).

## Literature retrieval settings

`literature_retrieval.json` defines the article and SI inventories, neutral publisher profiles,
image directory, local calibration paths, and browser timing settings. The two
sections retain their original retry and journal-failure thresholds. Calibration
coordinates and remembered inventory paths are written locally under
`results/literature_retrieval/` when the desktop tools are used.

Run `python tools/literature_retrieval/fetch_papers.py --validate` or
`python tools/literature_retrieval/fetch_si.py --validate` to inspect the configured inputs
without opening a browser. See [literature-retrieval](../docs/literature_retrieval.md) for setup.

## Synthesis records and dataset preparation

| Configuration | Purpose |
| --- | --- |
| `document_matching.json` | Match local article and SI files against the selected inventory |
| `example_document_matching.json` | Match the included demonstration PDFs |
| `example_positive_extraction.json`, `example_negative_reconstruction.json` | Run positive extraction and negative reconstruction on the included demonstration pair, saving separate example results |
| `positive_extraction.json` | Model, document paths, prompts, concurrency, and saved positive outputs |
| `negative_reconstruction.json` | Negative reconstruction: planning and enumeration inputs and outputs |
| `negative_corrections.json` | Explicit DOI-specific enumeration rules retained from the notebook |
| `curation.json` | Positive and negative curation paths and required molecular-weight lookup |
| `dataset_preparation.json` | Prepare final JSONL and split records from the included processed positive and negative CSVs and publication years |
| `dataset_preparation_from_curation.json` | Prepare a new dataset from generated positive and negative curation outputs |
| `dataset_preparation_corrected.json` | Prepare a separate dataset using the linker-corrected processed negative CSV |
| `dataset_forced_questions.json` | Fixed benchmark conditions used to select holdout clusters |

Paths are resolved from `project_root`. The default dataset configuration reads `data/processed_data/` and writes to `results/datasets/conditions/`. The curation-output and linker-corrected alternatives write to `results/datasets/curated_conditions/` and `results/datasets/corrected_conditions/`, respectively. Bundled final JSONL and split records are together in `data/final_json/`. Use a separate local configuration for a small live extraction run. The [workflow guide](../docs/workflow.md) explains stage order and required inputs.

## Model evaluation settings

| Configuration | Purpose |
| --- | --- |
| `holdout_evaluation.json` | Final holdout JSONL, model IDs, concurrency, seed, retry settings, and output names |
| `quest_evaluation.json` | Question definitions, classifier prompt, model groups, repeated rounds, and reasoning settings |

Model credentials are read from `OPENAI_API_KEY`; the API demo can request the key through a hidden prompt when a live run is enabled. Human analysis uses the anonymous files under `benchmarks/mof_quest/` and requires no credentials. See [evaluation](../docs/evaluation.md).
