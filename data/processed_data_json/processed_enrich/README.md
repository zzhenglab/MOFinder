# Process-enriched matched control

[Download the training and holdout ZIP](https://github.com/zzhenglab/MOFinder/raw/refs/heads/main/data/processed_data_json/processed_enrich/process_enrich_train_holdout.zip). It contains both JSONL files and a standalone README comparing the baseline and enriched system and user prompts, with row counts, field definitions, and file hashes. The [prompt comparison](README_training_package.md) can also be read online. Rebuild the package from the repository root with `python tools/package_process_enrich.py`.

[`train_process_enrich.jsonl`](train_process_enrich.jsonl) (23,528 rows) and [`holdout_process_enrich.jsonl`](holdout_process_enrich.jsonl) (2,595 rows) preserve the standard split, record order, labels, and eight original inputs. They add only `vessel_type`, `vessel_volume_mL` (capacity in mL), and `agitation` to each user prompt. The system prompt is identical to each original prompt except for these three names appended to its input list. Missing values are `Not reported`; unresolved capacities are `Ambiguous`.

The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. `jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.

Final categories are shared with the cleaned CSVs. The nine categories in `agitation` have two-to-five-word labels. `Stirred before static synthesis` requires an explicit stirring-then-static sequence. `Stirred before main synthesis` describes preparatory stirring before the main synthesis step and leaves later conditions unspecified. `Stirring reported` does not establish continuous stirring during the reaction. Sonication remains separate; `Shaking, vortexing, rotation and mixing` groups related mechanical methods, including homogenization. `No stirring` denotes explicitly static or unstirred conditions. Unspecified vessel types and vessel classes with fewer than 10 positive-reference records map to `Not reported`. The same mapping and source-review rules apply to both labels and splits. Original descriptions remain in the cleaned CSVs' raw columns, outside model input. See the [nine-category counts](../../processed_data/with_process_details/README.md#normalization), [normalization rules](../../../src/mofinder/curation/process_stirring.py), and [source-review registry](../../../src/mofinder/curation/agitation_source_reviews.py).

Negative process annotations can be inherited from successful recipes. The existing split shares 864 DOIs across training and holdout. Use this dataset as a matched control; do not interpret it as causal process validation. No manual benchmark process details are invented and no model was trained.

The release [independent verification](independent_verification.json) compares every row directly with the same row in the archived split, without sorting. Both splits have zero mismatches in the original values, JSON types, key order, labels, metadata, or prompt text outside the input-list expansion.

Repeat the independent comparison from the repository root with `python tools/audit_process_enrich_alignment.py`. Add `--output results/local/process_alignment.json` to save a fresh report.

Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich` using a new output directory. See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.

The canonical [process-enriched system prompt](../../../prompts/training/reaction_prediction_process_enrich.txt) is stored in `prompts/training/`; no prompt copy is kept in this dataset folder.

## Positive-dataset process distributions

Click any figure to open the full-resolution PNG.

These figures describe all 15,340 positive tabular records from 4,568 DOIs, before model-training exclusions. Each figure shows synthesis records in panel **a** and unique DOIs in panel **b**, using the gradient style of the primary-modulator figure. The [Section S5 draft](../../../docs/process_details/Section_S5_process_details.md), [captions](../../../docs/process_details/FIGURE_CAPTIONS.md), [calculation tables and gallery](../../../docs/process_details/README.md), and [counting methods](../../../docs/process_details/DISTRIBUTION_METHODS.md) provide the accompanying material.

PTFE-lined autoclaves are the most common vessel type, accounting for 37.4% of positive records, followed by vials at 16.8%. A paper can report several vessel types, so it may contribute to multiple DOI counts. The Not reported category also includes rare vessel types pooled during cleaning.

<a href="../../../docs/process_details/figures/process_enrich_vessel_type.png"><img src="../../../docs/process_details/figures/process_enrich_vessel_type.png" alt="Reaction-vessel category frequencies among positive records and unique DOIs" width="500"></a>

Reported vessel capacities have a median of 23 mL and an interquartile range of 16–25 mL. Numeric capacities are available for 7,271 positive records (47.4%). The DOI panel uses one median per paper, and dashed lines show the mean in each panel. Missing and ambiguous capacities are omitted.

<a href="../../../docs/process_details/figures/process_enrich_vessel_volume.png"><img src="../../../docs/process_details/figures/process_enrich_vessel_volume.png" alt="Vessel-capacity distributions among positive records and unique DOIs" width="500"></a>

The No stirring category represents explicitly static or unstirred conditions and accounts for 6,522 positive records (42.5%). The field is Not reported for 3,886 records (25.3%). Stirred before static synthesis contains 1,759 records (11.5%), Stirred before main synthesis contains 495 (3.2%), and Stirring reported contains 2,190 (14.3%). Preparatory stirring occurs during initial mixing or dissolution before the main synthesis step; it does not establish static conditions or continued stirring afterward. Sonication remains separate, while Shaking, vortexing, rotation and mixing contains 65 records (0.4%). The [source-review registry](../../../src/mofinder/curation/agitation_source_reviews.py) preserves reviewed methods and timing.

<a href="../../../docs/process_details/figures/process_enrich_agitation.png"><img src="../../../docs/process_details/figures/process_enrich_agitation.png" alt="Agitation-category frequencies among positive records and unique DOIs" width="500"></a>


