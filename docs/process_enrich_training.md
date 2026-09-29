# Eleven-field process-enriched control

This control adds `vessel_type`, `vessel_volume_mL`, and `agitation` to the original eight reaction-condition inputs in each user prompt. It retains the archived train/holdout split, row order, labels, and all eight original input values. The primary dataset and its preparation pipeline remain the baseline.

The system prompt changes only the original input list: `temperature_C, and time_h.` becomes `temperature_C, time_h, vessel_type, vessel_volume_mL, and agitation.` All other prompt text, including whitespace and the output instructions, is identical. The preparation code rejects any additional prompt changes. Run `python tools/audit_process_enrich_alignment.py` for an independent, row-by-row comparison of both released splits; the saved [verification report](../data/processed_data_json/processed_enrich_11field/independent_verification.json) records zero mismatches.

The cleaned source files are `data/processed_data/with_process_details/Process_detail_positive.csv` and `Process_detail_negative.csv`. They retain all 15,340 positive and 15,063 negative source rows. Missing process information is `Not reported`; unresolved capacities are `Ambiguous`. Agitation descriptions that do not uniquely specify a supported state are encoded as `Not reported` according to the normalization rules. Vessel volume is the nominal vessel capacity in mL; it is not inferred from solvent volume. Original `vessel_type` and `stirring` annotations remain unchanged as `vessel_type_raw` and `stirring_raw` in the derived tables.

