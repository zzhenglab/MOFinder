# Mining, curation, and dataset preparation

The workflow uses Python modules, with a short notebook for each stage. Configurations define paths and run settings; model instructions are stored in `prompts/`. Run commands from the repository root after installing:

```bash
python -m pip install -e ".[mining,curation,datasets]"
```

## Stage inputs and outputs

| Stage | Reads | Writes | Guide |
| --- | --- | --- | --- |
| Document matching | DOI inventory and local article/SI files | Document manifest; local file-status inventory | [Matching](document_matching.md) |
| Positive extraction | Document manifest, article/SI text, extraction prompts | Raw responses, parsed article and synthesis JSONs, synthesis CSV | [Positive extraction](positive_extraction.md) |
| CSV recovery | Document manifest and saved positive JSONs | Reconstructed or completed synthesis CSV | [Positive extraction](positive_extraction.md) |
| Negative planning | Raw positive CSV, successful synthesis JSONs, article/SI text | Evidence-based modification plans and parent-synthesis snapshots | [Negative reconstruction](negative_extraction.md) |
| Failure enumeration | Modification plans and their successful parents | Enumerated negative JSONs and CSV | [Negative reconstruction](negative_extraction.md) |
| Curation | Raw positive CSV or enumerated negative CSV; linker molecular weights | Successive cleaned tables, optional plots and reports | [Curation](curation.md) |
| Dataset preparation | Stage-6 positive and negative tables; DOI years | Train/holdout JSONL, split assignments, temporal subsets, run records | [Datasets](datasets.md) |

Do not delete the successful synthesis JSONs after flattening them to CSV. Negative reconstruction needs the nested records and their one-based parent indices. The raw positive `article_trial_or_failure` flag controls eligibility for negative planning.

## Local documents

The production configurations read:

```text
data/local/articles/10.1021_jacs.2c09756.pdf
data/local/supporting_information/10.1021_jacs.2c09756_SI.pdf
```

Use the DOI with `/` replaced by `_`; add `_SI` for supporting information. These local download directories are excluded from Git. The separately labelled [demonstration pair](../Demo/05_data_mining/README.md) is included for an offline matching check:

```bash
python -m mofinder.literature.match_documents match --config configs/example_document_matching.json
```

The PDFs contain synthetic sample text and no measured experimental data. Their outputs belong under `results/examples/`, separately from research data.

## Production sequence

First match the local files against the selected literature retrieval inventory:

```bash
python -m mofinder.literature.match_documents match --config configs/document_matching.json
python -m mofinder.extraction.positive validate --config configs/positive_extraction.json
```

With model access and `OPENAI_API_KEY` configured, start positive extraction:

```bash
python -m mofinder.extraction.positive run --config configs/positive_extraction.json
```

Recovery from saved JSONs is an independent local operation:

```bash
python -m mofinder.extraction.backfill --config configs/positive_extraction.json
```

Next validate and run negative planning, then enumerate the saved plans:

```bash
python -m mofinder.extraction.negative validate --config configs/negative_extraction.json
python -m mofinder.extraction.negative mine --config configs/negative_extraction.json
python -m mofinder.extraction.negative enumerate --config configs/negative_extraction.json
```

Mining commands send document text to the configured model. Matching, recovery, enumeration, curation, and dataset preparation require no model requests. Notebook switches disable live mining by default.

Validate the required lookup and run both curation branches:

```bash
python -m mofinder.curation validate-inputs --config configs/curation.json --mode both
python -m mofinder.curation run --config configs/curation.json --mode both
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

To prepare datasets directly from the archived cleaned records, use:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_archived.json
```

This independent offline route uses the archived processed records directly. The [curation guide](curation.md) and [dataset guide](datasets.md) describe individual stages and options. The default dataset input uses positive stage 6, as in the source preparation notebook. Positive stage 7 is optional trimming and is not selected automatically.

## Train a model

The prepared training JSONL supports two separate training routes:

- [GPT-4.1 dashboard training](training_openai.md) records the upload procedure and hyperparameters.
- [GPT-oss-20B GPU training](training_hpc.md) prepares one train/holdout pair for transfer to an HPC system and runs the local LoRA training workflow.

Keep the dataset hashes and resulting model identity with each run. The existing evaluation model IDs refer to completed research runs; preparing a new dataset or training job does not update those IDs automatically.

## Preserve scientific provenance

The negative enumerator applies the Cartesian product of the permitted option lists. Some generated records therefore vary more than one factor. Keep the supporting rationale, parent identity, and DOI-specific corrections with these records. An enumerated condition is not itself a reported experiment.

The split groups precursor, linker, and solvent identities under the configured settings. This is not a DOI-disjoint split. The forced benchmark conditions and their cluster exclusions are recorded separately. Publication-year subsets are produced from training records; they are not automatically separate prospective test sets.

The archived negative `stage 6_v3` snapshot is distributed with scientific values preserved and four local-path columns omitted in `data/processed/revised/`. The archived configuration uses that exact table. The ordinary configuration connects to newly generated negative stage-6 output and records its provenance separately. A new curation run should not be assumed identical to the archived snapshot.

## Remaining research inputs

- Saved positive extraction CSV/JSONs, negative plans, and enumerated records for comparison against a completed run.
- Training-job records connecting the archived dataset versions and training settings to the model IDs already recorded in the evaluation configurations.
- Complete saved predictions and the figure/table mapping for the paper-associated release.

Offline software checks do not establish extraction accuracy or reproduce model-training results. See [evaluation](evaluation.md) for the available holdout and question-panel analyses. Separate positive and negative extraction-evaluation workflows require their reference data and scoring code.
