# MOFinder data

Use the [processed positive and negative records](processed_data/README.md) as dataset-preparation inputs. The [final JSONL and split information](final_json/README.md) are ready for training and evaluation.

```text
processed_data/
  processed_positive.csv  ─┐
  processed_negative.csv  ─┼─ dataset preparation → final_json/
  publication_years.csv   ─┘                        train.jsonl
                                                    holdout.jsonl
                                                    split assignments and summaries
```

| Folder | What to find here |
| --- | --- |
| [processed_data/](processed_data/README.md) | Processed synthesis records, literature metadata, publication years, and retrieval inventories |
| [final_json/](final_json/README.md) | Training and holdout JSONL, split assignments, label definitions, and provenance |
| [organic_linker_info/](organic_linker_info/README.md) | Linker molecular weights and documented spelling corrections used during curation |
| [name_SMILES_mappers/](name_SMILES_mappers/README.md) | Name-to-SMILES and SMILES-to-name dictionaries |
| [paper_processing_assets/](paper_processing_assets/README.md) | Image templates used by literature retrieval |

To regenerate the final datasets from the bundled processed tables, run from the repository root:

```bash
python -m mofinder.datasets.prepare prepare --config configs/dataset_preparation.json
```

New outputs go to `results/datasets/conditions/`. The `final_json/` folder holds the distributed dataset. See the [dataset guide](../docs/datasets.md) for the full workflow and [manifest.json](manifest.json) for metadata provenance and links to related manifests.
