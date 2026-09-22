# Literature retrieval validation

The article and SI downloaders use neutral publisher identifiers in code, configuration, and image filenames. The checks below cover inventory handling and browser-action logic without opening a browser or controlling the desktop.

This report preserves the original literature-retrieval integration checkpoint; its test count and package versions are historical, not a report of the current full suite.

## Input and asset checks

| Check | Result |
| --- | --- |
| Article inventory | 7,437 source rows retained, including two duplicate DOI rows |
| SI inventory | 7,437 source rows retained, including two duplicate DOI rows |
| Recorded status fields | Preserved independently for each source workbook |
| Publisher assignments | Original per-stage matching results retained as neutral IDs |
| Image templates | 48 renamed files, all byte-identical to the source images (47 from the original archive and one additional capture) |
| Publisher W SI entry template | `publisher_W_SI_1.png` included unchanged |
| Missing optional SI template | `publisher_S_SI_Accept2.png` |
| Documents | Research downloads remain local; demonstration PDFs are documented in `Demo/03_api_demo/inputs/mining/README.md` |
| Calibration | Calibration starts without coordinates or workstation-specific paths |

The article inventory has 422 blank-status rows, of which 412 remain `unmapped` under the original matching rules. The SI inventory has 475 blank-status rows, of which three are `unmapped`. The downloaders require explicit supported profile IDs for these rows. Review neutral profile assignments in a working copy before scheduling affected records.

## Offline execution checks

The literature retrieval validation checkpoint passed 41 repository tests, including 18 literature retrieval tests. Tests cover inventory status strings, local-copy preservation, numeric image ordering, retries, blank/zero/one selection, SI skips, journal failure thresholds, and the five-row SI test limit. GUI modules and browser actions were blocked or replaced by controlled objects during these checks.

Both `--help` and `--validate` run without a desktop session. Validation did not modify either archived inventory and did not create calibration, settings, or downloaded-document files.

Direct comparisons with the source notebooks matched 210 SI action traces and 168 article action traces across successful, failed, and fallback paths. The five SI profile flows and three core article action functions retain the same syntax trees after neutral identifier substitution.

The literature retrieval tests used Python 3.12 with pandas 2.2.3 and openpyxl 3.1.5. The triage checks also passed in the same test run. Windows/Linux CI includes both literature retrieval input checks; its execution status must be checked on the published commit.

## Operational changes

- Main execution is guarded, so importing a module does not open the GUI or browser.
- Paths and timing settings are read from `configs/literature_retrieval.json`.
- CSV and XLSX inventories are supported, and status values are read as strings.
- Selecting an inventory creates or reopens a local working copy before status updates.
- Screen calibration starts without coordinates and is saved separately on each computer.
- The SI five-row test control now enforces its limit; the original control was unused.
- Moving the pointer to a screen corner stops automation through the existing broad exception handlers.

The publisher action sequences, image order, retry counts, journal thresholds, and SI status-selection rules were retained. Normal literature retrieval processes blank states; existing success/failure states are not automatically reset. SI double-check mode processes zero states only.

## Desktop verification still needed

Live page layouts, image matches, browser download settings, institutional access, and save-dialog coordinates were not tested. The original workflow closes Chrome windows during literature retrieval, so it should run in a dedicated desktop session. The Publisher W SI entry template has not yet been checked against a live page.

No literature retrieval success rate is inferred from stored workbook flags or offline software checks. The recorded flags describe the archived inventory snapshots.
