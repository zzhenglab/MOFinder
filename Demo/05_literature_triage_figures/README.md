# Literature coverage demo

Open [literature_triage_figures.ipynb](literature_triage_figures.ipynb) for the executed publisher-coverage plot, Figure D11. The notebook counts bibliography records before abstract triage, including duplicate DOI rows, and uses the included [publisher/year data](../../docs/triage_figures/README.md).

From the repository root:

```bash
python -m pip install -e ".[plotting,notebook]"
jupyter lab Demo/05_literature_triage_figures/literature_triage_figures.ipynb
```

Run all cells to redraw the figure without API access. The notebook shares its [plotting implementation](../../src/mofinder/plotting/literature_triage_figures.py) with the command-line workflow and writes outputs to `docs/triage_figures/`.
