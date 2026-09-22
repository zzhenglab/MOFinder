"""Linker normalization, unit conversion, and filtering."""

def clean_positive(input_path, output_path, *, linker_mw_path, linker_prime_corrections=None):
    """Normalize linkers, convert supported amounts, and write the resulting CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    MW_PATH = Path(linker_mw_path)
    if not MW_PATH.is_file():
        raise FileNotFoundError(f"Linker molecular-weight table not found: {MW_PATH}")
    import pandas as pd
    import numpy as np
    import re
    from pathlib import Path




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
        "h3btb": "1,3,5-Tris(4-carboxyphenyl)benzene",
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
    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH.name} not found")

    df = pd.read_csv(IN_PATH, dtype=str, encoding="utf-8")
    if linker_prime_corrections is not None:
        from .linker_primes import correct_frame
        df = correct_frame(df, linker_prime_corrections)

    print_header(f"Loaded {IN_PATH.name}")
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
        unresolved_weights = mw_df["mw"].fillna("").astype(str).str.strip().eq("")
        print(f"Lookup rows with unresolved molecular weights: {int(unresolved_weights.sum())}")
    else:
        raise FileNotFoundError(f"Linker molecular-weight table not found: {MW_PATH}")

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

    # Mass values without a molecular weight remain unconverted and are filtered below.
    mass_units = df["linker_1_amount_unit"].astype(str).str.strip().str.lower().isin(
        {"mg", "milligram", "milligrams", "g", "gram", "grams"}
    )
    missing_weight = ~df["linker_1"].astype(str).str.strip().str.lower().isin(mw_map)
    print(f"Mass-unit records without a molecular weight: {int((mass_units & missing_weight).sum())}")

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
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print_header(f"Wrote cleaned CSV to {OUT_PATH.name}")
    return df


def clean_negative(input_path, output_path, *, linker_mw_path, linker_prime_corrections=None):
    """Normalize linkers, convert supported amounts, and write the resulting CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    MW_PATH = Path(linker_mw_path)
    if not MW_PATH.is_file():
        raise FileNotFoundError(f"Linker molecular-weight table not found: {MW_PATH}")
    import pandas as pd
    import numpy as np
    import re
    from pathlib import Path




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
        "d-h2cam": "D-camphoric acid",
        "h3btb": "1,3,5-Tris(4-carboxyphenyl)benzene",
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
    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH.name} not found")

    df = pd.read_csv(IN_PATH, dtype=str, encoding="utf-8")
    if linker_prime_corrections is not None:
        from .linker_primes import correct_frame
        df = correct_frame(df, linker_prime_corrections)

    print_header(f"Loaded {IN_PATH.name}")
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
    print(f"\nUnique linker_1 count: {len(unique_vals)}")
    print("All unique linker_1 values:")
    print("None" if len(unique_vals) == 0 else ", ".join(unique_vals))

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
    print(f"Unique linker_1 count with units not in {{mmol, mol}}: {len(unique_other_unit_linkers)}")
    if len(unique_other_unit_linkers) == 0:
        print("No unique linker_1 with non-mmol/mol units.")
    else:
        print("Unique linker_1 with non-mmol/mol units:")
        print(", ".join(unique_other_unit_linkers))

    unit_counts = unit_series[not_mmol_mol].value_counts()
    if len(unit_counts) > 0:
        print("\nNon-mmol/mol unit frequency:")
        print(unit_counts.to_string())

    # ---------------- 5) Unit conversions using "linker and mw.csv" ----------------
    print_header('Converting units using "linker and mw.csv"')


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
        unresolved_weights = mw_df["mw"].fillna("").astype(str).str.strip().eq("")
        print(f"Lookup rows with unresolved molecular weights: {int(unresolved_weights.sum())}")
    else:
        raise FileNotFoundError(f"Linker molecular-weight table not found: {MW_PATH}")

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

    # Mass values without a molecular weight remain unconverted and are filtered below.
    mass_units = df["linker_1_amount_unit"].astype(str).str.strip().str.lower().isin(
        {"mg", "milligram", "milligrams", "g", "gram", "grams"}
    )
    missing_weight = ~df["linker_1"].astype(str).str.strip().str.lower().isin(mw_map)
    print(f"Mass-unit records without a molecular weight: {int((mass_units & missing_weight).sum())}")

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
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print_header(f"Wrote cleaned CSV to {OUT_PATH.name}")
    return df
