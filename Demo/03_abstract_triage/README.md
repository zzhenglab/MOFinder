# Offline triage example

This example checks a 12-paper subset of the human reference and literature metadata included in the repository. It validates DOI matching, required columns, abstracts, and consensus counts. It does not generate or score model predictions.

From the repository root:

```bash
python -m pip install -e .
python Demo/03_abstract_triage/validate_example.py
```

Expected results: 12 reference papers, 12 scheduled abstracts, 9 Y and 3 N labels, and zero missing reference abstracts. The script checks the result against `expected_validation.json`.

The example selects the first 12 reference rows in their original order. Bibliographic records are joined by normalized DOI. These files are demonstration inputs and are not a separate model-performance benchmark.

`quickstart.ipynb` runs the same validation interactively after installing `.[notebook]`.
