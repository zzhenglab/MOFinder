# Abstract triage

The triage workflow runs from Python modules and command-line commands. Screening preserves response records, evaluation compares saved predictions with the human reference, and plotting generates figures from the same analysis. The [API demo](../Demo/03_api_demo/README.md) provides a four-abstract example with saved reference comparisons.

## Inputs

| Input | Content |
| --- | --- |
| `data/processed_data/literature_metadata.csv` | 13,773 bibliography records with DOI, title, source, keywords, and abstract |
| `benchmarks/abstract_triage/ground_truth.xlsx` | Unchanged 478-paper human annotation reference |
| `configs/abstract_triage.json` | Paths, model configurations, inference limits, and statistical settings |
| `prompts/abstract_triage.txt` | Screening criteria and prompt template |

For another collection, retain the bibliography fields `DOI`, `Article Title`, `Source Title`, `Author Keywords`, `Keywords Plus`, and `Abstract`. The reference needs `DOI` and binary `Consensus GT`; retain individual annotation columns for agreement calculations. Select CSV or XLSX input paths in the configuration, and use `max_papers` to limit a small screening run.

Every reference DOI has one nonempty abstract in the metadata export. The default `"benchmark_only": true` selects these 478 publications. Model inputs contain the title, source, keywords, and abstract. Annotation labels and comments are not included in prompts.

Three conflicting duplicate DOI groups occur outside the benchmark. Whole-corpus screening raises an explicit error until their bibliographic records are reconciled. See [`data/processed_data/literature_metadata.md`](../data/processed_data/literature_metadata.md).

## Installation and input validation

From the repository root:

```bash
python -m pip install -e ".[api,plotting]"
python -m mofinder.literature.triage validate-inputs --metadata data/processed_data/literature_metadata.csv --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
```

Expected counts are 478 scheduled publications, 293 Y and 185 N reference labels, and zero missing reference abstracts. This command makes no model requests. Input validation and statistical calculations also work with the base installation, `pip install -e .`.

## Screening

Inspect `configs/abstract_triage.json` before starting. Its `project_root` is resolved relative to the configuration file; the default value, `".."`, identifies the repository root. Input, prompt, and default output paths are resolved from that root.

The default configuration contains four model settings. Their availability depends on the API account and endpoint. Unsupported configurations are reported and are not replaced automatically. Check live model access before scheduling a full run.

Provide `OPENAI_API_KEY` as an environment variable, then run:

```bash
python -m mofinder.literature.triage screen --config configs/abstract_triage.json --output-dir results/abstract_triage/benchmark_run
```

Use a new output directory for a new run. Omitting `--output-dir` creates a distinct run directory under the configured `output_root`, which defaults to `results/abstract_triage/`. The first abstract checks each configuration before the remaining requests are scheduled. Each additional round requests new predictions.

The parser accepts only completed responses whose entire stripped answer is `Y` or `N`. Invalid, incomplete, refused, and failed responses remain visible and outside the scored denominator. Coverage must be reported with classification metrics.

### Resume an interrupted run

Continue an interrupted run with `--resume`:

```bash
python -m mofinder.literature.triage screen --config configs/abstract_triage.json --output-dir results/abstract_triage/benchmark_run --resume
```

`--resume` requires an existing `--output-dir`. It retains every saved attempt, including failed or invalid responses, and dispatches only requests without a saved record. It does not retry saved failures. Keep the same configuration and inputs when continuing a run; use a new run directory for a new experiment.

## Saved-run analysis

Analyze a saved run without making new model requests:

```bash
python -m mofinder.literature.triage analyze --run-dir results/abstract_triage/benchmark_run --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
```

The run directory should contain:

- `run_manifest.json`, including prompt and input identities;
- `responses.jsonl`, or a compatible `predictions.csv`;
- `reference_used.csv` and `reference_not_screened.csv`, when available.

Keep the run files, reference snapshots, and subsequent analysis outputs together. The workflow creates `results/` locally as needed, and its contents are excluded from Git. Saved notebook displays are not a complete prediction archive. Earlier experiments remain available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a); they are not substituted for a current run.

The loader records the current reference and any label changes before calculating comparison tables, paired tests, and figures. Reanalysis creates separate outputs so previous results remain identifiable. To name the analysis destination and make the statistical settings explicit:

```bash
python -m mofinder.literature.triage analyze --run-dir results/abstract_triage/benchmark_run --ground-truth benchmarks/abstract_triage/ground_truth.xlsx --output-dir results/local/benchmark_analysis --bootstraps 50000 --seed 42
```

Add `--no-plots` to produce the statistical outputs without figure generation. This mode does not require the plotting dependency group. Complete prediction records for the consolidated workflow are not included yet; reproducing its model-performance tables requires saved records from a completed run.

The analysis command defaults to 50,000 bootstrap draws and seed 42. For a run created with other statistical settings, pass the values recorded in its manifest using `--bootstraps` and `--seed`. Every analysis records the settings actually used.

### Statistical methods

Per-round estimates use 95% confidence intervals:

| Metrics | Interval method |
| --- | --- |
| Accuracy, precision, recall, specificity, and negative predictive value | Wilson interval |
| F1, balanced accuracy, and Matthews correlation coefficient | Publication-bootstrap percentile interval |

Across-round summaries report the mean and sample standard deviation (`ddof=1`) of the round estimates. Repeated predictions are not pooled as independent publications. Single-letter Y/N outputs provide no continuous prediction scores, so this workflow does not calculate ROC curves, AUC, or probability calibration.

## Human agreement

The annotation calculations can be run locally:

```bash
python -m mofinder.literature.triage human-agreement --metadata data/processed_data/literature_metadata.csv --ground-truth benchmarks/abstract_triage/ground_truth.xlsx --output-dir results/local/human_agreement
```

The output directory must be new. The default uses 50,000 publication-bootstrap draws and seed 42. Ambiguous `Y/N` ratings are not treated as binary votes. Pairwise agreement uses available binary pairs, Fleiss' kappa uses complete four-binary-rating rows, and nominal Krippendorff's alpha uses available binary ratings. The human consensus label remains authoritative for model scoring. The default bootstrap calculation can take several minutes.

Human annotation notes informed prompt refinement, and the same reference is used for evaluation.

## Implementation

| Module | Responsibility |
| --- | --- |
| `src/mofinder/literature/triage.py` | Input handling, configuration, model requests, response records, resume, and command-line interface |
| `src/mofinder/evaluation/triage.py` | Saved-run loading, performance statistics, human agreement, and comparison tables |
| `src/mofinder/plotting/triage.py` | Figures and their associated source tables |

Shared statistical functions remain importable from the literature module for compatibility. Prompt text and model defaults are stored in named files. Complete prediction records belong in the run archive; notebook outputs are not a substitute for those records.
