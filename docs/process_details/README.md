# Process-detail distributions

The figures summarize all 15,340 records from 4,568 DOIs in the [positive process-detail dataset](../../data/processed_data/with_process_details/README.md). The [plotting script](../../tools/plot_process_details.py) uses the same cleaned categories as the [process-enriched training and holdout files](../../data/processed_data_json/processed_enrich/README.md). The [Section S5 draft](Section_S5_process_details.md), [figure captions](FIGURE_CAPTIONS.md), [category counts](category_counts.csv), and [capacity histogram counts](volume_histogram_counts.csv) accompany the PNGs below.

Each figure has panel **a**, synthesis records, above panel **b**, unique DOIs. The gradients follow the primary-modulator figure: light blue to pale teal for records, and dark teal through muted teal to gray for DOIs. Colors progress through the displayed categories or capacity bins and do not encode an additional measurement. Vessel and stirring plots show category counts. Vessel-capacity plots use accepted numerical capacities and one median per DOI in panel b, with dashed arithmetic-mean lines.

Category consolidation is applied by the dataset-preparation code, so the figures, CSVs, and enriched training inputs use the same final labels. Stirring labels contain at most five words, and the pooled rare class names the reported methods: **Stirring, mixing, shaking, rotation, sonication**. Vessel labels include the shortened **PTFE-lined autoclave**. See the [counting and consolidation methods](DISTRIBUTION_METHODS.md) for category definitions and [matched training preparation](../process_enrich_training.md).

## Figures

Click any figure to open the full-resolution PNG.

PTFE-lined autoclaves are the most common vessel type, accounting for 37.4% of positive records, followed by vials at 16.8%. A paper can report several vessel types, so it may contribute to multiple DOI counts. The Not reported category also includes rare vessel types pooled during cleaning.

<a href="figures/process_enrich_vessel_type.png"><img src="figures/process_enrich_vessel_type.png" alt="Reaction-vessel category frequencies among positive records and unique DOIs" width="500"></a>

Reported vessel capacities have a median of 23 mL and an interquartile range of 16?25 mL. Numeric capacities are available for 7,271 positive records (47.4%). The DOI panel uses one median per paper, and dashed lines show the mean in each panel. Missing and ambiguous capacities are omitted.

<a href="figures/process_enrich_vessel_volume.png"><img src="figures/process_enrich_vessel_volume.png" alt="Vessel-capacity distributions among positive records and unique DOIs" width="500"></a>

The No stirring category represents explicitly static or unstirred conditions and accounts for 42.5% of positive records. Stirring information is Not reported for 25.3%. Where stated, the categories distinguish preparation-stage stirring from stirring followed by static synthesis. Rare reported methods are pooled, with their detailed descriptions retained in the audit.

<a href="figures/process_enrich_stirring.png"><img src="figures/process_enrich_stirring.png" alt="Stirring-category frequencies among positive records and unique DOIs" width="500"></a>

Categorical panels include **Not reported**; a DOI can contribute to multiple categories. Vessel **Not reported** includes selected rare known types. The [methods](DISTRIBUTION_METHODS.md) explain the consolidation and counting rules.

## Reproduce

Run from the repository root, choosing output and report folders:

```powershell
python tools/plot_process_details.py --output "../Figure 1 and Figure 4/SI figures/process enrich figures" --report-dir "../Figure 1 and Figure 4/SI figures/data/process_enrich"
```

Use `--si-section PATH` to save the short Section S5 Markdown draft and `--docx PATH` to save a Word draft with relative links to the PNGs and captions. The manuscript folder contains the three PNGs, the updated Section S5 drafts, and captions. Published PNG copies are in [`figures/`](figures/); calculation tables and provenance are kept alongside this README. Both positive and negative datasets remain available for training; figures display the positive dataset only. The distributions describe feature availability and do not establish a predictive improvement.
