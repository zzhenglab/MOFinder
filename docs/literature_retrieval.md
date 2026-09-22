# Article and supporting-information literature retrieval

The literature retrieval tools are Python desktop applications that open article landing
pages, follow recorded browser actions, and save documents under DOI-derived
filenames. The article and supporting-information (SI) applications retain their
separate browser flows. They do not require Jupyter, an LLM prompt, or an API key.

The tools control the keyboard and mouse and close Chrome windows during
literature retrieval. Save any browser work and use a dedicated desktop session before
starting a download run.

## Install and inspect the inputs

From the repository root, install the dependencies for a local desktop run:

```bash
python -m pip install -e ".[fetch-gui]"
python tools/literature_retrieval/fetch_papers.py --validate
python tools/literature_retrieval/fetch_si.py --validate
```

For inventory and image-template checks without desktop automation, install
`.[literature-retrieval]` instead. The `--validate` commands read the selected input and
report row counts, download states, publisher profiles, and image availability.
They do not open a browser or modify files. `--help` lists the available options.

The default inputs are documented in
[the literature retrieval input tables](../data/metadata/literature_retrieval/README.md). Each CSV
retains all 7,437 rows and the download states from its source workbook. A saved
state does not establish that a document is present on the current computer.

The article input has 422 blank states, including 412 rows without a supported
publisher profile under the original matching rules. The SI input has 475 blank
states, including three unmapped rows. Review those assignments before a live
run. Assign a neutral profile only after checking the intended browser flow, and
make changes in a local input copy. The full routing counts and source-export
details are recorded in the input-table documentation linked above.

## Configuration and local files

[`configs/literature_retrieval.json`](../configs/literature_retrieval.json) defines separate
`papers` and `si` sections. Paths are resolved relative to `project_root`, which
defaults to the repository root. The `tuning` sections retain the original
timings, image-match thresholds, retry limits, and save intervals.

| Setting | Article default | SI default |
| --- | --- | --- |
| Input inventory | `data/metadata/literature_retrieval/papers.csv` | `data/metadata/literature_retrieval/supporting_information.csv` |
| Working inventories | `results/literature_retrieval/papers/inventories/` | `results/literature_retrieval/si/inventories/` |
| Calibration | `results/literature_retrieval/papers/calibration.json` | `results/literature_retrieval/si/calibration.json` |
| App settings | `results/literature_retrieval/papers/app_settings.json` | `results/literature_retrieval/si/app_settings.json` |
| Download directory | `data/local/articles/` | `data/local/supporting_information/` |

Both applications use `data/literature_retrieval_assets/icons/`. Download directories,
calibration, app settings, and working inventories are local outputs excluded
from version control.

Launching an application creates a working copy of its selected CSV or XLSX
under the configured inventory directory. The source path and source-file hash
identify that copy. Selecting the same unchanged source again resumes the same
working inventory; selecting an existing working file continues that exact file.
The Browse control and manually entered input paths follow the same rule. The
archived input is not updated by the application.

To select another inventory:

```bash
python tools/literature_retrieval/fetch_papers.py --workbook "path/to/paper_inventory.xlsx"
python tools/literature_retrieval/fetch_si.py --workbook "path/to/si_inventory.xlsx"
```

The inventory needs a `DOI` column and a `Publisher` column containing one of
`publisher_A`, `publisher_E`, `publisher_R`, `publisher_S`, or `publisher_W`.
An explicit `Publisher ID` column takes precedence over `Publisher`. The tools
do not infer a profile from the DOI or accept descriptive publisher names as
routing keys. Unsupported entries remain unmapped. The archived paper and SI
exports preserve the different routing rules used by the two source workflows.

## Calibrate the desktop

Calibration must match the current laptop, screen resolution, display scaling,
browser zoom, and window layout. The distributed configuration contains no
machine-specific coordinates. Calibration files from another computer are not
loaded as public defaults.

1. Open the application with the appropriate command below. Check the inventory
   path and configured download directory.
2. Open a representative article page for the relevant publisher profile. The
   article application's sample-page control can select a matching row from the
   inventory. The SI application's sample buttons use `sample_urls` entries in
   the configuration; set an HTTPS URL there or open a representative page
   manually.
3. Open a Save dialog. Select **Set FILE NAME box XY**, hover over the filename
   field, press **F8**, and press **F9** to finish. Both applications require this
   calibration before starting.
4. For articles, choose **Icon mode** for a profile with suitable templates, or
   use **Record actions** to capture its browser click sequence. Press **F8** at
   each action position and **F9** when finished. SI literature retrieval uses its
   configured image-template sequences.
5. Check that the templates match the current browser appearance. Re-capture
   templates when the page layout, screen scaling, or browser zoom changes.

Image names use neutral publisher identifiers. Renaming preserves the image
bytes and does not change their visible content. See
[the image-template inventory](../data/literature_retrieval_assets/README.md) for checksums
and flow references.

The required `publisher_W_SI_1.png` entry template is included. The optional `publisher_S_SI_Accept2.png` cookie-button alternative remains absent. Image matching still requires a compatible local browser appearance.

The [mining example](../Demo/03_api_demo/inputs/mining/README.md) includes DOI-named demonstration documents for checking the literature retrieval-to-extraction handoff.

## Download articles

```bash
python tools/literature_retrieval/fetch_papers.py
```

After calibration, select **Start**. The article application processes blank
`Downloaded` states. Recorded `1` and `0` states are retained and are not
scheduled again automatically. For a new literature retrieval, prepare a local inventory
copy and intentionally clear the states of the rows that should be downloaded.
Use a small selected inventory for the first desktop run.

## Download supporting information

```bash
python tools/literature_retrieval/fetch_si.py
```

After calibration, select **Start (block 2)**. Normal mode processes blank
`SI Downloaded` states. **Double check mode (only 0s)** retries recorded `0`
states. **Test mode (5 rows)** limits the selected pending rows to the first five
without reordering them.

**Sync from folder to inventory (block 1)** updates the working inventory from
the configured local SI directory. Use it when reconciling an existing local
download collection. The article and SI `Downloaded` fields originate from
separate workbook snapshots and are not merged; `SI Downloaded` controls SI
literature retrieval.

Both applications retain **Ctrl+Shift+S** to save progress and
**Ctrl+Shift+X** or **STOP now** to stop. Moving the pointer to a screen corner
also triggers the desktop automation fail-safe.

## Outputs and next stage

The applications update download-state columns in their local working
inventories and write downloaded files to the configured local directories.
Browser sequences, file-naming rules, and download detection follow the source
workflow. The SI test option limits execution to five pending rows; both
applications support pointer-corner interruption.

Research article and SI downloads remain local. The API demo's
[literature input folder](../Demo/03_api_demo/literature_input/README.md)
contains replaceable article/SI templates and a three-paper DOI inventory.
Document matching builds a DOI-to-file manifest from local documents before
positive extraction and negative reconstruction. The separate
[mining example](../Demo/03_api_demo/inputs/mining/README.md) contains demonstration PDFs.

Live Chrome literature retrieval remains to be validated on the configured desktop.
Offline validation and its limits are recorded in
[literature retrieval validation](literature_retrieval_validation.md). Remaining workflow tasks
are listed in [next stages](next_stages.md).
