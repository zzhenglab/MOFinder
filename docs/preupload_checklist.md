# Pre-upload checks and input preparation

Run commands from the repository root. The included examples, curated tables, training files, and anonymous human responses support local checks. Literature downloads, live model calls, and GPU training require separate checks in their execution environments. Record the date, environment, dataset hashes, and outcome of each completed check.

## 1. Set up a clean checkout

- [ ] Apply the update to a local clone, then inspect `git status --short` and `git diff --stat`.
- [ ] Keep the source notebooks available locally for comparison with [the code map](source_to_code.md). The short notebooks in `notebooks/` call the implementation in `src/mofinder/`.
- [ ] Create a Python 3.10 or newer environment and install the required dependencies:

```bash
python -m pip install -e ".[triage,literature-retrieval,mining,curation,datasets,evaluation,notebook]"
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `python` if that environment is not activated. On Linux or macOS, use `.venv/bin/python`. Environment creation is described in [installation](installation.md).

Local configurations can be stored in `configs/local/`, which is excluded from Git. For a copied configuration placed directly in that folder, change `project_root` from `".."` to `"../.."`; otherwise its repository-relative paths resolve incorrectly. Choose new output directories when changing input data, prompts, or model settings.

## 2. Check the included files without external services

No input replacement is needed for these commands. The desktop validation commands inspect inventories and image templates without opening Chrome.

```bash
python -m unittest discover -s tests -v
python Demo/03_api_demo/run_demo.py triage
python -m mofinder.literature.triage validate-inputs --metadata data/metadata/literature_metadata.csv --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
python tools/literature_retrieval/fetch_papers.py --validate
python tools/literature_retrieval/fetch_si.py --validate
python -m mofinder.literature.match_documents match --config configs/example_document_matching.json
python -m mofinder.extraction.positive validate --config configs/example_positive_extraction.json
python Demo/01_data_cleaning/run_demo.py --check
python Demo/02_json_preparation/run_demo.py --positive-csv Demo/01_data_cleaning/outputs/mof_extraction_1_2_3_4_5_6.csv --check
python Demo/03_api_demo/run_demo.py validate
python -m mofinder.evaluation.holdout validate --config configs/holdout_evaluation.json
python -m mofinder.evaluation.quest validate --config configs/quest_evaluation.json
python -m mofinder.evaluation.human_quest analyze
```

| Check | Expected result |
| --- | --- |
| Regression tests | All tests pass; API responses and training calculations are checked locally where fixtures or mocks are used. |
| Small triage example | 12 reference publications (9 Y and 3 N); four scheduled (3 Y and 1 N), with eight outside the selected subset. All 12 abstracts are available. |
| Full triage reference | 478 publications, 293 Y and 185 N; no missing reference abstracts. |
| Retrieval inventory validation | Both inventories and required image templates load. Unmapped publisher profiles and the optional missing cookie template remain listed for local review. |
| Demonstration document matching | One main article and one SI match the DOI in `Demo/03_api_demo/inputs/mining/inventory.csv`; both have readable text. |
| Cleaning demo | 174 raw records produce 146 stage-6 records; the expected output comparison passes. |
| JSON preparation demo | 252 training records and 28 holdout records; zero shared clusters; expected JSONL and split assignments match. |
| API demo validation | Four selected abstracts and the sample PDF pair are readable. Before positive mining runs, its missing output CSV is expected in the negative-input report. |
| Holdout validation | 2,595 archived records with P/N labels and valid message structure. |
| Question validation | 22 questions, 11 P and 11 N; configured model settings are reported. This does not establish account access. |
| Human analysis | 98 participants, 22 questions, 2,156 responses; summary and participant/question tables are written locally. |

The duration conventions are regression-tested in `tests/test_curation_times.py` and used by both cleaning branches. They supplement the existing cleaning rules. Reported numeric `time_h` values and original `time_text` remain intact; supported text fills missing or nonnumeric durations.

## 3. Reproduce the included datasets

The archived and corrected inputs are separate dataset versions. Keep their output folders, split assignments, training jobs, and evaluated models together.

```bash
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation_archived.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_archived.json
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation_corrected.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_corrected.json
```

| Version | Input files | Output directory | Expected train / holdout |
| --- | --- | --- | ---: |
| Archived | `data/cleaned_data/archived/positive_stage6.csv` and `data/cleaned_data/archived/negative_stage6_v3.csv` | `results/datasets/archived_conditions/` | 23,528 / 2,595 |
| Corrected linker spellings | Same positive table and `data/cleaned_data/linker_corrected/negative_stage6_v3.csv` | `results/datasets/corrected_conditions/` | 23,436 / 2,604 |
| Newly mined and cleaned records | Both stage-6 files under `results/curation/` | `results/datasets/conditions/` | Determined by the new inputs |

- [ ] For the archived run, compare `mof_ft_train.jsonl` byte-for-byte with `data/training/train.jsonl`, and `mof_ft_holdout.jsonl` with `data/training/holdout.jsonl`.
- [ ] Check each run's `mof_ft_split_summary.json` for filtering counts, P/N counts, year coverage, input hashes, and benchmark coverage.
- [ ] Confirm that training and holdout have no shared cluster keys or exact condition inputs. Dataset preparation enforces these checks before writing outputs.
- [ ] Keep the corrected run's new assignments. Linker names enter cluster identity, so archived assignments cannot be transferred to corrected names.

The included partition is a grouped training/holdout split. It does not include a third independent test partition, and it is not DOI- or parent-disjoint. If the holdout is supplied as validation data during training, record that use with the training job.

### Publication-year subsets and future-year evaluation

The preparation commands already generate separate and cumulative publication-year **training subsets** in four-period and five-period variants. The required `DOI` and `Publication Year` mapping is included in `data/metadata/publication_years.csv`. These files can be generated immediately from either included stage-6 dataset, or after a new curation run. Missing-year rows remain in the full partition but are excluded from year subsets.

A train-on-past, test-on-future evaluation is a separate pending workflow. A fixed all-year holdout evaluated against successively larger training-year subsets is not that temporal test. Before implementing the temporal partitions, specify:

- [ ] The cutoff dates and which years belong to training, validation, and future testing.
- [ ] How publications, successful parents, and their enumerated descendants are grouped across boundaries.
- [ ] How to handle clusters spanning a cutoff and records with missing years.
- [ ] Which development data determine thresholds or checkpoints, and which future records remain outside those decisions.
- [ ] The matching training, evaluation, and prediction-export commands.

The publication-year metadata is available. The confirmed temporal protocol or revised source notebook, plus resulting split assignments and model results, are still needed.

One retained archived holdout record has no mapped publication year (`10.1021/jacs.5c08726`). Check its bibliographic year before building future-year partitions; do not infer its year from the DOI string.

## 4. Test literature retrieval and mining with local papers

### Three to five article/SI pairs

For this small test, use `Demo/03_api_demo/literature_input/`. Replace the six blank PDFs below with the corresponding real documents. To use different papers, change `inventory.csv` and both filenames for each DOI.

| DOI | Replace under `literature_input/main/` | Replace under `literature_input/si/` |
| --- | --- | --- |
| `10.1021/jacs.2c09756` | `10.1021_jacs.2c09756.pdf` | `10.1021_jacs.2c09756_SI.pdf` |
| `10.1002/adfm.200600944` | `10.1002_adfm.200600944.pdf` | `10.1002_adfm.200600944_SI.pdf` |
| `10.1002/adfm.201002517` | `10.1002_adfm.201002517.pdf` | `10.1002_adfm.201002517_SI.pdf` |

The DOI list controls selection. The local configuration accepts up to five papers and uses concurrency 1. Use documents with extractable text; scanned pages need OCR before this workflow. The illustrative pair in `Demo/03_api_demo/inputs/mining/` is ready for a separate demonstration and does not need replacement.

```bash
python Demo/03_api_demo/run_demo.py validate --config-dir Demo/03_api_demo/configs/local_papers
```

- [ ] Confirm that the selected article/SI pairs match the inventory and have readable text.
- [ ] Confirm that `placeholder_documents` is empty before live mining. The live runner rejects remaining templates.
- [ ] Check the models in the selected configuration files. Provide the API key through the hidden prompt or `OPENAI_API_KEY`.

```bash
python Demo/03_api_demo/run_demo.py triage --live
python Demo/03_api_demo/run_demo.py positive --config-dir Demo/03_api_demo/configs/local_papers --live
python Demo/03_api_demo/run_demo.py negative --config-dir Demo/03_api_demo/configs/local_papers --live
```

The triage command selects the first four of the 12 abstracts in `Demo/03_api_demo/inputs/`. It is independent of the PDF selection. Positive mining must finish before negative mining. Negative mining can legitimately return no records when the chosen papers contain no eligible trial/failure evidence.

Inspect the local-paper outputs under `results/examples/03_api_demo/local_papers/`:

- [ ] `positive/mof_extraction.csv`: fields agree with the source passages for the selected papers.
- [ ] `positive/mof_json_store/`: article and numbered synthesis JSONs exist and retain all extracted fields.
- [ ] `negative/`: plans identify their supporting text and correct successful parent; parent snapshots and enumerated records are retained.
- [ ] Enumerated modifications correspond to the saved plan options. Their Cartesian combinations are reconstructed conditions, not a count of independently reported failed experiments.

See [the API demo](../Demo/03_api_demo/README.md) for configuration names and output details. A new run with different inputs or settings needs fresh connected output paths; otherwise resume rules skip existing records.

### Desktop download check

Install `.[fetch-gui]` on the target desktop. Start with a local copy of `Demo/03_api_demo/literature_input/inventory.csv`, which contains three DOIs, their links, and supported neutral publisher profiles. Update the rows for the papers being tested; the apps add their download-state columns. For an existing working inventory, clear only the download-state cells intended for this test. Launch each app with the selected file:

```bash
python tools/literature_retrieval/fetch_papers.py --workbook path/to/paper_test.csv
python tools/literature_retrieval/fetch_si.py --workbook path/to/si_test.csv
```

- [ ] Calibrate the Save-dialog filename field and relevant browser actions on this computer.
- [ ] Check the image templates against the current browser layout.
- [ ] Confirm that article PDFs appear in `data/local/articles/` and SI files in `data/local/supporting_information/` with DOI-derived names.
- [ ] Confirm that the working inventories in `results/literature_retrieval/` record the observed download outcomes.
- [ ] Test stop and resume on the small inventory before a larger run. The applications control the desktop and close Chrome windows, so save browser work first.

The [retrieval guide](literature_retrieval.md) explains calibration and status fields. A stored download state alone does not establish that a file exists on this computer.

## 5. Supply the full workflow inputs

Use the paths below for the main configuration. Files generated by an upstream step need not be copied manually. For an existing research run, restore the complete connected CSV/JSON stores or point a local configuration to their current locations.

| Stage | File or directory to provide | Required preparation |
| --- | --- | --- |
| Abstract triage | `data/metadata/literature_metadata.csv`; `benchmarks/abstract_triage/ground_truth.xlsx` | Included. For another collection, retain the documented bibliographic columns and DOI/reference-label schema. Resolve the three conflicting DOI groups before whole-corpus screening. |
| Document matching | `data/metadata/literature_retrieval/supporting_information.csv` | Included inventory. Select a local replacement CSV/XLSX with a `DOI` column for another collection. |
| Main articles | `data/local/articles/` | Add real PDFs, for example `10.1021_jacs.2c09756.pdf`. |
| Supporting information | `data/local/supporting_information/` | Add the corresponding `_SI.pdf` or supported text document. |
| Positive extraction | `results/extraction/document_manifest.csv` | Generated by matching; contains `DOI`, `Main File`, and `SI File`. |
| Negative planning | `results/extraction/positive/mof_extraction.csv` and `results/extraction/positive/mof_json_store/` | Generated together by positive extraction. Retain the trial/failure flag, notes, and complete DOI directories. A cleaned stage-6 CSV is not a substitute. |
| Negative enumeration | `results/extraction/negative/mof_extraction_failplans.csv` and `results/extraction/negative/mof_negative_plan_store/` | Generated by planning. Retain the plan JSONs, ordered successful-parent snapshots, and provenance files. |
| Positive cleaning | `results/extraction/positive/mof_extraction.csv` | Full raw extraction table. Preserve the original extraction schema and document-availability information. The existing source CSV can be selected here; the package currently distributes a smaller raw demo. |
| Negative cleaning | `results/extraction/negative/mof_extraction_failures_enum.csv` | Raw enumerated table produced before cleaning. The archived stage-6 table belongs in dataset preparation. |
| Organic linker information | `data/organic_linker_info/linker_molecular_weights.csv`; `data/organic_linker_info/linker_prime_corrections.json` | Included. MW CSV has no header. Leave unresolved weights blank until established. |
| Dataset preparation | Both stage-6 CSVs under `results/curation/`; `data/metadata/publication_years.csv` | Generated cleaned CSVs plus included publication years. Keep the positive stage-6 input even if optional stage-7 trimming also runs. |

Run the matching, extraction, and enumeration commands in [the workflow guide](workflow.md). Then test both cleaning branches and the newly generated dataset:

```bash
python -m mofinder.curation validate-inputs --config configs/curation.json --mode both
python -m mofinder.curation run --config configs/curation.json --mode both
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

