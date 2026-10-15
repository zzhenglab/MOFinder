# Chemical name and SMILES mappings

Audited chemical dictionaries and a three-sheet reagent catalog.

| File | Contents | Entries |
| --- | --- | --- |
| `name2smiles.json` | Chemical name to SMILES string | 3,302 |
| `smiles2name.json` | SMILES string to chemical names | 3,236 |
| `reagent_catalog.json` | Category lists with Name, SMILES and Comment | 3,477 |
| `reagent_catalog.xlsx` | Metal precursors, Organic linkers and Other reagents sheets | 663 / 2,156 / 658 |

The catalog preserves frequency order and representation comments. Names shared across categories are combined in the lookup dictionary only when their SMILES agree. The lookup also includes four source-verified full-name entries used in corrected records. Comments identify qualified component or constitutional representations. Lookup keys are stored as written.

```python
import json
from pathlib import Path

folder = Path("data/name_SMILES_mappers")
name_to_smiles = json.loads((folder / "name2smiles.json").read_text(encoding="utf-8"))
smiles_to_names = json.loads((folder / "smiles2name.json").read_text(encoding="utf-8"))

smiles = name_to_smiles.get("terephthalic acid")
names = smiles_to_names.get(smiles, [])
```

Run this example from the repository root. For [SMILESearcher](https://github.com/zach-zhiling-zheng/SMILESearcher), use `data/name_SMILES_mappers/name2smiles.json` as the cache path. Molecular-weight conversion during curation uses the separate [linker lookup](../organic_linker_info/README.md).
