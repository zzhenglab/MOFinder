# Dataset preparation

`mofinder.datasets.prepare` turns processed positive and negative records into final condition-classification JSONL, publication-year training subsets, and split records. The default configuration uses the bundled CSVs and publication metadata in [data/processed_data](../data/processed_data/README.md). The prepared research files and their assignments are together in [data/final_json](../data/final_json/README.md).

```bash
python -m pip install -e ".[datasets]"
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

`validate` reads inputs and reports missing files, column requirements, and input provenance without creating outputs. `prepare` runs the configured split and writes to `results/datasets/conditions`. Use `--output-dir` to select another run directory. Each run should have its own directory so files from an earlier year-bin configuration cannot be mistaken for current outputs.

The implementation is in [datasets/prepare.py](../src/mofinder/datasets/prepare.py). For a small example with expected outputs, use [the dataset preparation demo](../Demo/02_dataset_preparation/README.md).

## Input selection

Paths are relative to `project_root` in [dataset_preparation.json](../configs/dataset_preparation.json).

| Input | Default | Role |
| --- | --- | --- |
| Processed positive CSV | `data/processed_data/processed_positive.csv` | Successful syntheses, labelled P |
| Processed negative CSV | `data/processed_data/processed_negative.csv` | Enumerated unsuccessful conditions, labelled N |
| Publication metadata | `data/processed_data/publication_years.csv` | DOI-to-year mapping |
| Reaction-prediction prompt | `prompts/training/reaction_prediction.txt` | System message in every example; shared with MOF Quest evaluation and HPC training |
| Benchmark conditions | `configs/dataset_forced_questions.json` | 22 question inputs reserved for holdout when matched |

After running curation on new extraction records, select the configuration for those generated outputs:

```bash
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation_from_curation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_from_curation.json
```

This reads the positive and negative description-stage CSVs under `results/curation/` and writes a separate run to `results/datasets/curated_conditions/`.

For the source-confirmed linker corrections, use `configs/dataset_preparation_corrected.json`. It reads `data/processed_data/linker_corrected/processed_negative.csv` with the same processed positive table and writes to `results/datasets/corrected_conditions/`. Linker corrections change cluster identities, so this version calculates new assignments.

A run from newly extracted or curated records is a new dataset and can produce different split assignments. Each run records its input notes and SHA-256 hashes in the summary. The default bundled inputs retain the scientific values used for the original research dataset.

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

Publication-year bins use training rows only and keep whole years together. Fewer distinct years produce fewer bins. Records without a publication year remain in full training and holdout but are excluded from year subsets. Source row IDs are zero-based in the original positive-then-negative concatenation before filtering.

These files support training-history comparisons against the existing holdout. They do not define a future-year test partition. A chronological evaluation needs explicit cutoff years, publication/parent grouping rules, and separate dated train/test assignments. The current preparation command produces one training partition and one holdout partition; it does not create an additional independent test set.

All seeded sampling, search order, shuffling, and year-bin construction follow the source notebook. JSONL outputs were compared with the original notebook on controlled fixtures for both P:N modes. Automated tests cover cluster separation, forced conditions, label conflict handling, exact ratios, deterministic output, training-only year subsets, and infeasible input partitions. No training API requests are made by this module.

## Processed input validation

Using `processed_positive.csv`, `processed_negative.csv`, and the included publication metadata, the Python module produced all 16 JSONL files and the class map byte-for-byte identically to the source notebook.

| Partition | P | N | Total |
| --- | ---: | ---: | ---: |
| Original inputs | 15,340 | 15,063 | 30,403 |
| Training | 11,968 | 11,560 | 23,528 |
| Holdout | 1,320 | 1,275 | 2,595 |

The final training and holdout P:N ratio is 88:85. The retained split has zero shared clusters and **864 shared DOIs**. One holdout row lacks a publication year. These results describe the bundled processed inputs; fresh extraction and curation can change them.

The implementation also adds explicit failure messages for infeasible splits and handles the case where all selected holdout clusters are forced. Those changes affect edge cases in which the original notebook failed; they did not alter the final outputs above.

## Final JSONL and split records

The final training and holdout records are available at `data/final_json/train.jsonl` and `data/final_json/holdout.jsonl`. Their hashes exactly match the corresponding original preparation outputs. The same folder contains `split_assignments.csv`, `split_summary.json`, `class_map.json`, and `manifest.json`; see [the file guide](../data/final_json/README.md). Regenerating from `configs/dataset_preparation.json` reproduces both JSONL files byte for byte. The four removed local-path columns in the processed public tables do not affect any condition input, cluster key, or DOI mapping across all 30,403 rows.

The bundled records retain their original scientific values. New curation runs use `h3btb` → `1,3,5-Tris(4-carboxyphenyl)benzene` and the reference molecular-weight lookup. These curation changes do not rewrite the bundled training and holdout files.