- [ ] Inspect every numbered cleaning table and branch report, including row removals, aliases, quantities, temperatures, times, and derived ratios/concentrations.
- [ ] Compare corresponding stages with the original notebooks using identical raw inputs and lookup files. Use [the code map](source_to_code.md) to locate the original operations.
- [ ] Account for the documented H3BTB, hydrate-mass, duration-text, and DOI-specific prime corrections when comparing new output with archived tables. Archived JSONL files remain unchanged.
- [ ] Retain the curation and split manifests with the generated data.

## 6. Run the notebook walkthroughs

Install `.[notebook]` in the same environment as the workflow packages. Open each notebook from the repository root or its containing directory and run cells in order. A notebook that reports missing production input files has checked setup only; it has not executed that stage.

| Notebook | Input preparation | Switches or settings for execution |
| --- | --- | --- |
| `notebooks/01_abstract_triage.ipynb` | Included bibliography/reference; select a saved run to reproduce model metrics | `RUN_SCREENING`; `RUN_DIR` for saved analysis |
| `notebooks/02_document_matching.ipynb` | Included demonstration pair by default; select `configs/document_matching.json` for `data/local/` papers | Matching runs locally; `RUN_COUNTS` optionally enables document counts |
| `notebooks/03_positive_extraction.ipynb` | Run matching; select the corresponding positive configuration | `RUN_EXTRACTION`; `RUN_BACKFILL` only with saved JSONs |
| `notebooks/04_negative_reconstruction.ipynb` | Complete positive extraction and retain CSV/JSON stores | `RUN_MINING`, then `RUN_ENUMERATION` |
| `notebooks/05_data_curation.ipynb` | Supply both raw extraction tables | `RUN_CURATION`; `TRIM_POSITIVE` controls optional stage 7 |
| `notebooks/06_dataset_preparation.ipynb` | Supply both stage-6 files, or select the archived/corrected configuration | `RUN_PREPARATION` |
| `notebooks/07_holdout_evaluation.ipynb` | Included archived files; accessible model ID and fresh output name | `RUN_SANITY_TEST` or `RUN_EVALUATION`; `test_mode=True` limits the latter to ten pending records |
| `notebooks/08_quest_evaluation.ipynb` | Included question panel; accessible model group | `RUN_EVALUATION`; set one round for a small live check |
| `notebooks/09_human_benchmark.ipynb` | Included anonymous questions and responses | Local analysis; select a new output directory for another cohort |
| `Demo/01_data_cleaning/demo.ipynb` | Included raw records and lookups | Local cleaning demonstration |
| `Demo/02_json_preparation/demo.ipynb` | Included cleaned tables or the cleaning demo output | Local JSONL preparation |
| `Demo/03_api_demo/api_demo.ipynb` | Four abstracts selected from the included 12-paper subset and the sample article/SI pair; `.[mining,notebook]` installed; optionally select the local-paper configuration directory | Preview abstracts and exact requests locally; use `RUN_TRIAGE` for GPT predictions/reference comparison, then `RUN_POSITIVE_MINING` before `RUN_NEGATIVE_MINING`; all default to `False` |

