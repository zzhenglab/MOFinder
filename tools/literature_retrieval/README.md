# Article and supporting-information literature retrieval

These entry points launch the Python desktop applications in
`src/mofinder/literature_retrieval/`:

```bash
python -m pip install -e ".[fetch-gui]"
python tools/literature_retrieval/fetch_papers.py --validate
python tools/literature_retrieval/fetch_si.py --validate
```

The validation commands inspect inventory records and image templates without
opening a browser or changing files. Install `.[literature-retrieval]` for these offline
checks alone. Omit `--validate` to launch an application:

```bash
python tools/literature_retrieval/fetch_papers.py
python tools/literature_retrieval/fetch_si.py
```

Both tools accept `--config` and `--workbook`. The default configuration is
`configs/literature_retrieval.json`. Inputs are copied to local working inventories;
archived input tables remain unchanged.

The applications require an interactive desktop with Chrome, Tk, and local
calibration. They use the mouse and keyboard and close Chrome windows during
literature retrieval. Save browser work before starting. Publisher profiles and image
filenames use neutral identifiers.

See [the literature retrieval guide](../../docs/literature_retrieval.md) for calibration, input
states, download directories, missing templates, and the limits of validation.
