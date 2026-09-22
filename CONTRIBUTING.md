# Development conventions

Keep scientific code and its explanatory comments close to the working research implementation. Preserve useful comments, prompts, field definitions, and analysis order when moving code into modules. Use factual descriptions of the method and its inputs or outputs.

The main workflow belongs in Python modules under `src/mofinder/`. Provide callable functions and command-line entry points for each integrated stage. Notebooks are short walkthroughs that configure those functions and display their results. Keep each scientific calculation in one implementation shared by the terminal and notebook workflows.

Changes to labels, eligibility, normalization, prompts, splits, or statistical definitions must be documented separately from file organization and formatting changes. Compare outputs against the preceding implementation before replacing a scientific calculation. Record operational changes, such as resume behavior, separately as well.

Use portable paths relative to the configuration's project root or explicit input arguments. Store credentials in environment variables. Keep generated runs in the documented results directory and preserve their manifests and response records.

Notebooks should execute in order, with live screening disabled until explicitly selected. Clear transient outputs before committing a changed notebook, and archive complete prediction records separately when reporting a result.

Use descriptive filenames. Update configuration, documentation, and references together when renaming an input or output. Preserve original annotations and evidence notes as source data.

Install the verification dependencies and run the offline checks from the repository root:

```bash
python -m pip install -e ".[triage,literature-retrieval,mining,curation,datasets,evaluation]"
python -m unittest discover -s tests -v
python Demo/03_api_demo/run_demo.py triage
```

Use the same environment for terminal commands and the selected notebook kernel. See [installation](docs/installation.md) for setup and [the pre-upload checklist](docs/preupload_checklist.md) for the demo and workflow checks. Live API, desktop-download, and GPU checks are separate from this offline suite.