Optional document counting requires `.[document-counts]`; tokenizer resources may download on first use. Default notebook execution leaves live model calls disabled. Clear notebook outputs containing local paths, API output, or run-specific data before committing walkthroughs.

For the API demo's triage stage, confirm that the displayed requests contain the bibliographic fields and abstracts, with human labels used only in the results comparison. A preview with `RUN_TRIAGE = False` validates setup only. A live run sends four abstracts to OpenAI, incurs API charges, and saves its outputs under `results/examples/03_api_demo/triage/`; inspect request statuses as well as predictions.

## 7. Check training and model evaluation

### GPT-4.1 dashboard training

- [ ] Select the intended dataset version and record its hashes.
- [ ] Upload the training JSONL directly through the fine-tuning dashboard. Use the [training recipe](training_openai.md): two epochs, batch size 15, learning-rate multiplier 2, and seed 42. For the separate one-epoch run, set Epochs to 1; the archived 23,528 records give approximately 1,569 steps. Keep the two jobs and their model IDs separate.
- [ ] Record whether the paired holdout was also uploaded as validation data.
- [ ] Save the completed job ID, uploaded file IDs, resolved settings, actual step count, metrics, and trained model ID.
- [ ] Set the resulting accessible model ID and a fresh output name in the evaluation configuration. Existing fine-tuned model IDs do not update automatically when a new dataset is prepared.

