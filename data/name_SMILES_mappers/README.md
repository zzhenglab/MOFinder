# Chemical name and SMILES mappings

These JSON dictionaries are retained unchanged from the original MOFinder repository.

| File | Contents | Entries |
| --- | --- | --- |
| `name2smiles_1222.json` | Chemical name to SMILES string | 3,734 |
| `smiles2name_1222.json` | SMILES string to a list of chemical names | 2,290 |

The names include aliases and reported formulation details. Keys are stored as written; the dictionaries do not normalize capitalization or whitespace at lookup time.

```python
import json
from pathlib import Path

folder = Path("data/name_SMILES_mappers")
name_to_smiles = json.loads((folder / "name2smiles_1222.json").read_text(encoding="utf-8"))
smiles_to_names = json.loads((folder / "smiles2name_1222.json").read_text(encoding="utf-8"))

smiles = name_to_smiles.get("HCl (36–38%)")
names = smiles_to_names.get(smiles, [])
```

Run this example from the repository root. The original cache-based resolution workflow is described in the [historical workflow](../../docs/legacy_workflow.md). Molecular-weight conversion during curation uses the separate [linker lookup](../lookups/README.md).
