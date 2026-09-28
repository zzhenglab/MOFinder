# Process-detail distributions

These figures summarize the complete [positive and negative process-detail tables](../../data/processed_data/with_process_details/README.md). Panel a counts synthesis records; panel b counts unique DOIs. Missing and ambiguous process fields retain their rows. [Methods](DISTRIBUTION_METHODS.md), [counts](category_counts.csv), [coverage](field_coverage.csv), and [provenance](distribution_summary.json) accompany the figures.

## Vessel types

![Vessel types](figures/process_enrich_vessel_type.png)

## Vessel capacities

![Vessel capacities](figures/process_enrich_vessel_volume.png)

## Stirring descriptions

![Stirring descriptions](figures/process_enrich_stirring.png)

PNG, PDF, and SVG exports are in [figures](figures/), with [records-only](figures/01_synthesis_records/) and [records-plus-DOI](figures/02_records_and_DOI/) versions. The [manuscript subsection](Section_S5_process_details.md) and [captions](FIGURE_CAPTIONS.md) describe this optional control. No model-performance improvement has been assumed.

Regenerate from the repository root:

```bash
python tools/plot_process_details.py
```

See the [matched training preparation](../process_enrich_training.md) for the enriched JSONL and revised prompt.
