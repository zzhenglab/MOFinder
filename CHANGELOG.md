# Changelog

## Unreleased

- Standardized workflow terminology across documentation, demonstration names, configurations, notebook controls, and displayed messages: data curation, dataset preparation, positive extraction, and negative reconstruction. Preserved prior run artifacts unchanged in indexed recorded-run directories and added executions using the current names.

- Kept executed demo notebooks and verified run snapshots, added persistent offline run records and explicit expected-output comparisons, and named the demo scripts/notebooks by workflow. Simplified curation CSV names and finished both branches at processed descriptions. Replaced the separate notebook walkthrough folder with Python source links and Markdown guides.

- Combined processed positive/negative tables and literature metadata in `data/processed_data/`, and training/holdout JSONL with split records in `data/final_json/`. Replaced stage/version filenames with `processed_positive.csv` and `processed_negative.csv`; the default preparation configuration now reads these included inputs. Kept fresh curation and linker-corrected preparation as named alternatives, and updated scripts, notebooks, manifests, tests, and CI paths without changing scientific data or dataset partitions.

- Simplified literature classification documentation and removed redundant public classification CSVs; the labels remain in the article and SI inventories, with detailed analysis retained locally.

- Broadened the descriptive Chemical synthesis category to include original papers reporting experimental MOF/framework preparation, including structural and application studies. Preserved prior primary-topic categories, evidence, uncertainty flags, and all saved triage Y/N decisions in the audit.

- Published rough non-LLM topic classifications for the full literature corpus, with separate historical triage Y/N labels, evidence, and uncertainty flags. Replaced download-state columns in public article/SI inventories with `Classification`; local retrieval progress remains supported.