### Local GPU or HPC training

Preparation and validation require no GPU:

```bash
python tools/training/prepare_hpc.py --output results/local/preupload_hpc
python tools/training/train_hpc.py --bundle results/local/preupload_hpc --validate-only
```

Expected counts for the default bundle are 23,528 training, 2,595 holdout, and 22 question records. To use the corrected or newly curated dataset, provide its paired `--train` and `--holdout` paths to preparation. Use a new bundle directory.

- [ ] Transfer the bundle and code to the GPU system; repeat `--validate-only` after transfer.
- [ ] Provide a complete local GPT-oss-20B model/tokenizer directory and the working CUDA environment described in [HPC training](training_hpc.md).
- [ ] Run the documented single-dataset training command. The 5,000-step recipe is separate from the GPT-4.1 dashboard epoch setting.
- [ ] Check `result.json`, all scheduled prediction exports, runtime versions, and final adapter/tokenizer files when `--save-adapter` is selected.

### Small live evaluations and saved results

After selecting accessible models and setting `OPENAI_API_KEY`:

```bash
python -m mofinder.evaluation.holdout run --config configs/holdout_evaluation.json --model holdout_mofinder --test-mode
```

For MOF Quest, copy `configs/quest_evaluation.json` to `configs/local/quest_smoke.json`, set `project_root` to `"../.."`, select one accessible model, and change that group's `rounds` to `1`. Then run:

