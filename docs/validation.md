# Triage validation

Validation performed on 21 September 2026 used a fresh Linux environment with Python 3.12.14. Installation of the source checkout and the `triage` dependency group completed successfully.

| Check | Result |
| --- | --- |
| Offline regression tests | 23 passed |
| Small example | 12 papers; 9 Y and 3 N; zero missing abstracts |
| Full reference coverage | 478 of 478 abstracts available in 13,773 metadata rows |
| Reference distribution | 293 Y and 185 N |
| Reference file identity | Byte-identical to the source annotation workbook |
| Shared helper functions | All 11 original function syntax trees preserved |
| Prompt and model defaults | Preserved from the consolidated notebook |
| Notebook source | All code cells compile, including notebook-level await |
| Optional walkthrough and example notebook cells | Executed successfully in process with OpenAI imports blocked |
| Saved-run analysis | All 17 CSV outputs exactly match the original notebook in a controlled comparison |
| Figure data | Coordinates, intervals, labels, axes, and table entries match across 14 figures |
| Screening requests and parsing | 68 controlled request/response cases match the original notebook |
| Resume | Completed runs dispatch zero requests; interrupted runs dispatch only unrecorded requests |
| Python command-line analysis | Saved-run analysis completed without Jupyter or API requests |
| Live model screening | Not executed |
| Interactive kernel session | Not established in the local validation environment |

The local environment prohibits TCP and IPC socket binding, which prevents Jupyter kernel startup through `nbconvert`. This limit does not affect the command-line functions or in-process cell checks. Normal kernel execution is included in the Windows/Linux GitHub Actions workflow; consult the status for the commit being used.

Controlled responses were used only for software checks. They are not model-performance results and are not part of the benchmark archive. No API key or live model request was used.

The direct comparison used the original notebook, the 478-paper reference, three configurations, and two rounds. It included missing and invalid answers, an unavailable configuration, a stale CSV checkpoint, and changes between the saved and current reference. Every value in the 17 CSV outputs matched, including 2,868 per-publication rows. Statistical comparisons used 2,000 bootstrap draws with seed 42; the distributed defaults remain 50,000 draws and seed 42. Figure checks compared plotted values and text, not rendered file bytes.

The complete screening loop matched the original 37 recorded attempts in a controlled fixture. Resume retained five interrupted-run records and dispatched the remaining 32 requests. Tests also check that changed settings, duplicate requests, and invalid saved round numbers are rejected before dispatch.

## Statistical preservation

The human reference contains four ambiguous ratings and 474 complete four-binary-rating rows. Independent calculations agree with the Python functions:

| Statistic | Estimate |
| --- | ---: |
| Pairwise agreement using available binary ratings | 0.8445378151 |
| Fleiss' kappa using complete four-binary-rating rows | 0.6370698296 |
| Krippendorff's alpha using available binary ratings | 0.6357571452 |
| Four-rater unanimity | 338 / 478 |

These statistics describe the human reference workbook. Model classification performance requires actual saved predictions.

## Environment snapshot

The complete tested dependency snapshot is in [`docs/environments/triage-linux-py312.txt`](environments/triage-linux-py312.txt). It describes the Linux Python 3.12 validation environment; the portable dependency groups remain in `pyproject.toml`.

| Package | Tested version |
| --- | --- |
| NumPy | 2.5.3 |
| SciPy | 1.18.1 |
| Matplotlib | 3.11.2 |
| OpenAI Python client | 3.16.2 |
| IPython | 9.17.1 |
| JupyterLab | 4.6.4 |
| nbconvert | 7.17.1 |
| nbformat | 5.11.1 |
| nbclient | 0.11.0 |

To recreate that dependency environment on Linux with Python 3.12:

```bash
python -m pip install -r docs/environments/triage-linux-py312.txt
python -m pip install --no-deps -e .
```
