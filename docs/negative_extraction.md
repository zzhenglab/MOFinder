# Negative-condition plans and enumeration

The negative stage starts from the article and supporting-information manifest,
the positive extraction CSV, and the stored successful synthesis JSON files. It
produces literature-guided modification plans, then expands their option lists in
a separate step.

These outputs have different meanings. A plan records the model's proposed
alternatives, rationale, and evidence notes. The preserved prompt permits both
explicitly reported failures and several forms of inference. Enumeration takes
the Cartesian product of those alternatives. An enumerated combination is a
reconstructed condition, and does not establish that the combination was tested
or failed experimentally. For example, two solvent options and two temperature
options produce four combinations even if the paper never tested all four.

## Inputs and configuration

Edit `configs/negative_extraction.json`. Its paths are resolved relative to
`project_root`, so the commands can run from any working directory when given an
absolute configuration path.

| Input | Default path or required fields |
| --- | --- |
| Document manifest | `results/extraction/document_manifest.csv`; `DOI`, `Main File`, `SI File` |
| Positive extraction | `results/extraction/positive/mof_extraction.csv` |
| Successful syntheses | `results/extraction/positive/mof_json_store/<DOI>/synthesis_001.json` and subsequent indices |
| System prompt | `prompts/negative_system.txt` |
| Article prompt template | `prompts/negative_user.txt` |
| Manual enumeration corrections | `configs/negative_corrections.json` |

CSV and XLSX document manifests are supported. Use the absolute document paths
written by the matching stage. The positive CSV must include `doi`,
`article_trial_or_failure`, and `article_trial_or_failure_notes`. The optional
trial summary additionally retains `main_pdf`, `si_pdf`, `raw_output`, and
`parsed_json`, all written by the positive extractor.

The default model is `gpt-5`, with reasoning effort `medium` and
40 concurrent papers. Both prompt files contain the active extraction instructions. Set `OPENAI_API_KEY`
in the process environment before starting model calls.

PDF extraction uses `pypdf`; DOCX support uses `python-docx`. DOC
support requires an optional `textract` installation. Text
extraction errors return an empty string, so inspect
input validation and document readability before mining. Each article and SI
text is truncated independently to 400,000 characters, and the indexed success
list to 300,000 characters.

## Run the stage

```bash
python -m mofinder.extraction.negative validate --config configs/negative_extraction.json
python -m mofinder.extraction.negative mine --config configs/negative_extraction.json --dry-run
python -m mofinder.extraction.negative mine --config configs/negative_extraction.json
python -m mofinder.extraction.negative enumerate --config configs/negative_extraction.json --dry-run
python -m mofinder.extraction.negative enumerate --config configs/negative_extraction.json
```

Validation reports missing inputs, missing document paths, eligible papers,
missing successful bases, and papers marked `yes` without accompanying notes.
Both dry-run commands only inspect local inputs and list the selected work.
The [API demo](../Demo/03_api_demo/README.md) uses these functions for a small
interactive run and preserves its positive records, plans, and enumerated outputs.

Mining selects only DOIs marked `yes` in the positive CSV, ignoring whitespace
and case in that flag, and deduplicates DOIs in manifest order. The source rule
that sets the plan CSV's `article_trial_or_failure` flag only when notes are
nonempty is preserved. Consequently, a paper marked `yes` with empty notes can
be mined but is excluded by the default YES-only enumeration gate. Validation
reports these papers explicitly; inspect their positive extraction before
continuing.

The six editable classes are `metal_1`, `linker_1`, `modulator_1`, `solvent_main`,
`temperature_c`, and `time_h`. Empty option lists retain the successful base's
fields. A plan with no options produces a tracking row but is not enumerated.
The original Cartesian product order and CSV columns are retained. Other
properties, including structure and yield fields, are copied from the successful
parent for continuity; they are not measurements of the reconstructed condition.

## Outputs and parent identity

Outputs are written under `results/extraction/negative/`:

| Output | Contents |
| --- | --- |
| `mof_extraction_failplans.csv` | One row per successful base with options, plus empty or failed tracking rows |
| `mof_negative_plan_store/<DOI>/` | Raw response, complete `paper_plan.json`, individual `plan_001.json` files, `success_bases.json`, and its `plan_provenance.json` hash record |
| `mof_trials_yes_7.csv` | Deduplicated positive extraction records carrying trial or failure notes |
| `mof_extraction_failures_enum.csv` | One row per reconstructed combination |
| `mof_negative_enum_store/<DOI>/base_001/combo_0001.json` | Modified synthesis, parent index, and changed classes |
| `plans_metadata.json`, `enumeration_metadata.json` | Resolved configuration, prompt hashes, correction rules, and output interpretation |

The source miner sorts successful JSON files and removes duplicate JSON strings
before assigning 1-based indices. `success_bases.json` saves that exact ordered
list, and enumeration uses it to identify the parent. This avoids selecting the
wrong numbered source file when duplicates, missing files, or unreadable files
change the list. A missing, changed, or invalid recorded snapshot, or an index outside that list, raises an
error; enumeration does not silently substitute another parent. Plans generated
without any successful bases retain the original text-only prompt fallback,
but record an empty snapshot and cannot be enumerated until the successful bases
and plans have been regenerated. Legacy plans without a snapshot retain the
original numbered-file and article-JSON fallback behavior.

## Corrections and resume behavior

`configs/negative_corrections.json` records every manual rule from active cell 3
of the revised notebook, including provenance and the rationale available there:

| DOI | Retained rule |
| --- | --- |
| `10.1021/acsmaterialslett.0c00456` | Exclude because the notebook marks synthesis information as missing |
| `10.1002/chem.201802189` | Exclude base 2; retain the first half of metal and linker options, rounded up; set base 1 temperatures to 80 and 140 °C and time to 12 h |
| `10.1039/b713705b` | Set the temperature options for bases 1 and 2 to 100 °C; retain other option classes |

The exclusion of `10.1002/chem.201802189` base 2 applies with logging either
enabled or disabled. Set `enumeration.corrections_file` to `null` to enumerate
without the manual corrections.

Default mining resume behavior skips a DOI present in either its plan CSV or
plan JSON artifacts, including recorded failures. Explicit reruns use
`force_rerun` and `update_in_place`; the selected DOI's old CSV rows are removed
before rerunning, including when `skip_if_plan_csv_exists` is disabled. An
unreadable existing plan CSV stops mining before any model requests; it is not
treated as an empty history. Enumeration skips any DOI/base pair already present in the
output CSV, and retains the source default of ignoring existing combination JSON
files for this decision. This is artifact-based resume behavior: a pair found in
a partially written CSV is not independently checked for complete enumeration.
Use a fresh output directory when regenerating combinations after changing
plans or correction rules.

## Validation

Local tests cover model request construction with a mock client, YES-only
selection, empty notes, exact prompt hashes, parent snapshot integrity,
Cartesian product ordering, preserved parent fields, manual overrides,
verbosity-independent exclusions, resume behavior, and dry runs without writes.
An independent comparison with the active source notebook matched both prompt
strings, the complete Pydantic schema, five plan-flattening cases, and eight
enumeration scenarios producing 138 rows and matching JSON payloads. No live
model requests were used for this validation.