```bash
python -m mofinder.evaluation.quest run --config configs/local/quest_smoke.json --group latest_fine_tuned
```

- [ ] Check raw responses, reference alignment, token probabilities where supported, failed/invalid counts, and saved manifests. A one-model, one-round question run has 22 attempted records.
- [ ] Analyze the saved CSVs with the commands in [holdout evaluation](holdout_evaluation.md) and [question evaluation](quest_evaluation.md).
- [ ] Add the complete paper-associated prediction archives to reproduce reported performance without new API calls. Small live checks alone do not reproduce those results.

## 8. Files and results still needed for full reproduction

| Material | Current availability | Destination or next action |
| --- | --- | --- |
| Full raw positive extraction CSV | Source file exists; only the raw cleaning subset is distributed | Select the complete source in `configs/curation.json` for full cleaning; prepare a portable release export if distributing it. |
| Successful-synthesis JSON store | Not distributed | Restore under `results/extraction/positive/mof_json_store/` or select its location in a local configuration. Needed for negative mining and CSV recovery. |
| Full negative plan, parent, and enumerated JSON stores | Not distributed | Restore the connected stores under `results/extraction/negative/`, with the pre-cleaning enumeration CSV. Needed to reproduce planning/enumeration independently of a new model run. |
| Real research PDFs | Local inputs | Add to the documented local folders for retrieval/mining checks; the supplied sample and blank templates do not replace the research corpus. |
| Positive and negative extraction evaluation | Separate scoring code and ground-truth records pending | Integrate each evaluation's actual schema and reference data before assigning public input paths. |
| Full triage, holdout, and question-panel model predictions | Complete run archives pending | Retain the associated manifests and CSV/JSONL outputs in their documented run layouts; connect released results to immutable input and model identities. |
| Training job provenance | Recipes included; completed job records pending | Record the exact dataset version, API job or HPC run, trained model, and downstream evaluation run. |
| Future-year validation/test split | Publication years included; temporal protocol pending | Confirm the protocol described above, then generate versioned partitions and evaluation outputs. |
| Publication- and parent-grouped evaluation | Current split groups precursor/linker/solvent clusters | Supply the confirmed grouping procedure and the parent identities required to generate separate publication/parent-disjoint partitions. |
| Holdout calibration analysis | P/N probabilities are saved where supported; ECE, Brier score, NLL, and reliability plots are not implemented in the standard holdout analysis | Add the agreed metric definitions and plots using complete saved predictions. Retain development/test separation for any fitted calibration. |
| Additional baseline and ablation results | Historical analysis scripts are available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a); revised matched comparisons are not included | Supply the input/split identities, settings, and predictions for any final positive-unlabeled baseline, reconstruction ablation, or process-variable comparison. |
| Prospective and structural source data | Historical Reactome files are available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a) | Link any revised candidate scores, selection records, measured outcomes, replicate identifiers, PXRD source data, and structure/archive identifiers used in the final figures. |
| Final figure/table inputs | Reproduction map incomplete | Complete [the figure/table map](figure_table_map.md) with saved inputs and commands for each final result. |