Category normalization is shared by CSVs, model JSONL, and figures. The nine categories in `agitation` have two-to-five-word labels. `Stirred before static synthesis` requires an explicit stirring-then-static sequence. `Stirred before main synthesis` describes initial mixing or dissolution before the main heating, aging, or reaction step; subsequent stirring or static conditions are unspecified. `Stirring reported` does not imply continuous stirring throughout synthesis; specific reported timing remains in the original descriptions and source-review rules. Sonication has separate before-static, before-main-synthesis, and reported categories. `Shaking, vortexing, rotation and mixing` groups related mechanical methods, including homogenization, with individual methods and stages preserved in the original descriptions and source-review rules. `No stirring` denotes explicitly static or unstirred conditions. The fixed mapping applies before split preparation and uses no agitation-frequency threshold. See the [nine-category counts](../data/processed_data/with_process_details/README.md#normalization).

The [source-review registry](../src/mofinder/curation/agitation_source_reviews.py) documents 17 description-specific clarifications affecting 50 positive and eight negative records. These include nine positive records whose ultrasonic wording supports `Sonicated before main synthesis`, and 17 records whose source protocols place stirring before the main synthesis step. Reviews preserve the original extracted strings and apply only to exact DOI/normalized-description matches.

Vessel categories with fewer than 10 positive-reference records and unspecified vessel types map to `Not reported`. Material-only labels are `Glass vessel`, `Polymer vessel`, and `Metal vessel`; the shortened `PTFE-lined autoclave` retains its existing membership. The same vessel mapping, agitation rules, and reviewed source interpretations are applied to positive and negative records before either split is prepared. `Not reported` for vessels includes a small number of rare reported types and is therefore not a pure missingness flag. The [normalization functions](../src/mofinder/curation/process_stirring.py) return detailed classifications and rule identifiers, which are excluded from model input.

## Prepare the paired JSONL files

From the repository root, with the package and its `datasets` dependencies installed:

```powershell
python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json --output results/datasets/process_enrich
```

Paths in the config resolve relative to `project_root`, which resolves relative to the config file. Absolute paths are also accepted. The optional `--output` override resolves relative to the current working directory and leaves the config unchanged. Preparation refuses to overwrite an existing directory, so choose a fresh output path for each reproduction. Without an override, the config targets `data/processed_data_json/processed_enrich_11field/`, which already contains the supplied release:

| File | Content |
| --- | --- |
| `train_process_enrich.jsonl` | 23,528 rows: 11,968 P and 11,560 N |
| `holdout_process_enrich.jsonl` | 2,595 rows: 1,320 P and 1,275 N |
| `train_sources.csv`, `holdout_sources.csv` | Source mapping for each JSONL row, excluded from model input |
| `class_map.json` | Unchanged P = success, N = failure label meaning |
| `manifest.json` | Source and output hashes, counts, process distributions by label, and alignment checks |

The system prompt is maintained separately at [prompts/training/reaction_prediction_process_enrich_11field.txt](../prompts/training/reaction_prediction_process_enrich_11field.txt) and embedded unchanged in every enriched example.

The source CSVs keep the full cohort; the JSONL files retain the standard preparation's existing filtered cohort. No new filtering, splitting, deduplication, or P/N balancing is performed. Each archived JSONL example is joined through its canonical eight-field condition key and P/N label to exactly one archived split assignment. That assignment identifies the source row. Preparation verifies source chemistry and DOI, rejects ambiguous matches and repeated or missing source rows, and checks that train/holdout condition and chemistry-cluster sets remain disjoint. It copies the baseline example and changes only its system prompt and the addition of the three process input fields.

There are exactly eleven model inputs. DOI, source index, raw annotation, rationale, modification notes, success flags, product properties, and split metadata remain in source tables or mapping files. They are never injected into the user message.

## Optional local/HPC bundle preparation

The ordinary validator still requires exactly eight fields. The explicit `process_enrich` profile accepts exactly eleven and validates the normalized process values and system prompt. This command prepares a portable training bundle; it does not train a model:

```powershell
python -m mofinder.training.prepare `
  --train data/processed_data_json/processed_enrich_11field/train_process_enrich.jsonl `
  --holdout data/processed_data_json/processed_enrich_11field/holdout_process_enrich.jsonl `
  --feature-profile process_enrich `
  --manual-process-policy missing_control `
  --output results/local/hpc_training_process_enrich

python -m mofinder.training.prepare --validate-bundle results/local/hpc_training_process_enrich
```

The current runner also evaluates the existing 22 manual benchmark questions. Those questions have no curated process annotations. For that reason, bundle preparation requires an explicit `--manual-process-policy missing_control`: it marks all three added benchmark values `Not reported` and records this limitation in the manifest. This benchmark then measures predictions with process information unavailable; it cannot demonstrate benefit from real process annotations. The standalone enriched train/holdout release includes no invented benchmark process data. The ordinary baseline bundle behavior is unchanged.

The process prompt is `prompts/training/reaction_prediction_process_enrich_11field.txt`. Its hash and exact text are checked during bundle preparation and validation. The same full prompt is used for training and inference. The existing tokenizer rejects overlength inputs instead of truncating instructions or chemistry; if its preflight requests a larger `max_length`, apply the same sufficient limit to both comparison arms before training.

## Compare fairly

Train the eight-input baseline and eleven-input control from the same starting model with the same adapter configuration, training budget, seeds, and evaluation schedule. Compare predictions at matched holdout rows and use the same prespecified checkpoint rule and P/N threshold. Report accuracy, balanced accuracy, P/N precision and recall, F1, and uncertainty of the paired difference; resample DOI groups rather than assuming records from one paper are independent.

Report performance both across the full matched holdout and by process availability. A supplementary missingness-only control can replace each observed process value with a generic `Reported` flag to assess whether a gain comes mainly from reporting patterns. Do not describe such flags as physical process settings.

The separate [nine-field control](../data/processed_data_json/processed_enrich_9field/README.md) adds only `stirring`, with lowercase `yes`, `no`, and `not reported` values and its own [system prompt](../prompts/training/reaction_prediction_process_enrich_9field.txt). It includes reported preparation stirring in `yes` unless an explicitly static synthesis follows. It does not use the eleven-field `agitation` categories or the eleven-field HPC profile above.

Negative annotations may be inherited from successful source recipes, so a predictive difference is not evidence that a process change causes synthesis success. The archived split is disjoint by chemistry cluster but shares 864 DOIs between training and holdout. Retaining it supports the direct paired comparison; an independently prepared DOI/parent-grouped split is needed for a stronger paper-independent assessment. Washing, activation, other post-synthesis treatment, and product characterization are excluded from this control. Agitation categories summarize reported descriptions and may include preparative mixing rather than continuous agitation during crystallization.

No models have been trained and no process-ablation performance is claimed by this dataset release.
