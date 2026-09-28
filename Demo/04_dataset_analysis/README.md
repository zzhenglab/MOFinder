# Dataset analysis demo

Open [dataset_analysis.ipynb](dataset_analysis.ipynb) for literature coverage, pairwise synthesis conditions, metals, linkers, solvents, modulators, topology, BET, TGA, stability, and training/test t-SNE. Composition and property plots show synthesis records above DOI summaries.

The notebook uses the included positive and negative datasets and the final training/test records. Shared [plotting code](../../src/mofinder/plotting/) reproduces all figures without API access.

From the repository root:

```bash
python -m pip install -e ".[plotting,notebook]"
jupyter lab Demo/04_dataset_analysis/dataset_analysis.ipynb
```

Choose **Run All** to regenerate the displayed figures and PNG exports in `results/dataset_analysis/`. The terminal equivalents are:

```bash
python -m mofinder.plotting.dataset_analysis
python -m mofinder.plotting.condition_coverage
python -m mofinder.plotting.split_embedding
python -m mofinder.plotting.literature_triage_figures --source docs/triage_figures/publisher_source_records.csv --mapping docs/triage_figures/publisher_name_mapping.csv --output-dir results/dataset_analysis/literature
```

The t-SNE command draws the included coordinates; add `--refit` to recompute them. See the [figure gallery](../../docs/dataset_analysis/README.md) for counting rules and plotting tables.
