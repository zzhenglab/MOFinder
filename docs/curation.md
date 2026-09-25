# Synthesis record curation

The curation package normalizes positive synthesis records and enumerated negative records through separate cleaning branches. Each branch applies chemical mappings, record filters, amount conversions, and derived descriptions. The sequence is implemented in [curation/pipeline.py](../src/mofinder/curation/pipeline.py); [the cleaning demo](../Demo/01_data_cleaning/README.md) provides a small run with expected-output checks.

## Inputs

`configs/curation.json` resolves paths relative to its `project_root`:

| Input | Default location |
| --- | --- |
| Positive extraction | `results/extraction/positive/mof_extraction.csv` |
| Enumerated negative extraction | `results/extraction/negative/mof_extraction_failures_enum.csv` |
| Linker molecular weights | `data/organic_linker_info/linker_molecular_weights.csv` |

The molecular-weight table is a UTF-8 CSV with **no header**, containing linker name and molecular weight in g/mol. Quote names that contain commas. Names are matched case-insensitively after stripping whitespace. Numeric molecular weights must be positive and finite; conflicting duplicate numeric weights are rejected. A blank weight indicates an unresolved value and remains blank.

The source lookup is preserved byte-for-byte as `data/organic_linker_info/linker_molecular_weights.csv`. It contains 591 rows: 217 with numeric weights and 374 with blank weights. Case-insensitive matching gives 210 names with known weights and 372 names without weights. Repeated names have consistent values. The lookup manifest records its source identifier and SHA-256 hash.

The workflow requires the molecular-weight table before creating outputs. For names absent from the table or present with a blank weight, mass-unit records remain unconverted and are removed by the final linker-unit filter. Reported molar amounts do not require a lookup weight. Validation reports known and unresolved lookup counts; the linker-stage report also counts mass-unit records without a molecular weight.

## Run

```bash
python -m pip install -e ".[curation]"
python -m mofinder.curation validate-inputs --config configs/curation.json
python -m mofinder.curation run --config configs/curation.json --mode both
```

Validation is read-only and exits with status 1 when inputs are missing or invalid. Run one branch with `--mode positive` or `--mode negative`. Run one operation with `--stage initial`, `metals`, `linkers`, `solvents`, `features`, `connectivity`, or `descriptions`.

```bash
python -m mofinder.curation run --mode positive --stage linkers
python -m mofinder.curation report --mode positive
```

Each operation reads the preceding stage's configured output. It does not search the working directory for a newer or similarly named CSV. The `connectivity` operation updates the stage-5 intermediate file, matching the original sequence. Other operations write distinct CSVs; extraction inputs remain unchanged. If an intermediate stage removes every record, the pipeline saves that stage's empty table and stops with a message identifying the stage.

Text reports are saved under each branch's `reports/` directory. `--no-reports` suppresses them. `--plots` additionally saves initial-stage histograms as PNGs; plotting requires the `plotting` extra and does not open a window. The standalone report produces summary counts and metal-linker coverage CSVs from the completed description table. The same reporting function can also describe the negative table.

## Operations and outputs

Positive output names start with `mof_extraction`; negative names start with `mof_extraction_failures_enum`. Files are saved under `results/curation/positive/` and `results/curation/negative/`, respectively.

Stage outputs and the bundled processed CSVs use UTF-8 with a byte-order mark (`utf-8-sig`) for spreadsheet compatibility. This preserves Unicode characters such as the hydrate separator in `Cu(NO3)2·1H2O`. When reading CSVs with Python's `csv` module, open them with `encoding="utf-8-sig"` to exclude the byte-order mark from the first column name.

| Operation | Suffix | Behavior |
| --- | --- | --- |
| `initial` | `_1.csv` | PDF availability and flag filters, required fields, linker aliases, temperature and time handling, precursor cleanup, topology and pore fields |
| `metals` | `_2.csv` | Precursor formulas and hydrates, amount-text parsing, molar conversions, precursor and unit filters |
| `linkers` | `_3.csv` | Branch-specific aliases, shorthand exclusions, linker MW conversion, retained mmol/equivalent units |
| `solvents` | `_4.csv` | Solvent names and abbreviations, mixture/volume inference, supported mass-to-volume conversions |
| `features` | `_5.csv` | Metal:linker ratio and integer metal concentration in mM |
| `connectivity` | Updates `_5.csv` | Classified connectivity next to the original text |
| `descriptions` | `_6.csv` | MOF description and derived metal information |

The original `metel_concnertation` spelling remains part of the CSV schema because dataset preparation consumes that column. Concentration uses the primary metal amount in mmol and the main-solvent volume in mL, multiplied by 1000 and rounded to an integer. The ratio uses the primary metal and linker values when the reported reagent units satisfy the original mmol checks; an explicit `1:1` amount-text fallback is retained.

Each completed branch writes `curation_manifest.json` with input and lookup SHA-256 hashes, operation paths and row counts.

## Reaction-time text

Both branches use `mofinder.curation.times` in the initial stage. Reported numeric `time_h` values remain unchanged. Missing or nonnumeric values are resolved from supported phrases in `time_h`, then `time_text`; the original `time_text` is retained.

