"""Initial filtering and broad field cleanup for Step 4 cleansing."""
from __future__ import annotations

from pathlib import Path

def clean_initial_dataset(input_path: str | Path, output_path: str | Path | None = None, *, apply_linker_synonym_merge: bool = True, reset_after_filters: bool = True, strict_slow_temperature_filter: bool = False) -> Path:
    """Run initial row filtering and broad cleanup, then write the _1 CSV."""
    import re
    from collections import Counter

    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    in_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else in_path.with_name(f"{in_path.stem}_1.csv")
    out_path = output_path
    # ---------- helpers ----------
    def is_filled(x):
        if x is None:
            return False
        if isinstance(x, float) and np.isnan(x):
            return False
        s = str(x).strip()
        return s != "" and s.lower() not in {"nan", "none"}

    def filled_series(s):
        return s.apply(is_filled)

    def count_changes(before, after):
        return int((before.astype(str) != after.astype(str)).sum())

    def print_header(msg):
        print("\n" + "=" * 80)
        print(msg)
        print("=" * 80)

    def safe_lower(x):
        try:
            return str(x).strip().lower()
        except Exception:
            return ""

    def strip_trailing_parens(val, keep_when="(anhydrous)"):
        """Remove a trailing ' ( ... )' only if it is not the allowed exception.
           If the trailing parens looks like a formula, keep only the inside.
           Returns new_val, changed_flag
        """
        if not is_filled(val):
            return val, False
        s = str(val).strip()
        m = re.search(r"\s\(([^)]*)\)\s*$", s)
        if not m:
            return s, False
        inside = m.group(1).strip()
        if keep_when and s.endswith(f" {keep_when}"):
            return s, False
        # If inside looks like a formula, prefer the inside (e.g., '... (Ti(iPrO)4)' -> 'Ti(iPrO)4')
        if re.fullmatch(r"[A-Za-z0-9·\[\]\(\)]+", inside):
            return inside, True
        # Otherwise remove the whole trailing parenthetical
        new_s = re.sub(r"\s\([^)]*\)\s*$", "", s)
        return new_s, new_s != s

    def remove_linker_trailing_parens(val):
        """For linker names like 'salicylic acid (H2L1)' remove trailing ' (H2L1)'"""
        if not is_filled(val):
            return val, False
        s = str(val).strip()
        new_s = re.sub(r"\s\([^)]*\)\s*$", "", s)
        return new_s, new_s != s

    def normalize_x_to_middle_dot(s):
        if not is_filled(s):
            return s, False
        new_s = str(s).replace(" × ", "·")
        return new_s, new_s != s

    def extract_digits_after_ccdc(val):
        """For crystal_code: if contains 'CCDC', keep the digits; else if mixed, keep digits only."""
        if not is_filled(val):
            return val, False
        s = str(val).strip()
        if "CCDC" in s.upper():
            digits = "".join(re.findall(r"\d+", s))
            return digits, s != digits
        if re.search(r"[A-Za-z]", s):
            digits = "".join(re.findall(r"\d+", s))
            return (digits if digits != "" else s), digits != s
        return s, False

    def coerce_numeric(series):
        return pd.to_numeric(series, errors="coerce")

    # Small guard to keep index contiguous after each filter.
    def _reset(df, why):
        """Reset index after a filter to prevent alignment bugs between columns."""
        df = df.reset_index(drop=True)
        # Tripwire for unexpected states
        assert df.index.equals(pd.RangeIndex(len(df))), f"Index is not contiguous after: {why}"
        return df

    # ---------- read ----------

    if not in_path.exists():
        raise FileNotFoundError(f"{in_path.name} not found in the current folder")

    # load as strings to avoid unintended type casting
    df = pd.read_csv(in_path, dtype=str, encoding="utf-8")
    print_header(f"Loaded {in_path.name}")
    print(f"Total rows: {len(df)}")

    # ---------- 1) main_pdf / si_pdf presence stats ----------
    for col in ["main_pdf", "si_pdf"]:
        if col not in df.columns:
            df[col] = np.nan

    has_main = filled_series(df["main_pdf"])
    has_si = filled_series(df["si_pdf"])

    both = has_main & has_si
    only_main = has_main & ~has_si
    only_si = ~has_main & has_si
    neither = ~has_main & ~has_si

    print_header("PDF availability counts")
    print(f"Have value in main_pdf: {int(has_main.sum())}")
    print(f"Have value in si_pdf: {int(has_si.sum())}")
    print(f"Have both: {int(both.sum())}")
    print(f"Only main not si: {int(only_main.sum())}")
    print(f"Only si not main: {int(only_si.sum())}")
    print(f"Neither: {int(neither.sum())}")

    # drop neither
    df = df[~neither].copy()
    df = _reset(df, "drop rows with neither main_pdf nor si_pdf") if reset_after_filters else df

    # ---------- 2) article_trial_or_failure filtering ----------
    col_atof = "article_trial_or_failure"
    if col_atof not in df.columns:
        df[col_atof] = np.nan

    valnorm = df[col_atof].apply(safe_lower)
    keep_atof = valnorm.isin({"yes", "no"})
    print_header("article_trial_or_failure filter")
    print(f"Rows total before filter: {len(df)}")
    print(f"Dropping rows where '{col_atof}' is neither yes nor no: {int((~keep_atof).sum())}")
    df = df[keep_atof].copy()
    df = _reset(df, "article_trial_or_failure yes/no only") if reset_after_filters else df
    print(f"Rows left: {len(df)}")

    # ---------- 3) drop required empties ----------
    required_cols = ["metal_1", "linker_1", "solvent_main", "solvent_main_abbr"]
    for c in required_cols:
        if c not in df.columns:
            df[c] = np.nan

    mask_required = filled_series(df["metal_1"]) & filled_series(df["linker_1"]) & filled_series(df["solvent_main"]) & filled_series(df["solvent_main_abbr"])
    print_header("Drop rows with required empties")
    print(f"Dropping rows where any of {required_cols} is empty: {int((~mask_required).sum())}")
    df = df[mask_required].copy()
    df = _reset(df, "required columns nonempty") if reset_after_filters else df
    print(f"Rows left: {len(df)}")

    # ---------- 4) light cleaning ----------
    # 4a) crystal_code
    if "crystal_code" not in df.columns:
        df["crystal_code"] = np.nan
    before = df["crystal_code"].fillna("")
    # Apply function, then assign with the current index to keep alignment stable
    new_vals, _flags = zip(*df["crystal_code"].apply(extract_digits_after_ccdc))
    df["crystal_code"] = pd.Series(new_vals, index=df.index).astype(str).str.strip()
    print_header("crystal_code cleaned")
    print(f"crystal_code changed: {count_changes(before, df['crystal_code'])}")

    # 4b) linker columns: remove trailing parenthetical
    for lk in ["linker_1", "linker_2", "linker_3"]:
        if lk in df.columns:
            before = df[lk].fillna("")
            vals, _flags = zip(*df[lk].apply(remove_linker_trailing_parens))
            df[lk] = pd.Series(vals, index=df.index).astype(str).str.strip()
            print(f"{lk} trailing parens removed: {count_changes(before, df[lk])}")

    if apply_linker_synonym_merge:
        # 4b.1) Linker deep clean: synonym merge (put this after the 4b loop, before 4c)
        print_header("Linker deep clean: synonym merge")

        def _norm_linker_key(s: str) -> str:
            if not is_filled(s):
                return ""
            s = str(s)
            # unify primes and hyphens, collapse spaces
            s = s.replace("′", "'").replace("’", "'").replace("‘", "'")
            s = s.replace("–", "-").replace("—", "-").replace("−", "-")
            s = re.sub(r"\s+", " ", s).strip().lower()
            # tighten punctuation spacing
            s = re.sub(r"\s*-\s*", "-", s)
            s = re.sub(r"\s*'\s*", "'", s)
            s = re.sub(r"\(\s*", "(", s)
            s = re.sub(r"\s*\)", ")", s)
            return s

        # Canonical names on the right; keys are normalized lowercase forms on the left
        linker_map = {
            # terephthalic acid group
            "terephthalic acid": "terephthalic acid",
            "benzene-1,4-dicarboxylic acid": "terephthalic acid",
            "1,4-benzenedicarboxylic acid": "terephthalic acid",
            "p-phthalic acid": "terephthalic acid",
            "bdc": "terephthalic acid",

            # 2-aminoterephthalic acid
            "2-aminoterephthalic acid": "2-aminoterephthalic acid",
            "2-amino-1,4-benzenedicarboxylic acid": "2-aminoterephthalic acid",
            "nh2-bdc": "2-aminoterephthalic acid",

            # trimesic acid group
            "1,3,5-benzenetricarboxylic acid": "benzene-1,3,5-tricarboxylic acid",
            "benzene-1,3,5-tricarboxylic acid": "benzene-1,3,5-tricarboxylic acid",
            "trimesic acid": "benzene-1,3,5-tricarboxylic acid",
            "btc": "benzene-1,3,5-tricarboxylic acid",

            # isophthalic acid group
            "isophthalic acid": "isophthalic acid",
            "benzene-1,3-dicarboxylic acid": "isophthalic acid",
            "1,3-benzenedicarboxylic acid": "isophthalic acid",

            # naphthalenedicarboxylic acids
            "1,4-naphthalenedicarboxylic acid": "1,4-naphthalenedicarboxylic acid",
            "naphthalene-1,4-dicarboxylic acid": "1,4-naphthalenedicarboxylic acid",
            "2,6-naphthalenedicarboxylic acid": "2,6-naphthalenedicarboxylic acid",
            "naphthalene-2,6-dicarboxylic acid": "2,6-naphthalenedicarboxylic acid",

            # heteroaromatic dicarboxylic acids
            "2,5-pyridinedicarboxylic acid": "2,5-pyridinedicarboxylic acid",
            "pyridine-2,5-dicarboxylic acid": "2,5-pyridinedicarboxylic acid",
            "2,5-thiophenedicarboxylic acid": "2,5-thiophenedicarboxylic acid",
            "thiophene-2,5-dicarboxylic acid": "2,5-thiophenedicarboxylic acid",

            # tetrafluoroterephthalic
            "tetrafluoroterephthalic acid": "tetrafluoroterephthalic acid",
            "2,3,5,6-tetrafluoro-1,4-benzenedicarboxylic acid": "tetrafluoroterephthalic acid",

            # biphenyl-4,4'-dicarboxylic acid
            "biphenyl-4,4'-dicarboxylic acid": "biphenyl-4,4'-dicarboxylic acid",
            "biphenyl-4,4′-dicarboxylic acid": "biphenyl-4,4'-dicarboxylic acid",
            "4,4'-biphenyldicarboxylic acid": "biphenyl-4,4'-dicarboxylic acid",
            "4,4′-biphenyldicarboxylic acid": "biphenyl-4,4'-dicarboxylic acid",
            "bpdc": "biphenyl-4,4'-dicarboxylic acid",

            # 4,4'-bipyridine
            "4,4'-bipyridine": "4,4'-bipyridine",
            "4,4′-bipyridine": "4,4'-bipyridine",

            # other named linkers seen in your list
            "4,4'-oxybis(benzoic acid)": "4,4'-oxybis(benzoic acid)",
            "4,4′-oxybis(benzoic acid)": "4,4'-oxybis(benzoic acid)",
            "4,4'-sulfonyldibenzoic acid": "4,4'-sulfonyldibenzoic acid",
            "4,4′-sulfonyldibenzoic acid": "4,4'-sulfonyldibenzoic acid",
            "2-methylimidazole": "2-methylimidazole",
            "2-methyl imidazole": "2-methylimidazole",
            "1,4-diazabicyclo[2.2.2]octane": "1,4-diazabicyclo[2.2.2]octane",
            "dabco": "1,4-diazabicyclo[2.2.2]octane",
            "tetrakis(4-carboxyphenyl)porphyrin": "tetrakis(4-carboxyphenyl)porphyrin",
            "tcpp": "tetrakis(4-carboxyphenyl)porphyrin",
            "1,3-bis(4-pyridyl)propane": "1,3-bis(4-pyridyl)propane",
            "bpp": "1,3-bis(4-pyridyl)propane",
            "1,4-bis(imidazol-1-ylmethyl)benzene": "1,4-bis(imidazol-1-ylmethyl)benzene",
            "bimb": "1,4-bis(imidazol-1-ylmethyl)benzene",
            "2,5-dihydroxyterephthalic acid": "2,5-dihydroxyterephthalic acid",
            "2,5-dihydroxy-1,4-benzenedicarboxylic acid": "2,5-dihydroxyterephthalic acid",
            "2-nitroterephthalic acid": "2-nitroterephthalic acid",
            "2-nitro-1,4-benzenedicarboxylic acid": "2-nitroterephthalic acid",
            "4-bpmp": "bis(pyridylmethyl)piperazine"
        }

        def canon_linker(val):
            if not is_filled(val):
                return val
            s = str(val).strip()
            # drop trailing "(H2L1)" style tags if present
            s, _ = remove_linker_trailing_parens(s)
            key = _norm_linker_key(s)

            if key in linker_map:
                return linker_map[key]

            # programmatic merges for common patterns
            if re.search(r"\bbenzene[-\s]?1,4[-\s]?dicarboxylic acid\b", key) or re.search(r"\b1,4[-\s]?benzenedicarboxylic acid\b", key):
                return "terephthalic acid"
            if re.search(r"\bbenzene[-\s]?1,3,5[-\s]?tricarboxylic acid\b", key) or "1,3,5-benzenetricarboxylic acid" in key:
                return "benzene-1,3,5-tricarboxylic acid"
            if re.search(r"\bbenzene[-\s]?1,3[-\s]?dicarboxylic acid\b", key) or "1,3-benzenedicarboxylic acid" in key:
                return "isophthalic acid"
            if re.search(r"\bnaphthalene[-\s]?1,4[-\s]?dicarboxylic acid\b", key):
                return "1,4-naphthalenedicarboxylic acid"
            if re.search(r"\bnaphthalene[-\s]?2,6[-\s]?dicarboxylic acid\b", key):
                return "2,6-naphthalenedicarboxylic acid"
            if re.search(r"\bpyridine[-\s]?2,5[-\s]?dicarboxylic acid\b", key):
                return "2,5-pyridinedicarboxylic acid"
            if re.search(r"\bthiophene[-\s]?2,5[-\s]?dicarboxylic acid\b", key):
                return "2,5-thiophenedicarboxylic acid"
            if "4,4'-bipyridine" in key or "4,4′-bipyridine" in key:
                return "4,4'-bipyridine"
            if "biphenyl-4,4'-dicarboxylic acid" in key or "4,4'-biphenyldicarboxylic acid" in key or "4,4′-biphenyldicarboxylic acid" in key:
                return "biphenyl-4,4'-dicarboxylic acid"

            return re.sub(r"\s+", " ", s).strip()

        # apply to linker columns
        for lk in ["linker_1", "linker_2", "linker_3"]:
            if lk in df.columns:
                before = df[lk].fillna("")
                df[lk] = df[lk].apply(canon_linker).astype(str).str.strip()
                print(f"{lk}: synonym merge changes: {count_changes(before, df[lk])}")

    # 4c) temperature handling
    for col in ["temperature_c", "temperature_c_text"]:
        if col not in df.columns:
            df[col] = np.nan

    txt = df["temperature_c_text"].astype(str)
    needs_25 = (~filled_series(df["temperature_c"])) & (
        txt.str.contains(r"\bRT\b", case=True, na=False) | txt.str.contains("room temperature", case=False, na=False)
    )
    df.loc[needs_25, "temperature_c"] = "25"

    if strict_slow_temperature_filter:
        # Tightened negative-plans option: keep slow cooling unless explicitly slow evaporation/diffusion.
        drop_temp_text = txt.str.contains(r"\bmicrowave\b", case=False, na=False) | \
                         txt.str.contains(r"\bevaporation\b", case=False, na=False) | \
                         txt.str.contains(r"\bslow evaporation\b|\bslow diffusion\b", case=False, na=False)
        drop_msg = "microwave or (slow) evaporation or slow diffusion"
    else:
        # Positive and negative-basic option.
        drop_temp_text = txt.str.contains("microwave", case=False, na=False) | \
                         txt.str.contains("evaporation", case=False, na=False) | \
                         txt.str.contains("slow", case=False, na=False)
        drop_msg = "microwave or evaporation or slow"
    print_header("temperature_c cleaning")
    print(f"Rows to drop due to temperature_c_text containing {drop_msg}: {int(drop_temp_text.sum())}")
    df = df[~drop_temp_text].copy()
    df = _reset(df, "temperature text screen") if reset_after_filters else df

    still_empty_temp = ~filled_series(df["temperature_c"])
    print(f"Dropping rows with empty temperature_c after filling: {int(still_empty_temp.sum())}")
    df = df[~still_empty_temp].copy()
    df = _reset(df, "drop rows with empty temperature_c") if reset_after_filters else df
    print(f"Rows left after temperature filters: {len(df)}")

    # 4d) metals: replace ' × ' with '·' and strip trailing parens except ' (anhydrous)'
    metal_cols = ["metal_1", "metal_2", "metal_3"]
    for mc in metal_cols:
        if mc not in df.columns:
            df[mc] = np.nan

    # normalize middle dot
    for mc in metal_cols:
        before = df[mc].fillna("").astype(str)
        after_list = [normalize_x_to_middle_dot(v)[0] for v in df[mc]]
        after_series = pd.Series(after_list, index=df.index)
        df[mc] = after_series
        print(f"{mc}: replaced ' × ' with '·' in {count_changes(before, after_series.fillna(''))} rows")

    # strip trailing parentheses with rule
    for mc in metal_cols:
        before = df[mc].fillna("").astype(str)
        new_vals = []
        for v in df[mc]:
            nv, _ch = strip_trailing_parens(v, keep_when="(anhydrous)")
            new_vals.append(nv)
        df[mc] = pd.Series(new_vals, index=df.index).astype(str).str.strip()
        print(f"{mc}: trailing parentheses handled in {count_changes(before, df[mc].fillna(''))} rows")

    # 4e) metal standardization dictionary (to canonical like FeCl3·6H2O)
    metal_map = {
        # Chlorides and oxychlorides
        "zrcl4": "ZrCl4",
        "zirconium tetrachloride": "ZrCl4",
        "zrocl2·8h2o": "ZrOCl2·8H2O",
        "zrocl2.8h2o": "ZrOCl2·8H2O",
        # Aluminum
        "alcl3·6h2o": "AlCl3·6H2O",
        "alcl3.6h2o": "AlCl3·6H2O",
        "aluminium nitrate nonahydrate": "Al(NO3)3·9H2O",
        # Iron
        "fecl3·6h2o": "FeCl3·6H2O",
        "iron(iii) chloride hexahydrate": "FeCl3·6H2O",
        "iron powder": "Fe",
        # Zinc
        "zinc nitrate hexahydrate": "Zn(NO3)2·6H2O",
        # Copper
        "cu(no3)2·h2o": "Cu(NO3)2·H2O",
        "cu(no3)2×h2o": "Cu(NO3)2·H2O",
        "copper(ii) nitrate dihydrate (2.5-hydrate)": "Cu(NO3)2·2.5H2O",
        # Indium
        "indium(iii) nitrate tetrahydrate-hemihydrate": "In(NO3)3·4.5H2O",
        # Rare earth hydroxides
        "gadolinium(iii) hydroxide": "Gd(OH)3",
        "dysprosium(iii) hydroxide": "Dy(OH)3",
        "holmium(iii) hydroxide": "Ho(OH)3",
        "erbium(iii) hydroxide": "Er(OH)3",
        # Titanium
        "tio(acac)2": "TiO(acac)2",
        "ti(i-propoxide)4": "Ti(iPrO)4",
        "ti(ipro)4": "Ti(iPrO)4",
        "tii(pro)4": "Ti(iPrO)4",
    }

    def canon_metal(val):
        if not is_filled(val):
            return val
        s = str(val).strip()
        s_norm = s.replace(" × ", "·")
        s_norm = re.sub(r"\s+", " ", s_norm).strip()
        key = s_norm.lower()
        if key in metal_map:
            return metal_map[key]
        # hydrate punctuation variant
        key2 = key.replace("·", ".")
        if key2 in metal_map:
            return metal_map[key2]
        return s_norm

    for mc in metal_cols:
        before = df[mc].fillna("").astype(str)
        df[mc] = df[mc].apply(canon_metal).astype(str).str.strip()
        print(f"{mc}: standardized entries changed: {count_changes(before, df[mc])}")

    # final normalization of any stray ×
    for mc in metal_cols:
        before = df[mc].fillna("").astype(str)
        df[mc] = df[mc].str.replace(r"\s*×\s*", "·", regex=True)
        print(f"{mc}: final '×' to '·' normalization count: {count_changes(before, df[mc].fillna(''))}")

    # ---------- pore_diameter_A cleanup ----------
    # Use a robust cutoff to avoid removing legitimate large pores.
    if "pore_diameter_A" in df.columns:
        pore_vals = pd.to_numeric(df["pore_diameter_A"], errors="coerce")
        # Use 99th percentile as an outlier guard. Fall back to 2x mean if quantile is NaN.
        q99 = pore_vals.dropna().quantile(0.99) if pore_vals.notna().any() else np.nan
        if np.isfinite(q99):
            df.loc[pore_vals > q99, "pore_diameter_A"] = ""
        else:
            mean_val = pore_vals.dropna().mean()
            if not np.isnan(mean_val):
                df.loc[pore_vals > 2 * mean_val, "pore_diameter_A"] = ""

    # ---------- topology_code cleaning ----------
    if "topology_code" not in df.columns:
        df["topology_code"] = np.nan

    topo = df["topology_code"].fillna("").astype(str).str.strip()

    # Identify which entries are either exactly three letters or three letters + '-' + one letter
    valid_topology_pattern = r"^[A-Za-z]{3}(-[A-Za-z])?$"
    invalid_mask = ~topo.str.match(valid_topology_pattern)

    # Count and show representative invalid entries
    invalid_examples = topo[invalid_mask].replace("", np.nan).dropna().unique()
    print_header("topology_code cleanup")
    print(f"Total rows checked: {len(df)}")
    print(f"Entries with invalid (non-three-letter) topology_code: {invalid_mask.sum()}")

    if len(invalid_examples) > 0:
        print("Examples of removed topology_code values:")
        print(", ".join(invalid_examples[:10]))
    else:
        print("No invalid topology_code values found.")

    # Set invalid ones to empty string
    df.loc[invalid_mask, "topology_code"] = ""

    # ---------- 5) Summary tables ----------
    print_header("Summary after cleaning and filtering")

    if "doi" not in df.columns:
        df["doi"] = np.nan

    papers_left = df["doi"].dropna().astype(str).str.strip().replace("", np.nan).dropna().nunique()
    rows_left = len(df)
    print(f"Papers left (unique doi): {papers_left}")
    print(f"Rows left: {rows_left}")

    yes_articles = df.loc[df[col_atof].str.strip().str.lower() == "yes", "doi"].dropna().astype(str).str.strip().nunique()
    print(f"Articles with article_trial_or_failure == yes (unique doi): {yes_articles}")

    def print_uniques_and_top(df, cols, title):
        print_header(title)
        for c in cols:
            if c in df.columns:
                series = df[c].dropna().astype(str).str.strip()
                series = series[series != ""]
                u = series.nunique()
                print(f"{c}: unique values = {u}")
                vc = series.value_counts().head(10)
                if len(vc) > 0:
                    print("Top 10:")
                    print(vc.to_string())
                else:
                    print("Top 10: none")
            else:
                print(f"{c}: column not found")

    print_uniques_and_top(df, ["metal_1", "metal_2", "metal_3"], "Unique metals")
    print_uniques_and_top(df, ["linker_1", "linker_2", "linker_3"], "Unique linkers")
    print_uniques_and_top(df, ["modulator_1", "modulator_2", "modulator_3"], "Unique modulators")
    print_uniques_and_top(df, ["solvent_main_abbr"], "Unique solvent_main_abbr")
    print_uniques_and_top(df, ["temperature_c"], "Unique temperature_c")
    print_uniques_and_top(df, ["time_h"], "Unique time_h")
    print_uniques_and_top(df, ["topology_code"], "Unique topology_code")

    # Numeric distributions
    def histogram_and_count(df, col, title):
        print_header(f"{title} distribution")
        series = df[col] if col in df.columns else pd.Series(dtype=str)
        nonempty = series.dropna().astype(str).str.strip()
        nonempty = nonempty[nonempty != ""]
        vals = pd.to_numeric(nonempty, errors="coerce")
        count_nonnull = int(vals.notna().sum())
        print(f"{col}: numeric non empty count = {count_nonnull}")
        if count_nonnull > 0:
            plt.figure()
            vals.dropna().astype(float).plot(kind="hist", bins=20, title=title)
            plt.xlabel(col)
            plt.ylabel("Count")
            plt.show()
        return count_nonnull

    _ = histogram_and_count(df, "pore_diameter_A", "Pore diameter (Å)")
    _ = histogram_and_count(df, "BET_surface_area_m2g", "BET surface area (m²/g)")
    _ = histogram_and_count(df, "tga_decomposition_temp_c", "TGA decomposition temp (°C)")

    # ---------- Topology report ----------
    print_header("Topology report")

    # Normalize: strip, drop empty, lower for case-insensitive counting
    topo_norm = (
        df["topology_code"]
        .astype(str)
        .str.strip()
    )
    topo_nonempty = topo_norm[topo_norm != ""]
    topo_counts = topo_nonempty.str.lower().value_counts()

    print(f"Non-empty topology_code rows: {int(topo_counts.sum())}")
    print(f"Unique topology codes (case-insensitive): {int(topo_counts.size)}")

    print("Top 10 topology codes:")
    print(topo_counts.head(10).to_string())

    # Stability counts
    def stability_counts(col):
        if col not in df.columns:
            print(f"{col}: column not found")
            return
        s = df[col].apply(safe_lower)
        s = s.replace("", np.nan)
        total_yes = int((s == "yes").sum())
        total_no = int((s == "no").sum())
        total_not_reported = int((s == "not_reported").sum())
        total_empty = int(s.isna().sum())
        print_header(f"{col} counts")
        print(f"yes: {total_yes}")
        print(f"no: {total_no}")
        print(f"not_reported: {total_not_reported}")
        print(f"empty: {total_empty}")
        vc = s.value_counts(dropna=False).head(10)
        print("Top 10 values:")
        print(vc.to_string())

    stability_counts("air_stable")
    stability_counts("water_stable")

    # ---------- write ----------
    # Replace NaN with empty string before saving
    df = df.fillna("")

    # Use UTF-8 with BOM for special symbols like "·"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print_header(f"Wrote cleaned CSV to {out_path.name}")
    return Path(output_path)

