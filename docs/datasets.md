# Condition classification datasets

`mofinder.datasets.prepare` creates condition-classification training JSONL, a held-out JSONL dataset, publication-year training subsets, and a split-assignment table. It does not start a fine-tuning job.

```bash
python -m pip install -e ".[datasets]"
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

`validate` reads inputs and reports missing files, column requirements, and input provenance without creating outputs. `prepare` runs the configured split and writes to `results/datasets/conditions`. Use `--output-dir` to select another run directory. Each run should have its own directory so files from an earlier year-bin configuration cannot be mistaken for current outputs.

The notebook [06_dataset_preparation.ipynb](../notebooks/06_dataset_preparation.ipynb) calls the same functions. Execution of preparation is disabled initially with `RUN_PREPARATION = False`.

## Input selection

Paths are relative to `project_root` in [dataset_preparation.json](../configs/dataset_preparation.json).

| Input | Default | Role |
| --- | --- | --- |
| Positive CSV | `results/curation/positive/mof_extraction_1_2_3_4_5_6.csv` | Successful syntheses, labelled P |
| Negative CSV | `results/curation/negative/mof_extraction_failures_enum_1_2_3_4_5_6.csv` | Enumerated unsuccessful conditions, labelled N |
| Publication metadata | `data/metadata/publication_years.csv` | DOI-to-year mapping |
| Reaction-prediction prompt | `prompts/training/reaction_prediction.txt` | System message in every example; shared with MOF Quest evaluation and HPC training |
| Benchmark conditions | `configs/dataset_forced_questions.json` | 22 question inputs reserved for holdout when matched |

For the archived inputs, use:

```bash
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation_archived.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_archived.json
```

This selects the public scientific-data exports in `data/cleaned_data/archived/` and writes a separate run to `results/datasets/archived_conditions`.

The source dataset notebook selected positive stage 6, before the optional positive stage 7 trimming. That choice is preserved. It named a negative `stage 6_v3` CSV, which is a separate prior input; current negative curation writes a stage 6 CSV. Set `negative_csv` explicitly to the historical snapshot when reproducing that run. A run from newly mined or curated data is a new dataset and can produce different split assignments. The input notes and SHA-256 hashes are recorded in its summary.

CSV and Excel publication metadata are supported; both must contain `DOI` and `Publication Year`. Duplicate metadata DOI entries use the modal valid year, with the lowest year resolving a tie. DOI recognition accepts canonical DOI strings, DOI URLs, and article/SI filenames such as `10.1021_jacs.2c09756_SI.pdf`.

## Input features and filters

Each JSONL record contains system, user, and assistant messages. The user message is a JSON object containing `metal_precursor`, `organic_linker`, `modulator`, `solvent`, `metal_concentration_mM`, `M_L_ratio`, `temperature_C`, and `time_h`. The assistant message is exactly `P` or `N`. The original classification prompt is preserved, including whitespace.

The feature builder uses the primary metal, up to three linkers, up to two modulators, and the main/secondary solvents. Full names take precedence over abbreviations. The original input column `metel_concnertation` is retained for compatibility with curation. Metal-to-linker ratios such as `1:1:1` become `1 / (1 + 1)`.

Records must include a metal, a linker, and a solvent. At least two of metal concentration, M/L ratio, and temperature must be parseable. Time and modulator can remain null. When identical classifier inputs have both labels, the default conflict filter removes the N records and retains the P records. Exact inputs are then deduplicated within each label, keeping the first record.

## Holdout and benchmark protection

The default cluster combines the primary metal **precursor**, the complete normalized linker set, and the complete normalized solvent set. Cluster key construction sorts reagent sets. Exact input keys and benchmark matching preserve the input's joined reagent order. Optional settings use metal element grouping or include modulators in the cluster.

For example, CdCl2 and Cd(NO3)2 form different precursor clusters even when the linker and solvent sets match. Element grouping merges those two salts into the same cluster.

A retained exact match to one of the benchmark's eight-field conditions forces its entire cluster into holdout. Matching ignores the benchmark reference label. One surviving record for each matched condition is protected during balancing. Unmatched questions are reported; their absence is not interpreted as successful holdout coverage.

The seed-42 search uses 64 restarts and 1,200 swaps per restart. It targets 10% of rows and 10% of clusters, with all forced clusters retained. These are targets, not guaranteed final proportions. The default `pn_mode: equal` downsamples to a common **exact P:N ratio** in both partitions while maximizing retention under the original integer-ratio search. The common ratio is not necessarily 1:1. The alternative `raw10` mode preserves the notebook's cost-based search toward the original P:N ratio within a 10% relative tolerance; this tolerance is an optimization target, not a hard acceptance gate.

Before writing outputs, the implementation checks that training and holdout share neither clusters nor exact condition inputs and that training contains no matched forced condition. Both partitions must contain P and N. A forced-only holdout is supported without attempting swaps from an empty optional set.

The split is **not grouped by DOI or by a successful synthesis parent**. Distinct clusters from the same article or enumeration parent may occur in different partitions. Precursor-based grouping also does not identify equivalent chemical aliases automatically. These limits should be considered when interpreting generalization results.

## Outputs

| File | Contents |
| --- | --- |
| `mof_ft_train.jsonl` | Full training set |
| `mof_ft_holdout.jsonl` | Cluster-disjoint holdout |
| `mof_ft_class_map.json` | P = success, N = failure |
| `mof_ft_split_assignments.csv` | Retained source row IDs, DOI, input/cluster keys, labels, and partition |
| `mof_ft_split_summary.json` | Filtering, balancing, coverage, counts, parameters, and input checksums |
| `mof_cls_train_<years>.jsonl` | Four contiguous year bins and cumulative bins 1–2 and 1–3 |
| `mof_cls_train_5periods_<years>.jsonl` | Five contiguous year bins and cumulative bins 1–2, 1–3, and 1–4 |

Publication-year bins use training rows only and keep whole years together. Fewer distinct years produce fewer bins. Records without a publication year remain in full training/holdout but are excluded from year subsets. Source row IDs are zero-based in the original positive-then-negative concatenation before filtering.

These files support training-history comparisons against the existing holdout. They do not define a future-year test partition. A chronological evaluation needs explicit cutoff years, publication/parent grouping rules, and separate dated train/test assignments. The current preparation command produces one training partition and one holdout partition; it does not create an additional independent test set.

All seeded sampling, search order, shuffling, and year-bin construction follow the source notebook. JSONL outputs were compared with the original notebook on controlled fixtures for both P:N modes. Automated tests cover cluster separation, forced conditions, label conflict handling, exact ratios, deterministic output, training-only year subsets, and infeasible input partitions. No training API requests are made by this module.

## Archived input validation

Using the archived stage 6 positive CSV, stage 6_v3 negative CSV, and original publication metadata, the Python module produced all 16 JSONL files and the class map byte-for-byte identically to the source notebook.

| Partition | P | N | Total |
| --- | ---: | ---: | ---: |
| Original inputs | 15,340 | 15,063 | 30,403 |
| Training | 11,968 | 11,560 | 23,528 |
| Holdout | 1,320 | 1,275 | 2,595 |

The final train/holdout P:N ratio is 88:85. The retained split has zero shared clusters and **864 shared DOIs**. One holdout row lacks a publication year. These results describe the archived inputs only; fresh mining and curation can change them.

The implementation also adds explicit failure messages for infeasible splits and handles the case where all selected holdout clusters are forced. Those changes affect edge cases in which the original notebook failed; they did not alter the archived outputs above.

## Archived training and validation files

The archived training and validation records are available together at `data/training/train.jsonl` and `data/training/holdout.jsonl`. Their hashes exactly match the corresponding original preparation outputs. The retained source rows, cluster assignments, and preparation summary are included in [data/splits](../data/splits/README.md). Regenerating from `configs/dataset_preparation_archived.json` reproduces both JSONL files byte for byte. The four removed local-path columns in the cleaned public tables do not affect any condition input, cluster key, or DOI mapping across all 30,403 rows.

The archived records retain their original scientific values. New curation runs use `h3btb` → `1,3,5-Tris(4-carboxyphenyl)benzene` and the reference molecular-weight lookup. These curation changes do not rewrite the archived training and validation files.
