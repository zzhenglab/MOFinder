# Document matching and mining example

The sample article and supporting information provide inputs for document matching and text mining. They describe MOF-303 and CAU-23 using illustrative synthesis conditions and placeholder figures. The article contains the synthesis procedures; the supporting information contains characterization methods. Both documents identify DOI `10.1021/jacs.2c09756` as their literature source.

The documents are demonstration material, not copies of the published article. Example extraction outputs are stored separately from research datasets.

| File | Role |
| --- | --- |
| `articles/10.1021_jacs.2c09756.pdf` | Main demonstration document |
| `supporting_information/10.1021_jacs.2c09756_SI.pdf` | Supporting-information demonstration document |
| `inventory.csv` | One-row input for document matching |
| `manifest.json` | Document identity and byte checksums |

The filenames follow literature retrieval naming: replace the DOI slash with an underscore and append `_SI` for supporting information. Document checksums are recorded in `manifest.json`.

Install and match the files without making model requests:

```bash
python -m pip install -e ".[mining]"
python -m mofinder.literature.match_documents match --config configs/example_document_matching.json
```

The three-column manifest is written under `results/examples/mining/`. The production configuration instead reads locally acquired documents under `data/local/`. See [the workflow guide](../../docs/workflow.md) for extraction, saved-JSON recovery, negative reconstruction, cleaning, and dataset preparation.

Live extraction requires model access. Reference extraction outputs are not included.

## Validate and run mining

After the matching command, validate the positive example:

```bash
python -m mofinder.extraction.positive validate --config configs/example_positive_extraction.json
```

The following two mining commands require `OPENAI_API_KEY` and make model requests; enumeration uses their saved outputs locally:

```bash
python -m mofinder.extraction.positive run --config configs/example_positive_extraction.json
python -m mofinder.extraction.negative mine --config configs/example_negative_extraction.json
python -m mofinder.extraction.negative enumerate --config configs/example_negative_extraction.json
```

The example uses concurrency 2 and writes under `results/examples/mining/`. Negative reconstruction selects documents marked `YES` for trial-and-error evidence in the positive extraction output. The model's extracted evidence determines whether negative records are generated.