| Phrase | Hours |
| --- | --- |
| `overnight`, including within a sentence | 12 |
| `48–72 h`, `48-72 hours`, `48 h to 72 h` | 72 |
| `12–24 h (stirred)` | 24 |
| `to 72 hours` | 72 |
| `2–4 days` or `2 to 4 days` | 96 |
| `2–4 weeks` or `2 to 4 weeks` | 672 |
| `2–4 months` or `2 to 4 months` | 2880 |
| `several days` or `serval days` | 144 |
| `several weeks` or `serval weeks` | 432 |
| `several months` or `serval months` | 2160 |
| `immediate` or `immediately`, with no number in the text | 0.1 |

Ranges accept hyphens, en dashes, em dashes, and `to`; the upper duration is used. Numeric conversions use 24 hours per day, 168 hours per week, and 720 hours per month. The qualitative mappings above are fixed conventions. Supported numeric ranges take precedence over qualitative phrases. Other text remains unresolved. The run manifest records `time_parser: duration-phrases-v1`.

## Positive and negative differences

| Rule | Positive | Negative |
| --- | --- | --- |
| Temperature text | Excludes text containing `microwave`, `evaporation`, or `slow` | Excludes microwave, evaporation, and slow diffusion; retains slow cooling |
| Pore-diameter outliers | Clears values above twice the mean | Clears values above the 99th percentile, with the original fallback |
| Linker aliases | Larger manual map | Smaller manual map |
| Description connectivity | Classified connectivity | Original connectivity text |
| Description metal parsing | Full metal names before formula tokens; abbreviation fallback | Formula tokens before metal-name lookup |

The two branches retain these distinct rules. In both branches, `h3btb` and `H3BTB` now map to `1,3,5-Tris(4-carboxyphenyl)benzene`. The initial normalization and linker-stage normalization use this corrected identity. Case-insensitive lookup resolves the lookup value of 438.4 g/mol. The run manifest records `linker_alias_revision: h3btb-tris-carboxyphenyl-benzene-v1`.

### Publication-specific prime restoration

`linker_prime_corrections` in `configs/curation.json` points to [167 documented spellings](../data/organic_linker_info/linker_prime_corrections.json) restored from intact same-publication records. The linker stage applies each rule only when the DOI and entire linker name or abbreviation match. Single, double, triple, and quadruple primes are distinguished. Missing or null configuration disables this lookup. The run manifest records the correction file and its SHA-256 hash.

The [corrected processed negative table](../data/processed_data/linker_corrected/README.md) changes only the supported linker fields. `configs/dataset_preparation_corrected.json` creates fresh grouped partitions under `results/datasets/corrected_conditions/`. The processed inputs and final training/holdout files remain available for reproducing the original runs. Corrected names must be grouped again because linker spellings contribute to cluster identity.

The Python mass parser corrects two related formula parsing errors found in the notebooks. A leading coefficient now multiplies the complete dot-separated fragment, and square brackets remain intact during abbreviation expansion. Thus `6H2O` contributes H12O6, fractional hydrates are handled consistently, and bracketed complexes can be parsed.

For example, using the source atomic weights, `Zn(NO3)2·6H2O` has a calculated molecular weight of 297.4762 g/mol; the notebook parser returned 217.4812 g/mol because it did not multiply the hydrate oxygen. Newly regenerated metal amounts, derived ratios, and concentrations can therefore differ for affected mass-based records. Already reported mol/mmol amounts are unaffected by this formula-mass correction. The bundled processed CSVs are not rewritten. The run manifest records `mass_parser: whole-fragment-coefficients-v2` to distinguish regenerated results.

## Prepare final JSONL

After curation, `configs/dataset_preparation_from_curation.json` reads the completed positive and negative description tables. Validate them and prepare the training/holdout files with:

```bash
python -m mofinder.datasets.prepare validate --config configs/dataset_preparation_from_curation.json
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation_from_curation.json
```

The default `configs/dataset_preparation.json` instead reads the bundled `processed_positive.csv` and `processed_negative.csv` in `data/processed_data/` and can run without repeating curation. See [dataset preparation](datasets.md) for split settings and the expected bundled-data counts.

## Verification

An earlier offline comparison ran the original notebook operations and the Python functions on the same 52-row controlled fixture for each branch. All 15 corresponding intermediate/final and positive coverage-report CSVs were byte-identical. The fixture covered missing PDF paths, invalid flags, temperature exclusions, linker aliases and units, precursor forms, solvent amounts, pore outliers, connectivity, and topology codes. This comparison predates the formula, alias, and time changes described above.

The curation tests check branch-specific rules, anhydrous and hydrated precursor mass conversion, fractional hydrates and bracketed formulas, linker mass/molar/equivalent units, solvent density conversion, ratio/concentration units, descriptions, explicit paths, and lookup validation. They also check both routes through the corrected `h3btb` mapping, case-insensitive resolution against the reference lookup, and handling of unresolved molecular weights. Time tests cover the supported phrase conventions, numeric-value precedence, and both cleaning branches. The unchanged-rule comparison is separate from the documented formula, alias, and time changes. Corrected element counts and molar masses are checked against explicit stoichiometry using the original atomic-weight table.
