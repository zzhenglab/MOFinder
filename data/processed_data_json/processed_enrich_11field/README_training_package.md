# Eleven-field process-enriched training and holdout

This package contains `train_process_enrich.jsonl`, `holdout_process_enrich.jsonl`, and this README. The files use eleven inputs: the baseline eight reaction conditions plus vessel type, vessel capacity, and agitation.

| File | Rows | P | N |
|---|---:|---:|---:|
| `train_process_enrich.jsonl` | 23,528 | 11,968 | 11,560 |
| `holdout_process_enrich.jsonl` | 2,595 | 1,320 | 1,275 |

Each line contains a JSON object with `messages` in system, user, assistant order. The user-message content is a JSON object encoded as a string. The assistant content is `P` or `N`.

## System-prompt difference

Only the input-field list is expanded. The chemistry task, output instructions, and all other system-prompt text and formatting remain unchanged in the JSONL files.

```diff
-    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, and time_h.
+    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, time_h, vessel_type, vessel_volume_mL, and agitation.
```

## User-prompt difference

The original eight values, JSON types, and key order are preserved. Three keys are appended: `vessel_type`, `vessel_volume_mL`, and `agitation`.

The following paired example comes from training row 7 (one-based), formatted for readability. Its assistant label remains `P`.

Baseline user content:

```json
{
  "metal_precursor": "Zr(SO4)2·4H2O",
  "organic_linker": "adipic acid",
  "modulator": null,
  "solvent": "water",
  "metal_concentration_mM": 400.0,
  "M_L_ratio": 1.0,
  "temperature_C": 90.0,
  "time_h": 20.0
}
```

Process-enriched user content:

```json
{
  "metal_precursor": "Zr(SO4)2·4H2O",
  "organic_linker": "adipic acid",
  "modulator": null,
  "solvent": "water",
  "metal_concentration_mM": 400.0,
  "M_L_ratio": 1.0,
  "temperature_C": 90.0,
  "time_h": 20.0,
  "vessel_type": "Vial",
  "vessel_volume_mL": 11.0,
  "agitation": "Stirring reported"
}
```

| Added field | Meaning |
|---|---|
| `vessel_type` | Cleaned vessel category; unavailable or selected rare categories use `Not reported`. |
| `vessel_volume_mL` | Numeric vessel capacity in mL, or `Not reported` / `Ambiguous`. |
| `agitation` | One of the nine categories below. |

- `No stirring`
- `Not reported`
- `Stirred before static synthesis`
- `Stirred before main synthesis`
- `Stirring reported`
- `Sonicated before static synthesis`
- `Sonicated before main synthesis`
- `Sonication reported`
- `Shaking, vortexing, rotation and mixing`

`Stirred before main synthesis` means initial preparation before the main heating or aging step, with later conditions unspecified. `Stirred before static synthesis` requires an explicitly static subsequent stage. The same distinction applies to sonication. `Stirring reported` leaves the stage unspecified. Shaking, vortexing, rotation, mixing, and homogenization are grouped separately from stirring.

## File verification

Every row was compared with the corresponding baseline row in file order. Row counts, order, labels, and all eight original input values and types match. The system prompt differs only by its input-field list.

SHA-256 hashes of the uncompressed JSONL files:

```text
69821f68873f014c392e50572898bb1b708ec6f921a6ef7a8cfa8264674dc57a  train_process_enrich.jsonl
02e5728a850c99bf62df0dc5f2fdb6c6c139b7fe1513525a5b0d73179802ea3e  holdout_process_enrich.jsonl
```

[System prompt](https://github.com/zzhenglab/MOFinder/blob/main/prompts/training/reaction_prediction_process_enrich_11field.txt)

To reproduce this ZIP from the repository root:

```bash
python tools/package_process_enrich.py
```
