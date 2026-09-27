# Dataset analysis demo

Open [dataset_analysis.ipynb](dataset_analysis.ipynb) for ten executed figures: pairwise synthesis conditions, metals, linkers, solvents, modulators, topology, BET, TGA, stability, and training/test t-SNE. Figures D2–D9 show synthesis records in panel a above unique DOI counts in panel b.

The notebook uses the included positive and negative datasets and the final training/test records. Shared [plotting code](../../src/mofinder/plotting/) reproduces all figures without API access.

From the repository root:

```bash
python -m pip install -e ".[plotting,notebook]"
jupyter lab Demo/04_dataset_analysis/dataset_analysis.ipynb
```

Choose **Run All** to regenerate the displayed outputs and eighteen PNGs in `results/dataset_analysis/`. The terminal equivalents are:

```bash
python -m mofinder.plotting.dataset_analysis
python -m mofinder.plotting.condition_coverage
python -m mofinder.plotting.split_embedding
```

The t-SNE command draws the included coordinates; add `--refit` to recompute them. See the [figure gallery](../../docs/dataset_analysis/README.md) for counting rules and [captions](../../docs/dataset_analysis/CAPTIONS.md).
