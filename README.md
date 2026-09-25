# MOFinder

MOFinder extracts MOF synthesis information from the literature, reconstructs evidence-supported negative reaction records, and prepares datasets for synthesis-outcome prediction.

<p align="center">
  <img src="data/mofinder.png" alt="MOFinder web application" width="750">
</p>

[Web application](https://mofinder.chemistry.wustl.edu/) · [MOF Quest](https://github.com/zzhenglab/MOF-Quest) · [Demos](Demo/README.md) · [Source code](docs/source_to_code.md) · [Abstract triage](docs/triage.md) · [Literature retrieval](docs/literature_retrieval.md) · [Workflow guide](docs/workflow.md) · [Model evaluation](docs/evaluation.md)

## Quick start

The workflow runs through Python commands. Python 3.10 or newer is required. Clone the repository and initialize its related applications:

```bash
git clone --recurse-submodules https://github.com/zzhenglab/MOFinder.git
cd MOFinder
```

Start with the two offline demonstrations:

```bash
python -m pip install -e ".[curation,datasets]"
python Demo/01_data_curation/mof_data_curation_demo.py --check
python Demo/02_dataset_preparation/mof_dataset_preparation_demo.py --positive-csv Demo/01_data_curation/outputs/mof_extraction_6.csv --check
```

These regenerate processed synthesis records and prepare grouped training and holdout JSONL. `--check` compares the files with the bundled expected outputs. The [data mining demo (API required)](Demo/03_api_data_mining/README.md) combines abstract triage, positive extraction, and negative reconstruction.

To try data mining, install `.[mining,notebook]` and open the [data mining notebook](Demo/03_api_data_mining/mof_api_data_mining_demo.ipynb). Run its preview cells to inspect four abstracts and the exact requests; set `RUN_TRIAGE = True` to generate predictions using GPT-5 with high reasoning effort and compare them with human labels. The same notebook provides positive extraction and negative reconstruction for the sample article/SI pair. Supply an API key when enabling a stage; live requests incur API charges. See the [demo instructions](Demo/03_api_data_mining/README.md).

Install the API and plotting dependencies, then validate the full triage inputs:

```bash
python -m pip install -e ".[api,plotting]"
python -m mofinder.literature.triage validate-inputs --metadata data/processed_data/literature_metadata.csv --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
```

With `OPENAI_API_KEY` set and the model settings checked, screen the 478-paper reference:

```bash
python -m mofinder.literature.triage screen --config configs/abstract_triage.json --output-dir results/abstract_triage/benchmark_run
```

Analyze that saved run locally:

```bash
python -m mofinder.literature.triage analyze --run-dir results/abstract_triage/benchmark_run --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
```

See [installation](docs/installation.md) and [triage](docs/triage.md) for credentials, resuming interrupted runs, and analysis options. Live screening requires API access; validation, saved-run analysis, and human-agreement calculations do not.

## Source code

The current implementation is in [`src/mofinder/`](src/mofinder/). The [source code map](docs/source_to_code.md) pairs each task with its Python file and Markdown instructions. The [original numbered research scripts](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a) remain available at the recorded historical commit; [the historical file index](docs/legacy_workflow.md) links to extraction, data curation, dataset preparation, model evaluation, and plotting code.

## Choose a workflow

| Task | Start here |
| --- | --- |
| Run data curation and dataset preparation without API access | [Offline demos](Demo/README.md) |
| Inspect abstracts, obtain GPT triage predictions, and try positive extraction and negative reconstruction | [data mining demo (API required)](Demo/03_api_data_mining/README.md) |
| Look up chemical names and SMILES | [Original mapping tables](data/name_SMILES_mappers/README.md) |
| Check installation and example inputs | [Offline input check](Demo/03_api_data_mining/README.md#install-and-check-the-inputs) |
| Screen the 478-paper reference | [Python screening command](docs/triage.md#screening) |
| Recalculate a completed triage run | [Saved-run analysis](docs/triage.md#saved-run-analysis) |
| Inspect human annotations | [Abstract triage benchmark](benchmarks/abstract_triage/README.md) |
| Download articles and supporting information | [Desktop literature retrieval guide](docs/literature_retrieval.md) |
| Match documents and extract synthesis records | [Workflow guide](docs/workflow.md) |
| Curate records and prepare training and holdout JSONL | [Data curation](docs/curation.md) and [dataset preparation](docs/datasets.md) |
| Extract records from three to five local article/SI pairs | [Local PDF inputs](Demo/03_api_data_mining/literature_input/README.md) |
| Read the Python implementation and its instructions | [Source code and workflow guides](docs/source_to_code.md) |
| Inspect processed positive and negative records and publication metadata | [Processed data](data/processed_data/README.md) |
| Inspect training, holdout, and record assignments | [Final JSONL and split records](data/final_json/README.md) |
| Train a model from one prepared dataset | [OpenAI interface](docs/training_openai.md) or [HPC workflow](docs/training_hpc.md) |
| Check the DOI-named sample documents locally | [Extraction example](Demo/03_api_data_mining/inputs/extraction/README.md) |
| Evaluate models on the holdout and question panel | [Evaluation workflow](docs/evaluation.md) |
| Analyze the human question benchmark | [Human benchmark](docs/human_benchmark.md) |
| Inspect data identities and transformations | [Data manifest](data/manifest.json) |
| Find the earlier extraction and modeling scripts | [Original research scripts](docs/legacy_workflow.md) |

## Repository layout

| Location | Contents |
| --- | --- |
| `src/mofinder/literature/` | Input validation, screening, document matching, and local document counts |
| `src/mofinder/literature_retrieval/` | Article and SI desktop applications, configuration loading, and inventory handling |
| `src/mofinder/extraction/` | Positive extraction, JSON recovery, negative plans, and enumeration |
| `src/mofinder/curation/` | Chemical normalization, amount conversion, derived features, and reports |
| `src/mofinder/datasets/` | Condition-classification records, grouped splits, and training JSONL |
| `src/mofinder/training/` | Single-dataset training input preparation and HPC fine-tuning |
| `src/mofinder/evaluation/` | Triage statistics, reaction holdout/model evaluation, and human benchmark analysis |
| `src/mofinder/plotting/` | Triage figures and associated source tables |
| `configs/` and `prompts/` | Named settings and prompt text |
| `data/paper_processing_assets/` | Browser image templates with neutral publisher identifiers |
| `data/` | Input manifests, metadata, organic linker information, dataset snapshots, and split records |
| `data/organic_linker_info/` | Organic linker molecular weights and publication-specific name corrections |
| `data/processed_data/` | Processed positive and negative CSVs, publication metadata, retrieval inventories, and a linker-corrected alternative |
| `data/name_SMILES_mappers/` | Original name-to-SMILES and SMILES-to-name mapping tables |
| `data/final_json/` | Final training and holdout JSONL with record assignments, split summary, and class map |
| `benchmarks/` | Human references and benchmark-specific documentation |
| `Demo/` | Offline data curation and dataset preparation; API examples for abstract triage, positive extraction, and negative reconstruction |
| `docs/` | Installation, workflow guides, source provenance, and reproduction instructions |
| `tools/literature_retrieval/` | Entry points for optional desktop download tools |
| `tools/training/` | Training-bundle preparation and GPU training entry points |
| `tests/` | Automated checks of workflows, splitting, and data integrity, run by GitHub Actions |

Python modules contain the reusable implementation and support terminal or HPC execution. Markdown guides explain their inputs, commands, and outputs; [the source code map](docs/source_to_code.md) links each guide directly to its implementation and the original research scripts. Interactive examples and saved run displays live together under `Demo/`, alongside Python runners. Training instructions are available for the [OpenAI interface](docs/training_openai.md) and [HPC execution](docs/training_hpc.md).

## Data and reproducibility

Start with [processed data](data/processed_data/README.md), then use it to prepare [final JSONL and split records](data/final_json/README.md). Processed positive and negative CSVs and their publication metadata are together in `data/processed_data/`; the prepared training and holdout files and their assignments are together in `data/final_json/`.

| File | Contents | Records |
| --- | --- | ---: |
| [`data/processed_data/processed_positive.csv`](data/processed_data/processed_positive.csv) | Positive records after curation, before dataset filtering | 15,340 |
| [`data/processed_data/processed_negative.csv`](data/processed_data/processed_negative.csv) | Reconstructed negative records after curation, before dataset filtering | 15,063 |
| [`data/processed_data/linker_corrected/processed_negative.csv`](data/processed_data/linker_corrected/README.md) | Same negative records with source-confirmed linker prime symbols restored | 15,063 |
| [`data/final_json/train.jsonl`](data/final_json/train.jsonl) | Training set: 11,968 P and 11,560 N | 23,528 |
| [`data/final_json/holdout.jsonl`](data/final_json/holdout.jsonl) | Holdout set: 1,320 P and 1,275 N | 2,595 |
| [`data/final_json/split_assignments.csv`](data/final_json/split_assignments.csv) | Source-row assignments for the retained training and holdout records | 26,123 |

Training and holdout records use chat-format JSONL. Each record contains a system instruction, a user message with eight reaction-condition fields, and an assistant answer of `P` or `N`.

<p align="center">
  <img src="data/Figures-03a.png" alt="Example reaction-condition input and P output" width="750">
</p>

The current triage input consists of 13,773 bibliography rows and 478 annotated reference publications. The reference has 293 Y and 185 N consensus labels. Every reference DOI has an abstract in the metadata export. Reference labels remain authoritative, including documented rubric decisions and overrides.

Complete saved model-run artifacts and reference-based scoring for positive extraction and negative reconstruction are not included. The available [evaluation workflows](docs/evaluation.md) cover abstract triage, reaction outcomes, and human responses. Statistical methods and prompt-development history are described in [the triage guide](docs/triage.md).

Each new run records its settings, prompt, input hashes, response status, and predictions. Workflows create `results/` locally as needed; generated outputs are excluded from Git. A complete saved run enables later analysis without repeating model requests. Explicit resume mode continues only requests with no saved record and preserves recorded failures.

This study focuses on LLM-based literature triage. To examine trends, we also roughly group papers into Chemical synthesis, Theory & modeling, Crystal engineering, and Functional materials using keyword rules, not an LLM. The results suggest that keyword grouping alone is insufficient to identify synthesis-relevant papers: many papers in the Chemical synthesis group are still excluded by triage. These classifications are included directly in the [article and SI tables](data/processed_data/literature_retrieval/README.md).

Published inventories omit download-status columns; the desktop applications maintain these states in local working copies. Research article and SI downloads remain local. The [demonstration PDFs](Demo/03_api_data_mining/inputs/extraction/README.md) contain synthetic sample text and no measured experimental data. See [the literature retrieval input inventory](data/processed_data/literature_retrieval/README.md) for methods, input hashes, and publisher-profile assignments.

The default [dataset configuration](configs/dataset_preparation.json) reads `processed_positive.csv`, `processed_negative.csv`, and `publication_years.csv` from `data/processed_data/`. Regenerate their final JSONL and split records locally with:

```bash
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

This writes to `results/datasets/conditions/`. To prepare a dataset after running curation, select [dataset_preparation_from_curation.json](configs/dataset_preparation_from_curation.json), which writes to `results/datasets/curated_conditions/`. The included processed tables omit four local-path columns while preserving all other values. The molecular-weight lookup is included, and new curation runs use the corrected H3BTB identity.

Current curation also restores source-confirmed prime symbols through a publication-specific lookup. The [corrected negative table](data/processed_data/linker_corrected/README.md) is available separately, with a configuration that calculates new grouped partitions. Linker spellings affect grouping, so corrected conditions use newly calculated splits. The bundled final JSONL and assignments preserve their original values.

Model evaluation reads reference answers locally from the final holdout JSONL for scoring and sends only the intended reaction inputs. Human responses are distributed with anonymous participant IDs; the original workbook remains the source for provenance. See [evaluation](docs/evaluation.md).

The historical data and counts described in [the earlier workflow](docs/legacy_workflow.md) belong to their original processing configuration. Its removed files are linked to the historical commit; the current datasets are listed above.

## Related applications

- `WebApplication/`: MOFinder web interface.
- `MOF-Quest/`: reaction-prediction game.
- `SMILESearcher/`: chemical name and SMILES resolution.

These three components retain their existing pinned Git submodule commits and configuration. Initialize them when needed:

```bash
git submodule update --init --recursive
```

## Open-weight model

The [GPT-oss-MOF checkpoint](https://huggingface.co/StarLiu714/GPT-oss-MOF) is available for local synthesis-outcome prediction. Local inference requires hardware suitable for a 20B-parameter model. The checkpoint is optional; data curation and dataset preparation run on a CPU without model downloads.

## Citation and license

Software citation metadata is provided in [CITATION.cff](CITATION.cff). The paper-associated release and archival identifier will be added when finalized. The MOFinder code uses the [MIT License](LICENSE); submodules retain their own licenses.
