# Installation

MOFinder requires Python 3.10 or newer. The workflows run from a source checkout through Python commands; Jupyter is optional. Input validation, saved-run analysis, and human-agreement calculations require no GPU or API key. Article and SI literature retrieval use an interactive desktop application with separately installed dependencies.

## Create an environment

Windows PowerShell, from the repository folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[api,plotting]"
.\.venv\Scripts\python.exe Demo/03_triage_extraction/mof_triage_extraction_demo.py triage
.\.venv\Scripts\python.exe -m mofinder.literature.triage --help
```

These commands use the environment directly and do not require PowerShell activation. Use `.\.venv\Scripts\python.exe` in place of `python` in the workflow commands while the environment is inactive.

Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[api,plotting]"
.venv/bin/python Demo/03_triage_extraction/mof_triage_extraction_demo.py triage
.venv/bin/python -m mofinder.literature.triage --help
```

Use `.venv/bin/python` in place of `python` while the environment is inactive. The [triage guide](triage.md) gives screening, resume, and analysis commands.

## Dependency groups

| Installation | Purpose |
| --- | --- |
| `pip install -e .` | Input validation, statistical analysis without figures, and human agreement |
| `pip install -e ".[api]"` | Add model screening |
| `pip install -e ".[plotting]"` | Add saved-run figure generation |
| `pip install -e ".[api,plotting]"` | Complete command-line triage workflow |
| `pip install -e ".[notebook]"` | Add Jupyter and plotting for local interactive analysis |
| `pip install -e ".[triage]"` | Complete triage environment, including the API client and Jupyter for demos |
| `pip install -e ".[legacy]"` | Dependencies for the earlier numbered scripts, available in the [historical repository tree](https://github.com/zzhenglab/MOFinder/tree/bb6502b669a027ad30a26668e621515756a52c5a) |
| `pip install -e ".[literature-retrieval]"` | Offline literature retrieval-inventory and image-template checks |
| `pip install -e ".[fetch-gui]"` | Complete desktop literature retrieval dependencies |
| `pip install -e ".[mining]"` | Document matching, positive extraction, negative reconstruction, and offline CSV recovery |
| `pip install -e ".[document-counts]"` | Optional PDF word/token counts and plots |
| `pip install -e ".[curation,datasets]"` | Data curation and dataset preparation |
| `pip install -e ".[evaluation]"` | Model evaluation on the holdout and question panel; human benchmark analysis |
| `pip install -e ".[all]"` | All declared optional dependencies |

Desktop literature retrieval also needs an interactive desktop, Tk, and calibrated browser controls. It is separate from triage installation. Submodule dependencies remain documented in their own repositories.

## Desktop literature retrieval

On Windows, install the desktop dependencies into the environment created above:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[fetch-gui]"
.\.venv\Scripts\python.exe tools/literature_retrieval/fetch_papers.py --validate
.\.venv\Scripts\python.exe tools/literature_retrieval/fetch_si.py --validate
```

Omit `--validate` to launch the corresponding application. On other systems, use
the environment's Python executable in the same commands. The desktop requires
Chrome, Tk, and permissions to control the mouse and keyboard. Calibrate and check the browser controls on the computer used for downloading.

The applications close Chrome windows during literature retrieval. Save browser work
before starting. Record the Save-dialog filename coordinates on the current
computer; article coordinate mode also needs the publisher-profile click
sequence. The SI application uses image templates. See
[literature retrieval](literature_retrieval.md) for the configuration, calibration, status rules,
and missing templates. No API credentials are used by these tools.

## API credentials

Set `OPENAI_API_KEY` in the environment before live screening or synthesis extraction. `.env.example` shows the variable name; the workflow does not automatically load an `.env` file. Offline commands do not use API credentials.

Check model settings and account access before scheduling a full run. Offline software checks cover request handling and response parsing; they do not verify live model access. Training instructions cover the [OpenAI interface](training_openai.md) and [HPC execution](training_hpc.md).

## Demo notebooks

The workflow commands and Markdown guides work without Jupyter. To view or rerun the saved demo notebooks, install the demo dependencies and open `Demo/` from the repository root:

```bash
python -m pip install -e ".[curation,datasets,mining,notebook]"
python -m jupyter lab Demo/
```

The notebooks call the same Python functions as the terminal workflow. Keep their saved outputs to inspect the recorded run, then execute the verification cells when rerunning. Live model calls in the API demo are disabled by default and must be enabled explicitly.

Select the same environment for the notebook kernel and for running `.py` files. In VS Code, **Python: Select Interpreter** controls script execution; the notebook's kernel selector is independent. An import that works in a notebook can still fail in a terminal using another Python installation. Register a named kernel from the installed environment if needed:

```bash
python -m ipykernel install --user --name mofinder-demo --display-name "Python (MOFinder demos)"
```

Use the environment's Python executable for that command. For the data curation and dataset preparation notebooks, also install `.[curation,datasets]`; for the combined API notebook, install `.[mining,notebook]`. On Windows, a short environment directory such as `%USERPROFILE%\.venvs\mofinder-demo` can avoid package-installation path-length errors in a deeply nested checkout.

## Offline verification

The full test suite covers more stages than the minimal triage installation. Install its dependencies before running all tests:

```bash
python -m pip install -e ".[triage,literature-retrieval,mining,curation,datasets,evaluation]"
python -m unittest discover -s tests -v
python Demo/03_triage_extraction/mof_triage_extraction_demo.py triage
python -m mofinder.literature.triage validate-inputs --metadata data/processed_data/literature_metadata.csv --ground-truth benchmarks/abstract_triage/ground_truth.xlsx
```

The [GitHub Actions workflow](../.github/workflows/triage.yml) runs offline tests on Windows and Linux. The [demos](../Demo/README.md) provide expected-output checks for data curation and dataset preparation. These checks do not measure extraction accuracy or model performance.

## Downstream workflow

Install `.[mining,curation,datasets]` for the revised extraction-to-dataset modules and add `notebook` for interactive demos. See [the workflow guide](workflow.md). PDF readers extract embedded text; no OCR pipeline is enabled. Legacy DOC conversion may require additional system software, while DOCX handling uses the supported Python readers.

The molecular-weight lookup is included. Original research extraction outputs are still needed to repeat a full curation run; the processed positive and negative tables in `data/processed_data/` and final JSONL in `data/final_json/` can be used directly. The included demonstration PDF pair supports offline document matching. API-enabled notebook cells are disabled by default.

## Evaluation

Install `.[evaluation]` for the holdout and 22-question evaluation modules and anonymous human benchmark analysis. Live model evaluation commands read `OPENAI_API_KEY` from the environment. Human analysis and saved-run analysis require no API key. See [evaluation](evaluation.md) for commands and source links.
