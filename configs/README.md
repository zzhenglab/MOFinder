# Experiment configurations

`abstract_triage.json` records the settings shared by the Python screening command and the optional notebook. Each run writes its effective settings and input hashes to a manifest.

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

## Mining and dataset settings

| Configuration | Purpose |
| --- | --- |
| `document_matching.json` | Match local article and SI files against the selected inventory |
| `example_document_matching.json` | Match the included demonstration PDFs |
| `example_positive_extraction.json`, `example_negative_extraction.json` | Mine only the included demonstration pair into separate example results |
| `positive_extraction.json` | Model, document paths, prompts, concurrency, and saved positive outputs |
| `negative_extraction.json` | Negative planning and enumeration inputs and outputs |
| `negative_corrections.json` | Explicit DOI-specific enumeration rules retained from the notebook |
| `curation.json` | Positive/negative cleaning paths and required molecular-weight lookup |
| `dataset_preparation.json` | Stage-6 inputs, publication years, split settings, and output provenance |
| `dataset_preparation_archived.json` | Reproduce preparation from the archived cleaned snapshots |
| `dataset_forced_questions.json` | Fixed benchmark conditions used to select holdout clusters |

Paths are resolved from `project_root`. Defaults preserve the source notebook settings; use a separate local configuration for a small live extraction run. The [workflow guide](../docs/workflow.md) explains stage order and required inputs.

## Evaluation settings

| Configuration | Purpose |
| --- | --- |
| `holdout_evaluation.json` | Archived holdout JSONL, model IDs, concurrency, seed, retry settings, and output names |
| `quest_evaluation.json` | Question definitions, classifier prompt, model groups, repeated rounds, and reasoning settings |

Model credentials are read from `OPENAI_API_KEY`; notebooks can request the key through a hidden prompt when a live run is enabled. Human analysis uses the anonymous files under `benchmarks/mof_quest/` and requires no credentials. See [evaluation](../docs/evaluation.md).