- Consolidated demonstrations into offline cleaning, offline JSON preparation, and `Demo/03_api_demo/mof_api_demo.ipynb` for abstract triage and positive/negative mining. The API notebook displays complete abstracts and exact requests before explicitly enabled calls, then compares predictions with reference labels held out of the requests.
- Added holdout-first and training-example previews with reaction parameters and complete JSON records to the JSON preparation notebook. Shortened displayed checkout paths while preserving paths used for files and saved run provenance.
- Standardized dataset preparation, question-panel evaluation, and HPC training on `prompts/training/reaction_prediction.txt`. Removed the short training prompt while preserving the full prompt text and archived JSONL bytes. HPC bundles now use schema version 2, and the default 512-token input limit rejects overlength records instead of truncating them; rebuild older bundles into new directories.
- Corrected reaction-evaluation parsing to require a standalone P/N response after whitespace and case normalization, and corrected fallback token-probability attribution. New runs record `standalone_pn_v1`; historical prediction CSVs remain unchanged, and incompatible holdout runs cannot be resumed under the new protocol.
- Audited documentation links, demo paths, installation requirements, and execution notes. Historical validation reports retain their original results and are explicitly identified as checkpoints.
- Made the API notebook reject stale triage previews and compare predictions with the run's saved reference labels. The negative-mining demo now stops when YES-labelled positive DOIs are missing from the selected document manifest.
- Made negative mining reject unreadable existing plan CSVs before requests and replace prior DOI rows during explicit in-place reruns even when CSV skipping is disabled.
- Fixed pandas 3 compatibility for document download flags and missing solvent names and abbreviations, and made extraction and filename-collision tests portable on Windows.
- Made the JSON demonstration's expected-output comparison tolerate platform line endings while still requiring matching UTF-8 text and split assignments.
- Replaced the earlier numbered scripts, `eval/`, `visualization/`, top-level demo files, and old data with the reorganized package contents. Preserved the three existing submodule commits, their configuration, and the MIT license.
- Consolidated example inputs and walkthroughs under `Demo/` and updated paths without changing their datasets or expected results.
- Removed the separate duration-example input tables from the cleaning demo; time parsing remains part of the shared cleaning implementation and regression tests.
- Updated the GPT-4.1 training recipe to two epochs, with approximately 1,569 steps per epoch for the archived training set.
- Added a complete pre-upload checklist with input placement, offline commands, live checks, and remaining research artifacts.
- Added the GPT-4.1 dashboard training recipe and single-dataset GPT-oss-20B LoRA training, with a portable input bundle and offline input validation. Both now use the shared full reaction-prediction instructions.
- Added source-confirmed prime-symbol corrections for current linker normalization and a corrected negative-data table. Archived model inputs and split assignments remain unchanged.
- Consolidated browser image templates under `data/` and the recorded environment under `docs/environments/`.
- Restored the original README illustrations, dataset links, clone instructions, and open-weight model link.
- Renamed desktop downloading paths and commands to literature retrieval.
- Replaced upload-copy filenames in public manifests with descriptive source identifiers while retaining source checksums.
- Restored UTF-8 byte-order marks in archived cleaned CSVs and kept generated demo and split tables compatible with spreadsheet software.
- Placed training and holdout JSONL together under `data/final_json/` and included reproducible record assignments under `data/final_json/`.
- Added three article/SI replacement-template pairs and local-paper extraction configurations.
- Added explicit input-placement instructions to every walkthrough and a source-cell-to-function navigation guide.
- Added separate offline cleaning and JSON-preparation demos, with optional API-based triage and positive/negative mining examples.
- Added missing-duration recovery in both curation branches for overnight, numeric ranges, several/serval days, weeks, or months, and immediate events without numbers. Existing numeric durations are preserved.
- Included the original name-to-SMILES and SMILES-to-name dictionaries in the update package and documented their formats.
- Updated human-benchmark provenance to the latest question workbook; anonymous question and response exports are unchanged.
- Established the package, documentation, benchmark, configuration, prompt, and example directories.
- Moved the consolidated abstract-triage workflow into Python modules for screening, statistical evaluation, and plotting, with command-line entry points.
- Reduced the triage notebook to a walkthrough that calls the Python implementation and displays its results.
- Preserved the screening prompt, model defaults, response parsing, analysis order, and statistical definitions.
- Added explicit resume mode: saved attempts, including failures, are retained, and only requests without a saved record are dispatched.
- Added the 478-paper human reference and a six-field export of 13,773 bibliography records with file hashes.
- Added offline validation, human-agreement commands, a small example, and focused regression checks.
- Centralized installation metadata in `pyproject.toml`; `setup.py` now delegates to it. API and plotting dependencies can be installed without Jupyter.
- Moved article and SI literature retrieval into Python desktop applications with command-line launchers and read-only inventory validation.
- Replaced publisher names in the integrated literature retrieval code, routing fields, and image filenames with neutral identifiers; retained all 47 source image files byte for byte.
- Added two literature retrieval input exports with all 7,437 source rows and original download states. Preserved the differing publisher-routing results of the article and SI workflows.
- Moved literature retrieval paths and timing settings into configuration. Calibration is recorded locally, and download-state updates are saved to local working inventories without modifying archived inputs.
- Preserved literature retrieval browser sequences and file-naming logic. Made the SI five-row test option effective and retained mouse-corner fail-safe interruption in both applications.
- Documented missing SI templates, local desktop validation, and document-directory placeholders.
- Added the Publisher W SI entry template, bringing the icon inventory to 48 files.
- Added DOI-named demonstration PDFs with explicit provenance and isolated example configurations.
- Integrated document matching and optional PDF counts; retained SI-preferred combined counts and separated local matching states from archived literature retrieval inputs.
- Added JSON-backed positive extraction and independent CSV recovery. API credentials are read from the environment.
- Preserved active positive/negative mining and classification prompts in separate text files, with explicit configurations and concise calling notebooks.
- Integrated negative planning and Cartesian failure enumeration with documented DOI-specific corrections and preserved parent snapshots. Fixed the exclusion that previously depended on logging verbosity.
- Integrated positive/negative chemical curation and optional reports. Required an explicit molecular-weight lookup and corrected hydrate-fragment stoichiometry in metal mass conversion.
- Integrated classification JSONL preparation, seeded grouped splitting, forced benchmark conditions, and publication-year training subsets. Recorded split assignments and input identities.
- Preserved the archived cleaned snapshots unchanged and added an archived-input preparation route. Verified all 16 JSONL outputs and class map against the original notebook on those inputs.
- Documented the grouped split definitions, input identities, and remaining research inputs.

The replaced workflow and datasets remain accessible in [repository history at `bb6502b`](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a). Their earlier README is preserved with historical source links in [the historical workflow guide](docs/legacy_workflow.md).

### Evaluation and reference data

- Corrected H3BTB normalization to 1,3,5-Tris(4-carboxyphenyl)benzene in both curation branches and included the reference molecular-weight lookup.
- Removed the four local file-path columns from public cleaned tables while retaining all other cell values and row order.
- Added the archived fine-tuning training and validation JSONL files without changes.
- Integrated holdout and 22-question model evaluation, with deferred API clients, saved-output analysis, explicit configurations, and hidden API-key entry in notebooks.
- Added anonymous human benchmark records and analysis aligned by reaction ID.
- Retained the recorded evaluation rules and model settings; separate positive/negative reference-based workflows remain pending their source code and ground truth.
