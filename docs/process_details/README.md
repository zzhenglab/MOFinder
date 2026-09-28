# Process-detail distributions

The [plotting script](../../tools/plot_process_details.py) summarizes the complete [positive process-detail dataset](../../data/processed_data/with_process_details/README.md). Figure assets are generated locally and are not included in this repository. The script writes exactly three PNGs to an explicitly supplied output folder; calculation tables, captions, provenance, and the short Section S5 draft are written to a separate report folder.

Each figure has panel **a**, synthesis records, above panel **b**, unique DOIs. The colors match the positive-dataset temperature/time figures: muted teal for records and light blue for DOIs. Vessel and stirring plots show the final dataset categories and their counts. Vessel-capacity plots use accepted numerical capacities and one median per DOI in panel b, with dashed arithmetic-mean lines.

Category consolidation is applied by the dataset-preparation code, so the figures, CSVs, and enriched training inputs use the same final labels. Stirring labels contain at most five words, and the pooled rare class names the reported methods: **Stirring, mixing, shaking, rotation, sonication**. Vessel labels include the shortened **PTFE-lined autoclave**. See the [counting and consolidation methods](DISTRIBUTION_METHODS.md) for category definitions and [matched training preparation](../process_enrich_training.md).

Run from the repository root, choosing local output and report folders:

```powershell
python tools/plot_process_details.py --output "../Figure 1 and Figure 4/SI figures/process enrich figures" --report-dir "../Figure 1 and Figure 4/SI figures/data/process_enrich"
```

Use `--si-section PATH` to save a local copy of the short Section S5 Markdown draft and `--docx PATH` to save a Word draft with relative links to the local PNGs and captions. Both positive and negative datasets remain available for training; figures display the positive dataset only. The distributions describe feature availability and do not establish a predictive improvement.
