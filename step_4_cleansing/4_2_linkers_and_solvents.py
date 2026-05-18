from __future__ import annotations

import argparse
from pathlib import Path

from utils import FULL_BRANCHES, branch_paths, configure_utf8_stdio


def clean_linker_1(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Run linker_1 cleanup and write the _3 CSV."""
    import re

    import numpy as np
    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_3.csv")
    def print_header(msg):
        print("\n" + "=" * 80)
        print(msg)
        print("=" * 80)

    def is_filled(x):
        if x is None:
            return False
        if isinstance(x, float) and np.isnan(x):
            return False
        s = str(x).strip()
        return s != "" and s.lower() not in {"nan", "none"}

    # ---------------- manual maps and special cases ----------------
    LINKER_MAP = {
        "1,4-dicarboxybenzene": "terephthalic acid",
        "benzene-1,4-dicarboxylate": "terephthalic acid",
        "1,3,5-benzene tricarboxylic acid": "benzene-1,3,5-tricarboxylic acid",
        "furan-2,5-dicarboxylic acid": "2,5-furandicarboxylic acid",
        "benzene-1,2,4,5-tetracarboxylic acid": "1,2,4,5-benzenetetracarboxylic acid",
        "3,5-pyridinedicarboxylic acid": "pyridine-3,5-dicarboxylic acid",
        "2,6-pyridinedicarboxylic acid": "pyridine-2,6-dicarboxylic acid",
        "4,4'-oxybisbenzoic acid": "4,4'-oxybis(benzoic acid)",
        "4,4'-(hexafluoroisopropylidene) bis(benzoic acid)": "4,4'-(hexafluoroisopropylidene)bis(benzoic acid)",
        "meso-tetra(4-carboxyphenyl)porphyrin": "tetrakis(4-carboxyphenyl)porphyrin",
        "meso-tetrakis(4-carboxyphenyl)porphyrin": "tetrakis(4-carboxyphenyl)porphyrin",
        "5,10,15,20-tetrakis(4-carboxyphenyl)porphyrin": "tetrakis(4-carboxyphenyl)porphyrin",
        "1,3,5-tri(4-carboxyphenyl)benzene": "1,3,5-tris(4-carboxyphenyl)benzene",
        "1,3,5-benzenetribenzoic acid": "1,3,5-tris(4-carboxyphenyl)benzene",
        "5-(4-carboxy-2-nitrophenoxy)-isophthalic acid": "5-(4-carboxy-2-nitrophenoxy)isophthalic acid",
        "5-(3,5-dicarboxybenzyloxy)-isophthalic acid": "5-(3,5-dicarboxybenzyloxy)isophthalic acid",
        "d-h2cam": "D-camphoric acid",
        "d-camphoric acid": "D-camphoric acid",
        "D-(+)-camphoric acid": "D-camphoric acid",
        "h3btb": "terephthalic acid",
        "h2bdc-f": "2-fluorobenzene-1,4-dicarboxylic acid",
        "h2bdc-f2": "2,5-difluorobenzene-1,4-dicarboxylic acid",
        "h2bdc-cl": "2-chlorobenzene-1,4-dicarboxylic acid",
        "h2bdc-cl2": "2,5-dichlorobenzene-1,4-dicarboxylic acid",
        "h2bdc-br": "2-bromobenzene-1,4-dicarboxylic acid",
        "h2bdc-br2": "2,5-dibromobenzene-1,4-dicarboxylic acid",
        "h2bdc-i": "2-iodobenzene-1,4-dicarboxylic acid",
        "h2bdc-ch3": "2-methylbenzene-1,4-dicarboxylic acid",
        "h2bdc-(ch3)2": "2,5-dimethylbenzene-1,4-dicarboxylic acid",
        "h2bdc-cf3": "2-(trifluoromethyl)benzene-1,4-dicarboxylic acid",
        "h2bdc-(cf3)2": "2,5-bis(trifluoromethyl)benzene-1,4-dicarboxylic acid",
        "h2bdc-no2": "2-nitrobenzene-1,4-dicarboxylic acid",
        "h2bdc-nh2": "2-aminobenzene-1,4-dicarboxylic acid",
        "h2bdc-oh": "2-hydroxybenzene-1,4-dicarboxylic acid",
        "bdc-so3na": "2-sulfonatobenzene-1,4-dicarboxylic acid sodium salt",
        "h2bdc-c6h4": "2-phenylbenzene-1,4-dicarboxylic acid",
        "h2bdc-(co2h)2": "benzene-1,2,4,5-tetracarboxylic acid",
        "4-bpmp": "bis(pyridylmethyl)piperazine"
    }

    SPECIAL_DROP_RAW = {
        "[IrCp*(H2bpydc)Cl]Cl",
        "2,5-BPTA",
        "BDC-SO3Na",
        "bis(4′-carboxyl-2,2′:6′,2″-terpyridine) Ru(II) hexafluorophosphate, [Ru(tpyCOOH)2](PF6)2",
    }
    def normalize_spaces_for_match(s: str) -> str:
        return re.sub(r"\s+", "", s.strip().lower())

    SPECIAL_DROP_SET = {normalize_spaces_for_match(x) for x in SPECIAL_DROP_RAW}

    # ---------------- compile patterns ----------------
    PAT_HNUM_SHORT = re.compile(r"^H\d+[A-Za-z0-9\-]{0,7}$", re.IGNORECASE)
    PAT_PAREN_H_START = re.compile(r"^\(\s*H", re.IGNORECASE)
    PAT_L_SHORT = re.compile(r"^L(\d{0,2})$", re.IGNORECASE)
    PAT_COMPLEX_WORD = re.compile(r"\bcomplex\b", re.IGNORECASE)
    # (S) or (D), optional spaces/hyphen, then H + digits, then up to 5 extra letters/digits
    PAT_CHIRAL_HSHORT = re.compile(r"^\(\s*[SD]\s*\)\s*-?\s*H\d+[A-Za-z0-9]{0,5}$", re.IGNORECASE)

    def map_or_drop_linker(val: str):
        if not is_filled(val):
            return val, False, "keep_empty"
        s = str(val).strip()
        s_lower = s.lower()
        s_nospace_norm = normalize_spaces_for_match(s)

        if s_lower in LINKER_MAP:
            return LINKER_MAP[s_lower], False, "mapped"
        if s_nospace_norm in SPECIAL_DROP_SET:
            return s, True, "special_drop"
        if PAT_COMPLEX_WORD.search(s):
            return s, True, "contains_complex"
        if PAT_PAREN_H_START.match(s):
            return s, True, "starts_with_(H"
        if PAT_CHIRAL_HSHORT.match(s):
            return s, True, "chiral_H_short"
        if PAT_HNUM_SHORT.match(s):
            return s, True, "Hnum_short"
        if PAT_L_SHORT.match(s):
            return s, True, "L_short"
        return s, False, "kept"

    # ---------------- run ----------------
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found")

    df = pd.read_csv(input_path, dtype=str, encoding="utf-8")

    print_header(f"Loaded {input_path.name}")
    print(f"Rows total: {len(df)}")

    # Ensure amount columns exist
    for c in ["linker_1_amount_text", "linker_1_amount_value", "linker_1_amount_unit"]:
        if c not in df.columns:
            df[c] = np.nan

    # 1) Drop rows where all three amount columns are empty
    amt_empty = (~df["linker_1_amount_text"].apply(is_filled)) & \
                (~df["linker_1_amount_value"].apply(is_filled)) & \
                (~df["linker_1_amount_unit"].apply(is_filled))
    print_header("Drop rows with all three linker_1 amount fields empty")
    print(f"Rows to drop on empty triple: {int(amt_empty.sum())}")
    df = df[~amt_empty].copy()
    print(f"Rows left after triple-empty drop: {len(df)}")

    # 2) Apply linker_1 mapping and drop logic
    if "linker_1" not in df.columns:
        df["linker_1"] = ""

    mapped_vals, drop_reasons, drop_mask = [], [], []
    for v in df["linker_1"].astype(str):
        new_v, drop_flag, reason = map_or_drop_linker(v)
        mapped_vals.append(new_v)
        drop_reasons.append(reason)
        drop_mask.append(drop_flag)

    df["linker_1"] = mapped_vals
    drop_mask = pd.Series(drop_mask, index=df.index)
    drop_reasons = pd.Series(drop_reasons, index=df.index)

    print_header("Linker_1 drop reasons")
    reason_counts = drop_reasons[drop_mask].value_counts()
    if len(reason_counts) == 0:
        print("No rows marked for drop by linker_1 rules.")
    else:
        for r, c in reason_counts.items():
            print(f"{r}: {int(c)}")

    print(f"Total rows to drop by linker_1 rules: {int(drop_mask.sum())}")
    df = df[~drop_mask].copy()
    print(f"Rows left after linker_1 filters: {len(df)}")

    # 3) Summaries for linker_1
    print_header("linker_1 summaries")
    series = df["linker_1"].astype(str).str.strip()
    series = series[series != ""]
    vc = series.value_counts()

    topn = vc.head(10)
    print("Top 10 linker_1 by count:")
    print("None" if len(topn) == 0 else topn.to_string())

    unique_vals = sorted(series.unique(), key=lambda x: x.lower())
    #print(f"\nUnique linker_1 count: {len(unique_vals)}")
    #print("All unique linker_1 values:")
    #print("None" if len(unique_vals) == 0 else ", ".join(unique_vals))

    # 4) Unique-linker check for non-mmol or non-mol amount units
    print_header("Unique linker_1 with units not mmol or mol")
    unit_series = df.get("linker_1_amount_unit", pd.Series(index=df.index, dtype=str)).astype(str).str.strip().str.lower()
    not_mmol_mol = unit_series.notna() & (unit_series != "") & ~(unit_series.isin({"mmol", "mol"}))

    rows_other_units = int(not_mmol_mol.sum())
    print(f"Rows with units not in {{mmol, mol}}: {rows_other_units}")

    unique_other_unit_linkers = sorted(
        df.loc[not_mmol_mol & (df["linker_1"].astype(str).str.strip() != ""), "linker_1"].astype(str).str.strip().unique(),
        key=lambda x: x.lower()
    )
    #print(f"Unique linker_1 count with units not in {{mmol, mol}}: {len(unique_other_unit_linkers)}")
    #if len(unique_other_unit_linkers) == 0:
    #    print("No unique linker_1 with non-mmol/mol units.")
    #else:
    #    print("Unique linker_1 with non-mmol/mol units:")
    #    print(", ".join(unique_other_unit_linkers))

    unit_counts = unit_series[not_mmol_mol].value_counts()
    if len(unit_counts) > 0:
        print("\nNon-mmol/mol unit frequency:")
        print(unit_counts.to_string())

    # ---------------- 5) Unit conversions using "linker and mw.csv" ----------------
    print_header('Converting units using "linker and mw.csv"')

    MW_PATH = input_path.with_name("linker and mw.csv")
    mw_map = {}
    if MW_PATH.exists():
        mw_df = pd.read_csv(MW_PATH, header=None, names=["linker_name", "mw"], dtype=str, encoding="utf-8")
        # build case-insensitive map
        for _, row in mw_df.iterrows():
            name = str(row["linker_name"]).strip()
            try:
                mw = float(str(row["mw"]).strip())
            except Exception:
                continue
            if name != "" and np.isfinite(mw):
                mw_map[name.lower()] = mw
        print(f"Loaded MW entries: {len(mw_map)}")
    else:
        print('Warning: "linker and mw.csv" not found. Skipping mg/g conversions.')

    def to_float_safe(x):
        try:
            return float(str(x).strip())
        except Exception:
            return None

    conv_counts = {"umol_to_mmol": 0, "mol_to_mmol": 0, "mg_to_mmol": 0, "g_to_mmol": 0}

    def convert_row(idx, row):
        unit = str(row.get("linker_1_amount_unit", "")).strip()
        unit_lower = unit.lower()
        val = to_float_safe(row.get("linker_1_amount_value", ""))
        if val is None:
            return  # cannot convert non numeric

        # eq or equiv: leave as is
        if "equiv" in unit_lower or unit_lower == "eq":
            return

        # μmol or µmol or umol -> mmol
        if unit_lower in {"μmol", "µmol", "umol"}:
            new_val = val / 1000.0
            df.at[idx, "linker_1_amount_value"] = f"{new_val:.6g}"
            df.at[idx, "linker_1_amount_unit"] = "mmol"
            conv_counts["umol_to_mmol"] += 1
            return

        # mol -> mmol
        if unit_lower == "mol":
            new_val = val * 1000.0
            df.at[idx, "linker_1_amount_value"] = f"{new_val:.6g}"
            df.at[idx, "linker_1_amount_unit"] = "mmol"
            conv_counts["mol_to_mmol"] += 1
            return

        # mg or g -> need MW
        lk = str(row.get("linker_1", "")).strip().lower()
        mw = mw_map.get(lk)
        if unit_lower in {"mg", "milligram", "milligrams"} and mw:
            mmol = val / mw
            df.at[idx, "linker_1_amount_value"] = f"{mmol:.6g}"
            df.at[idx, "linker_1_amount_unit"] = "mmol"
            conv_counts["mg_to_mmol"] += 1
            return

        if unit_lower in {"g", "gram", "grams"} and mw:
            mmol = (val * 1000.0) / mw
            df.at[idx, "linker_1_amount_value"] = f"{mmol:.6g}"
            df.at[idx, "linker_1_amount_unit"] = "mmol"
            conv_counts["g_to_mmol"] += 1
            return
        # otherwise leave unchanged

    for idx, row in df.iterrows():
        convert_row(idx, row)

    print("Conversions performed:")
    for k, v in conv_counts.items():
        print(f"{k}: {v}")

    # ---------------- 6) Final drop: keep only mmol or eq-type ----------------
    print_header("Final filtering to keep only mmol or eq-type units")
    unit_series_after = df["linker_1_amount_unit"].astype(str).str.strip().str.lower()
    keep_mask = (unit_series_after == "mmol") | (unit_series_after.str.contains("equiv")) | (unit_series_after == "eq")
    dropped_final = int((~keep_mask).sum())
    df = df[keep_mask].copy()
    print(f"Dropped rows for non-allowed units: {dropped_final}")
    print(f"Rows left after final unit filter: {len(df)}")

    # Save
    df = df.fillna("")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print_header(f"Wrote cleaned CSV to {output_path.name}")
    return Path(output_path)


def clean_solvents(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Run solvent canonicalization and volume inference, then write the _4 CSV."""
    import re

    import numpy as np
    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_4.csv")
    # Solvent cleanup and volume inference (with solvent map)
    # - Canonicalizes solvent_main/solvent_secondary and their *_abbr using a synonym map
    #   e.g., "ethanol (absolute)" -> "ethanol" with abbr "EtOH"
    # - Fills solvent_main_ml where possible from solvent_main_amount_text
    # - Supports "X mL + Y mL", ratio totals, and per-solvent mL extraction
    # - Converts mass (g, mg) to mL for H2O, EtOH, DMF using density
    # - Drops rows where solvent_main_abbr, solvent_main_amount_text, solvent_main_ml are all blank
    # - Prints top 10 solvent_main

    import re
    import numpy as np
    import pandas as pd
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found")

    # ---------------- utilities ----------------
    def print_header(msg):
        print("\n" + "=" * 80)
        print(msg)
        print("=" * 80)

    def is_filled(x):
        if x is None:
            return False
        if isinstance(x, float) and np.isnan(x):
            return False
        s = str(x).strip()
        return s != "" and s.lower() not in {"nan", "none"}

    def filled_series(s):
        return s.apply(is_filled)

    def parse_num(s):
        t = str(s).strip()
        if "/" in t:
            a, b = t.split("/", 1)
            try:
                return float(a) / float(b)
            except Exception:
                return None
        try:
            return float(t)
        except Exception:
            return None

    # ---------------- solvent map ----------------
    # Canonical solvent keys -> (canonical name, canonical abbr)
    SOLVENT_CANON = {
        "water": ("water", "H2O"),
        "ethanol": ("ethanol", "EtOH"),
        "methanol": ("methanol", "MeOH"),
        "isopropanol": ("isopropanol", "iPrOH"),
        "acetonitrile": ("acetonitrile", "MeCN"),
        "dimethylformamide": ("dimethylformamide", "DMF"),
        "dimethyl sulfoxide": ("dimethyl sulfoxide", "DMSO"),
        "n-methyl-2-pyrrolidone": ("N-methyl-2-pyrrolidone", "NMP"),
        "tetrahydrofuran": ("tetrahydrofuran", "THF"),
        "toluene": ("toluene", "toluene"),
        "acetone": ("acetone", "acetone"),
        "n,n-dimethylacetamide": ("N,N-dimethylacetamide", "DMAc"),
    }

    # Normalize a solvent name into a lookup key
    QUAL_WORDS = r"(absolute|anhydrous|dry|extra\s*dry|spectroscopic|hplc|reagent|acs|ultra\s*pure|degassed|deoxygenated|stabilized|saturated|technical|denatured|\d{2,3}\s*%)"
    PARENS_CLEAN = re.compile(r"\([^)]*\)")
    QUAL_TAILS = re.compile(rf"(?:[,;\s-]+{QUAL_WORDS})+$", re.IGNORECASE)

    def normalize_solvent_key(name: str) -> str:
        if not is_filled(name):
            return ""
        s = str(name).strip()
        # remove parenthetical qualifiers like "(absolute)" or "(with 2-MI)" for mapping only
        s = PARENS_CLEAN.sub("", s)
        # drop qualifier tails and percentages
        s = QUAL_TAILS.sub("", s)
        s = re.sub(r"\s+", " ", s)
        s = s.lower().strip()
        # common alias expansions
        s = s.replace("ethyl alcohol", "ethanol")
        s = s.replace("methyl alcohol", "methanol")
        s = s.replace("isopropyl alcohol", "isopropanol")
        s = s.replace("2-propanol", "isopropanol")
        s = s.replace("dimethylsulfoxide", "dimethyl sulfoxide")
        s = s.replace("n,n-dimethyl formamide", "dimethylformamide")
        s = s.replace("n,n-dimethylformamide", "dimethylformamide")
        s = s.replace("n methyl 2 pyrrolidone", "n-methyl-2-pyrrolidone")
        s = s.replace("n-methylpyrrolidone", "n-methyl-2-pyrrolidone")
        s = s.replace("di water", "water")
        s = s.replace("deionized water", "water")
        s = s.replace("deionised water", "water")
        s = s.replace("distilled water", "water")
        s = s.replace("doubly deionized water", "water")
        s = s.replace("double deionized water", "water")
        s = s.replace("milli-q water", "water")
        s = s.replace("ultrapure water", "water")
        s = s.replace("tap water", "water")
        s = s.replace("h₂o", "h2o")
        if s == "h2o":
            s = "water"
        return s

    # Map many name variants to canonical keys
    NAME_TO_KEY = {
        # water
        "water": "water", "h2o": "water",
        # ethanol
        "ethanol": "ethanol", "ethanol absolute": "ethanol", "absolute ethanol": "ethanol",
        "ethanol (absolute)": "ethanol",
        "anhydrous ethanol": "ethanol", "ethanol anhydrous": "ethanol", "95% ethanol": "ethanol",
        "etoh": "ethanol", "denatured ethanol": "ethanol",
        # methanol
        "methanol": "methanol", "meoh": "methanol", "anhydrous methanol": "methanol",
        # isopropanol
        "isopropanol": "isopropanol", "ipa": "isopropanol", "iproh": "isopropanol",
        # acetonitrile
        "acetonitrile": "acetonitrile", "mecn": "acetonitrile", "acn": "acetonitrile",
        # dmf
        "dimethylformamide": "dimethylformamide", "dmf": "dimethylformamide",
        # dmso
        "dimethyl sulfoxide": "dimethyl sulfoxide", "dmso": "dimethyl sulfoxide",
        # nmp
        "n-methyl-2-pyrrolidone": "n-methyl-2-pyrrolidone", "nmp": "n-methyl-2-pyrrolidone",
        # thf
        "tetrahydrofuran": "tetrahydrofuran", "thf": "tetrahydrofuran",
        # toluene
        "toluene": "toluene", "phme": "toluene",
        # acetone
        "acetone": "acetone",
        # dma c
        "n,n-dimethylacetamide": "n,n-dimethylacetamide", "dmac": "n,n-dimethylacetamide", "dmac.": "n,n-dimethylacetamide",
    }

    # Abbreviation to canonical keys
    ABBR_TO_KEY = {
        "H2O": "water",
        "ETOH": "ethanol",
        "MEOH": "methanol",
        "IPROH": "isopropanol",
        "IPA": "isopropanol",
        "MECN": "acetonitrile",
        "ACN": "acetonitrile",
        "DMF": "dimethylformamide",
        "DMSO": "dimethyl sulfoxide",
        "NMP": "n-methyl-2-pyrrolidone",
        "THF": "tetrahydrofuran",
        "TOLUENE": "toluene",
        "ACETONE": "acetone",
        "DMAC": "n,n-dimethylacetamide",
        "DMAc": "n,n-dimethylacetamide",
    }

    def canonize_solvent_pair(name: str, abbr: str):
        key_from_name = NAME_TO_KEY.get(normalize_solvent_key(name))
        a = "" if pd.isna(abbr) else str(abbr).strip()
        key_from_abbr = ABBR_TO_KEY.get(a.upper()) if a else None
        key = key_from_name or key_from_abbr
        if key in SOLVENT_CANON:
            canon_name, canon_abbr = SOLVENT_CANON[key]
            return canon_name, canon_abbr
        # If abbr is H2O but name not water, force water per your rule
        if a.upper() == "H2O":
            return "water", "H2O"
        # Otherwise return cleaned name and unchanged abbr
        return (str(name).strip() if is_filled(name) else ""), a

    # Tokens to recognize mL near the main solvent
    def tokens_for_abbr(abbr: str):
        a = (abbr or "").strip().upper()
        if a == "H2O":
            return [
                "H2O", "water", "deionized water", "deionised water", "distilled water",
                "DI water", "DI H2O", "doubly deionized water", "double deionized water",
                "Milli-Q water", "ultrapure water", "tap water",
            ]
        if a == "DMF":
            return ["DMF", "N,N-dimethylformamide", "dimethylformamide"]
        if a == "ETOH":
            return ["EtOH", "ethanol", "ethyl alcohol", "absolute ethanol", "anhydrous ethanol"]
        if a == "MEOH":
            return ["MeOH", "methanol", "methyl alcohol", "anhydrous methanol"]
        if a in {"IPROH", "IPA"}:
            return ["iPrOH", "IPA", "isopropanol", "isopropyl alcohol", "2-propanol"]
        if a in {"MECN", "ACN"}:
            return ["MeCN", "acetonitrile"]
        if a == "DMSO":
            return ["DMSO", "dimethyl sulfoxide", "dimethylsulfoxide"]
        if a == "NMP":
            return ["NMP", "N-methyl-2-pyrrolidone", "N-methylpyrrolidone"]
        if a == "THF":
            return ["THF", "tetrahydrofuran"]
        if a == "TOLUENE":
            return ["toluene", "PhMe"]
        if a == "ACETONE":
            return ["acetone"]
        if a in {"DMAC", "DMAC."}:
            return ["DMAc", "N,N-dimethylacetamide", "dimethylacetamide"]
        return [a] if a else []

    def token_regex_for_abbr(abbr: str):
        toks = [re.escape(t) for t in tokens_for_abbr(abbr) if t]
        if not toks:
            return None
        return re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(toks)})(?![A-Za-z0-9])", re.IGNORECASE)

    # densities for mass -> volume
    DENSITY_BY_ABBR = {"H2O": 1.0, "ETOH": 0.789, "DMF": 0.944}  # g/mL

    # ---------------- volume parsing helpers ----------------
    ML_NUM = r"(\d+(?:\.\d+)?(?:/\d+)?)"
    ML_PAT = re.compile(rf"{ML_NUM}\s*mL", re.IGNORECASE)

    def find_all_ml_numbers(text: str):
        return [parse_num(x) for x in re.findall(ML_PAT, str(text) or "") if parse_num(x) is not None]

    def find_ml_near_abbr(text: str, abbr: str):
        tok = token_regex_for_abbr(abbr)
        if tok is None:
            return 0.0
        s = str(text) or ""
        total = 0.0
        used = set()
        # pattern: number mL followed by solvent token within nearby context
        for m in re.finditer(rf"{ML_NUM}\s*mL", s, re.IGNORECASE):
            num = parse_num(m.group(1))
            if num is None:
                continue
            seg = s[m.end(): m.end() + 40]
            if tok.search(seg):
                rng = (m.start(), m.end())
                if rng not in used:
                    used.add(rng)
                    total += num
        # token first then number mL
        for m in tok.finditer(s):
            seg = s[m.end(): m.end() + 40]
            m2 = re.search(rf"{ML_NUM}\s*mL", seg, re.IGNORECASE)
            if m2:
                num = parse_num(m2.group(1))
                if num is not None:
                    start = m.end() + m2.start()
                    end = m.end() + m2.end()
                    rng = (start, end)
                    if rng not in used:
                        used.add(rng)
                        total += num
        return total

    def parse_parenthetical_mixture_shares(text: str, abbr: str):
        s = str(text) or ""
        tok = token_regex_for_abbr(abbr)
        if tok is None:
            return 0.0, 0.0
        share, mix_total_seen = 0.0, 0.0
        mix_pat = re.compile(r"([A-Za-z0-9\-\(\)]+)\s*/\s*([A-Za-z0-9\-\(\)]+)\s*\(([^)]*)\)", re.IGNORECASE)
        for m in mix_pat.finditer(s):
            left, right, inside = m.group(1), m.group(2), m.group(3)
            vm = re.search(rf"{ML_NUM}\s*mL", inside, re.IGNORECASE)
            if not vm:
                continue
            V = parse_num(vm.group(1)) or 0.0
            mix_total_seen += V
            ratio = re.search(rf"(?:v\s*/\s*v\s*)?{ML_NUM}\s*:\s*{ML_NUM}", inside, re.IGNORECASE)
            a = parse_num(ratio.group(1)) if ratio else 1.0
            b = parse_num(ratio.group(2)) if ratio else 1.0
            a = a if a else 1.0
            b = b if b else 1.0
            left_is = token_regex_for_abbr(abbr).search(left) is not None
            right_is = token_regex_for_abbr(abbr).search(right) is not None
            if left_is and not right_is:
                share += V * a / (a + b)
            elif right_is and not left_is:
                share += V * b / (a + b)
        return share, mix_total_seen

    def parse_ratio_total_allocation(text: str, abbr: str):
        s = str(text) or ""
        pat = re.compile(
            rf"([A-Za-z0-9\-\(\)]+)\s*[:/]\s*([A-Za-z0-9\-\(\)]+)\s*=\s*{ML_NUM}\s*:\s*{ML_NUM}.*?(?:total(?:\s*volume)?|in\s*total)\s*[:=]?\s*{ML_NUM}\s*mL",
            re.IGNORECASE | re.DOTALL,
        )
        total_share = 0.0
        for m in pat.finditer(s):
            left, right = m.group(1), m.group(2)
            a = parse_num(m.group(3)) or 1.0
            b = parse_num(m.group(4)) or 1.0
            total_vol = parse_num(m.group(5)) or 0.0
            if total_vol <= 0:
                continue
            left_is = token_regex_for_abbr(abbr).search(left) is not None
            right_is = token_regex_for_abbr(abbr).search(right) is not None
            if left_is and not right_is:
                total_share += total_vol * a / (a + b)
            elif right_is and not left_is:
                total_share += total_vol * b / (a + b)
        return total_share

    def parse_plus_sum_smart(text: str, abbr: str):
        s = str(text) or ""
        if "+" not in s or not re.search(ML_PAT, s):
            return None
        nums = find_all_ml_numbers(s)
        if len(nums) < 2:
            return None
        mix_share, mix_total = parse_parenthetical_mixture_shares(s, abbr)
        base_sum = sum(nums) - mix_total
        return base_sum + mix_share

    def find_mass_grams_near_abbr(text: str, abbr: str):
        s = str(text) or ""
        tok = token_regex_for_abbr(abbr)
        if tok is None:
            return None
        grams = None
        # num g then token
        for m in re.finditer(rf"{ML_NUM}\s*(g|mg)\b", s, re.IGNORECASE):
            n = parse_num(m.group(1))
            unit = m.group(2).lower()
            tail = s[m.end(): m.end() + 40]
            if n is None:
                continue
            if tok.search(tail):
                grams = n / 1000.0 if unit == "mg" else n
                break
        if grams is None:
            # token then num g
            for m in tok.finditer(s):
                seg = s[m.end(): m.end() + 40]
                m2 = re.search(rf"{ML_NUM}\s*(g|mg)\b", seg, re.IGNORECASE)
                if m2:
                    n = parse_num(m2.group(1))
                    unit = m2.group(2).lower()
                    if n is not None:
                        grams = n / 1000.0 if unit == "mg" else n
                        break
        return grams

    def grams_to_mL(grams: float, abbr: str):
        a = (abbr or "").strip().upper()
        rho = DENSITY_BY_ABBR.get(a)
        if rho and grams is not None:
            return grams / rho
        return None

    # ---------------- run ----------------
    df = pd.read_csv(input_path, dtype=str, encoding="utf-8")

    # Ensure columns
    for c in ["solvent_main", "solvent_main_abbr", "solvent_main_amount_text", "solvent_main_ml"]:
        if c not in df.columns:
            df[c] = ""
    for c in ["solvent_secondary", "solvent_secondary_abbr"]:
        if c not in df.columns:
            df[c] = ""

    print_header(f"Loaded {input_path.name}")
    print(f"Rows total: {len(df)}")

    # ---------------- apply solvent map first (so parsing can use canonical abbr) ----------------
    print_header("Solvent mapping to canonical names and abbreviations")

    def _apply_map_pair(df, name_col, abbr_col):
        before_name = df[name_col].astype(str)
        before_abbr = df[abbr_col].astype(str)
        new_names, new_abbrs = [], []
        for n, a in zip(before_name, before_abbr):
            cn, ca = canonize_solvent_pair(n, a)
            new_names.append(cn)
            new_abbrs.append(ca)
        df[name_col] = new_names
        df[abbr_col] = new_abbrs
        changed_n = int((before_name != df[name_col].astype(str)).sum())
        changed_a = int((before_abbr != df[abbr_col].astype(str)).sum())
        print(f"{name_col} mapped changes: {changed_n}")
        print(f"{abbr_col} mapped changes: {changed_a}")

    _apply_map_pair(df, "solvent_main", "solvent_main_abbr")
    _apply_map_pair(df, "solvent_secondary", "solvent_secondary_abbr")

    # ---------------- fill solvent_main_ml ----------------
    empty_ml = ~filled_series(df["solvent_main_ml"])
    rows_to_process = df[empty_ml].index

    cnt_plus, cnt_ratio, cnt_token_ml, cnt_mass, cnt_h2o_strict = 0, 0, 0, 0, 0

    for idx in rows_to_process:
        text = df.at[idx, "solvent_main_amount_text"]
        abbr = (df.at[idx, "solvent_main_abbr"] or "").strip()
        if not is_filled(text):
            continue

        # 1) plus-case with mixture share replacement
        val = parse_plus_sum_smart(text, abbr)
        if val is not None and val > 0:
            df.at[idx, "solvent_main_ml"] = f"{float(val):.6g}"
            cnt_plus += 1
            continue

        # 2) ratio allocation with total volume
        val = parse_ratio_total_allocation(text, abbr)
        if val > 0:
            df.at[idx, "solvent_main_ml"] = f"{float(val):.6g}"
            cnt_ratio += 1
            continue

        # 3) explicit amounts tied to main solvent token
        val = find_ml_near_abbr(text, abbr)
        if val > 0:
            df.at[idx, "solvent_main_ml"] = f"{float(val):.6g}"
            cnt_token_ml += 1
            continue

        # 4) parenthetical mixture share even without '+'
        share, _tot = parse_parenthetical_mixture_shares(text, abbr)
        if share > 0:
            df.at[idx, "solvent_main_ml"] = f"{float(share):.6g}"
            cnt_token_ml += 1
            continue

        # 5) mass to mL conversion if abbr in known densities
        grams = find_mass_grams_near_abbr(text, abbr)
        vol = grams_to_mL(grams, abbr)
        if vol and vol > 0:
            df.at[idx, "solvent_main_ml"] = f"{float(vol):.6g}"
            cnt_mass += 1
            continue

        # 6) H2O specific fallback as requested
        if (abbr or "").upper() == "H2O":
            m = re.search(rf"(?:H2O[^\d]{{0,15}}{ML_NUM}\s*mL)|({ML_NUM}\s*mL[^\d]{{0,15}}H2O)", str(text), re.IGNORECASE)
            if m:
                nn = None
                for g in m.groups():
                    if g and parse_num(g) is not None:
                        nn = parse_num(g)
                        break
                if nn:
                    df.at[idx, "solvent_main_ml"] = f"{float(nn):.6g}"
                    cnt_h2o_strict += 1
                    continue

    print_header("solvent_main_ml filled counts")
    print(f"From plus-sum: {cnt_plus}")
    print(f"From ratio total: {cnt_ratio}")
    print(f"From token-linked mL (incl. mixtures): {cnt_token_ml}")
    print(f"From mass conversion: {cnt_mass}")
    print(f"From H2O fallback: {cnt_h2o_strict}")

    # ---------------- final drop ----------------
    print_header("Final drop of rows with empty solvent fields")
    all_blank = (
        ~filled_series(df["solvent_main_abbr"])
        & ~filled_series(df["solvent_main_amount_text"])
        & ~filled_series(df["solvent_main_ml"])
    )
    print(f"Rows to drop (all three empty): {int(all_blank.sum())}")
    df = df[~all_blank].copy()
    print(f"Rows left: {len(df)}")

    # ---------------- top 10 solvent_main ----------------
    print_header("Top 10 solvent_main")
    series = df["solvent_main"].astype(str).str.strip()
    series = series[series != ""]
    vc = series.value_counts().head(10)
    print("None" if len(vc) == 0 else vc.to_string())

    # ---------------- save ----------------
    df = df.fillna("")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print_header(f"Wrote cleaned CSV to {output_path.name}")
    return Path(output_path)



def run(branch: str, input_path: str | Path | None = None, output_3: str | Path | None = None, output_4: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    if branch not in FULL_BRANCHES:
        raise ValueError("Step 4.2 is only defined for positive and negative-plans branches; negative-basic stops after Step 4.1.")
    paths = branch_paths(branch)
    s2 = Path(input_path) if input_path else paths["s2"]
    s3 = Path(output_3) if output_3 else paths["s3"]
    s4 = Path(output_4) if output_4 else paths["s4"]
    clean_linker_1(s2, s3)
    return clean_solvents(s3, s4)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 4.2: linker cleanup plus solvent canonicalization/volume inference.")
    parser.add_argument("--branch", choices=sorted(FULL_BRANCHES), default="positive")
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--output-3", default=None)
    parser.add_argument("--output-4", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.input_path, args.output_3, args.output_4)


if __name__ == "__main__":
    main()
