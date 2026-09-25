# Remaining workflow tasks

Python modules and Markdown guides cover the workflow from abstract triage through reaction and human-benchmark evaluation. The input datasets, molecular-weight lookup, sample PDFs, and anonymous human responses are included.

## Evaluation and training

| Task | Current status | Remaining inputs or work |
| --- | --- | --- |
| Positive extraction evaluation | Extraction and output schemas are implemented | Integrate the revised scoring code and corresponding ground-truth records |
| Negative reconstruction evaluation | Planning and enumeration are implemented | Integrate the revised scoring code and corresponding ground-truth records |
| Saved model results | Analysis commands are implemented; source notebooks contain result summaries | Add complete prediction CSVs and available run metadata for abstract triage, the reaction holdout, and the 22-question panel |
| Model training | GPT-4.1 dashboard recipe and single-dataset GPT-oss-20B GPU training are included | Validate GPU execution in the training environment and connect each evaluated model to its training settings, dataset hashes, and job record |
| Temporal evaluation | Publication-year metadata, four/five training-year bins, and cumulative training subsets can be generated | Finalize the future-year test protocol, cutoff years, and grouping rules; generate dated train/test assignments and evaluate the corresponding models |
| Publication outputs | Analysis modules and a preliminary figure/table map are included | Map final figures and tables to their saved inputs, configurations, and reproduction commands |

## Verification of the packaged workflow

- Run the Windows/Linux GitHub Actions checks on the release commit.
- Verify the packaged screening, extraction, and model-evaluation commands with small live runs using an account with access to the configured models.
- Check desktop literature retrieval on the target computer, including browser downloads, image matching, and local calibration.

These checks concern the packaged Python implementation. Completed runs in the original research notebooks are separate execution records.

## Full upstream reproduction

The data curation demo includes a subset of raw positive extraction records. Full upstream reproduction uses the complete positive extraction CSV and successful-synthesis JSON store, the negative plans, and the enumerated records before curation. The full positive CSV has been supplied separately; it is not distributed in the current repository. Processed positive and negative tables are included in `data/processed_data/` for dataset preparation. Research article and SI files remain local; demonstration PDFs are included for testing document matching and extraction. The [pre-upload checklist](preupload_checklist.md) gives the destination and required format for each input.

Before a whole-corpus literature retrieval or screening run:

- Resolve the three conflicting DOI groups in the bibliographic metadata. The 478-paper triage reference is unaffected.
- Assign supported neutral publisher profiles to unmapped pending literature retrieval rows.
- Add `publisher_S_SI_Accept2.png` only if the target browser encounters that optional cookie-button layout.

Blank molecular weights remain unresolved in the lookup and are reported during curation. Completing additional entries is optional and can change which mass-based records can be converted.

## Release preparation

Finalize the software citation and associated article metadata, select a version tag, and archive the code with the dataset, prompt, model, and prediction identities used for each published result. Saved model predictions are needed to reproduce the performance tables without repeating API requests.
