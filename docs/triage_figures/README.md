# Literature coverage

![Publisher coverage before abstract triage](Figure_D11_publisher_coverage.png)

Figure D11. Publisher coverage in the literature corpus, grouped by publication period before abstract triage.

Bars count 13,773 bibliography records, including duplicate DOI rows, across five publisher groups and three publication periods. Percentages use the full bibliography as the denominator. The data contain 13,770 unique nonempty DOIs.

[Publisher/year records](publisher_source_records.csv), [publisher-name mappings](publisher_name_mapping.csv), [period counts](publisher_period_counts.csv), and [input checksums](provenance.json) are included. The [executed notebook](../../Demo/05_literature_triage_figures/literature_triage_figures.ipynb) shows the calculations and figure output.

## Reproduce

From the repository root:

```bash
python -m pip install -e ".[plotting,notebook]"
python -m mofinder.plotting.literature_triage_figures --source docs/triage_figures/publisher_source_records.csv --mapping docs/triage_figures/publisher_name_mapping.csv --output-dir docs/triage_figures
```

This writes a 6-inch, 600 dpi PNG, PDF, SVG, and summary CSV using the shared [plotting module](../../src/mofinder/plotting/literature_triage_figures.py).