The anonymous human benchmark inputs, archived cleaned tables, original train/holdout files, split assignments, prompts, molecular-weight lookup, and name/SMILES mappings are included. Their source workbooks are not required to run the included analyses. A new human workbook can be exported with `mofinder.evaluation.human_quest export-workbook` as documented in [human analysis](human_benchmark.md).

## 9. Inspect the GitHub payload

- [ ] Preview the root README and check its two reused figures, internal links, dataset links, and current workflow status.
- [ ] Confirm that all demonstrations are under `Demo/` and each notebook's input instructions match the current paths.
- [ ] Check comments against the source notebooks using the source-to-code map. Keep chemical explanations and necessary operational notes; keep release-specific comparison notes outside the scientific code.
- [ ] Check that the included archived files still match their manifests and that new corrected outputs are clearly identified.
- [ ] Match the manuscript and supporting-information dataset counts, split descriptions, training settings, checkpoint identities, and performance tables to the exact release inputs and saved runs.
- [ ] Inspect `git diff --name-status` and `git status --short`. Commit the intended code, data, prompts, documentation, and required deletions. Local outputs, calibration, credentials, and private workbooks should not appear in the staged list.
- [ ] Leave all notebook live-run switches disabled in the committed walkthroughs.
- [ ] Run the Windows/Linux GitHub Actions workflow on the uploaded commit and inspect every job. Local tests do not establish the remote CI result.
- [ ] After all intended results are connected to their data and code, set the release version and citation metadata and archive the release.

The ZIP's update instructions, manifest, and update script are delivery utilities. They belong beside the packaged `MOFinder/` directory and are not repository files. The update instructions describe which files to apply; the repository's `docs/` contains the reusable workflow documentation.
