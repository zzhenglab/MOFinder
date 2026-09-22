# Mining and dataset validation

Offline checks compare the Python workflows with the recorded source notebooks. Source filenames, hashes, and active cell indices are recorded in [workflow_sources.json](workflow_sources.json); comparison results and expected dataset hashes are in [workflow_validation.json](workflow_validation.json).

The tables below preserve the original mining-integration checkpoint. Test totals and environment limitations belong to that checkpoint, rather than the current suite. Later documented changes include the shared reaction-prediction prompt path, consolidated API demo, and notebook display improvements; see [CHANGELOG.md](../CHANGELOG.md).

## Execution evidence

| Check | Result |
| --- | --- |
| Mining validation checkpoint | 107 tests passed at that stage, including triage and literature retrieval; the expanded evaluation suite is recorded separately |
| Active prompt strings | All five positive, negative, and classification strings match their source values exactly |
| Document matching | 26 controlled rows, six fields, and four presence groups match the original notebook |
| Optional document counts | Six controlled cases and six columns match the original, including SI preference and missing/non-PDF behavior |
| Positive extraction | Original schema and 83-column flattening preserved; 18 direct source comparisons |
| Negative reconstruction | Original schema and five flattening comparisons; eight enumeration cases, 138 rows, and their JSON payloads match |
| Curation | 15 unchanged-rule CSVs match byte for byte on 52-row fixtures for each branch; formula corrections checked separately |
| Dataset preparation | All 16 JSONL outputs and class map match byte for byte on the archived cleaned snapshots; both balancing modes additionally compared on controlled inputs |
| Walkthroughs | All five downstream notebooks execute from the repository root and notebook directory with model imports blocked and mining, curation, and dataset-preparation switches disabled |
| Included PDFs | Matched successfully and embedded text read locally; original bytes retained |
| Publication years | CSV export yields the same 13,770 DOI/year mappings as the original workbook |

Notebook execution used code cells in process. Notebook format validation also passed. GitHub Actions is configured for kernel-based walkthrough execution and offline tests on Windows/Linux; the checks reported here were performed locally. Optional token counting was compared on controlled inputs; the validation environment did not include `tiktoken` for an actual token-count run.

## Archived dataset results

These counts describe dataset preparation from the exact archived inputs and original split settings, not a fresh extraction or a new model-performance evaluation.

| Partition | Positive | Negative | Total |
| --- | ---: | ---: | ---: |
| Input snapshots | 15,340 | 15,063 | 30,403 |
| Training after filtering and balancing | 11,968 | 11,560 | 23,528 |
| Holdout after filtering and balancing | 1,320 | 1,275 | 2,595 |

Both final partitions have P:N = 88:85. Their chemical-cluster overlap is zero, while 864 DOIs occur in both partitions. The split groups precursor/linker/solvent combinations and permits different clusters from one paper in different partitions.

## Documented corrections

Operational changes prevent duplicate-DOI write races, stale or mismatched JSON parents, blank-document model requests, silent missing-lookup filtering, and empty-table crashes. New negative plans retain the exact ordered successful-synthesis list presented to the model and verify its saved identity during enumeration. The curated exclusion is applied independently of logging verbosity.

Metal formula parsing now applies leading coefficients to whole hydrate fragments and preserves bracketed groups. The original parser undercounted hydrate oxygen and could reject bracketed complexes. The source atomic-weight table is retained; corrected stoichiometry and numerical differences are recorded in the validation JSON. Regenerated amounts and derived features can change for affected records. The scientific values in the archived cleaned snapshots and the dataset reproduction comparison remain unchanged; public CSV exports omit four local-path columns.

See the [positive](positive_extraction.md), [negative](negative_extraction.md), [curation](curation.md), and [dataset](datasets.md) guides for the complete behavior and compatibility notes.

## Validation limits

No live model requests, browser downloads, or training jobs were performed. Schema preservation and offline equivalence do not establish extraction accuracy. The demonstration PDFs contain hypothetical negative outcomes and are kept separate from research data. The revised linker molecular-weight lookup is now included. Full upstream reproduction still needs the original extraction stores. New curation uses the confirmed H3BTB identity; source-specific DOI corrections retain their documented rationale.
