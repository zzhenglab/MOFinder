"""Derived features for curated synthesis records."""

def clean(input_path, output_path):
    """Calculate the metal:linker ratio and metal concentration, then write the CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    # - M:L ratio uses mmol units, with an explicit 1:1 amount-text fallback
    # - metel_concnertation = round( (metal_1_amount_value / solvent_main_ml) * 1000 ) as an integer string
    # - Any legacy "metal_1_concentration_M" column is removed
    # - Prints success and failure counts for both calculations

    import re
    import math
    import numpy as np
    import pandas as pd
    from pathlib import Path




    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH.name} not found")

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

    def parse_num(s):
        t = str(s).strip()
        if t == "":
            return None
        if "/" in t:
            num, den = t.split("/", 1)
            try:
                val = float(num) / float(den)
            except Exception:
                return None
        else:
            try:
                val = float(t)
            except Exception:
                return None
        return val if np.isfinite(val) else None

    def is_mmol(u):
        return str(u).strip().lower() == "mmol"

    # Detect an explicit "1:1" anywhere in the text
    RATIO_1_1_PAT = re.compile(r"(?<!\d)1\s*[:：]\s*1(?!\d)")

    df = pd.read_csv(IN_PATH, dtype=str, encoding="utf-8")

    # Ensure required columns exist
    for c in [
        "metal_1_amount_value","metal_1_amount_unit","metal_1_amount_text",
        "metal_2_amount_unit","metal_3_amount_unit",
        "linker_1_amount_value","linker_1_amount_unit",
        "linker_2_amount_unit","linker_3_amount_unit",
        "solvent_main_ml","temperature_c"
    ]:
        if c not in df.columns:
            df[c] = ""

    # Remove any legacy concentration column if present
    to_drop = [c for c in df.columns if c.strip().lower() == "metal_1_concentration_m"]
    if to_drop:
        df.drop(columns=to_drop, inplace=True)

    # Prepare output columns as strings
    ratio_col = [""] * len(df)
    conc_mM_col = [""] * len(df)  # metel_concnertation

    # Counters for M:L ratio
    ratio_ok = 0
    ratio_fallback = 0
    ratio_fail_unit = 0
    ratio_fail_missing = 0
    ratio_fail_non_numeric = 0
    ratio_fail_zero = 0

    # Counters for metel_concnertation (mM integer)
    conc_ok = 0
    conc_fail_unit = 0
    conc_fail_missing = 0
    conc_fail_non_numeric = 0
    conc_fail_zero_vol = 0

    for idx, row in df.iterrows():
        # ---------- M:L ratio ----------
        m1_u = row.get("metal_1_amount_unit", "")
        m2_u = row.get("metal_2_amount_unit", "")
        m3_u = row.get("metal_3_amount_unit", "")
        l1_u = row.get("linker_1_amount_unit", "")
        l2_u = row.get("linker_2_amount_unit", "")
        l3_u = row.get("linker_3_amount_unit", "")

        # All present units must be mmol
        units_ok = is_mmol(m1_u) and is_mmol(l1_u)
        for extra_u in (m2_u, m3_u, l2_u, l3_u):
            if is_filled(extra_u) and not is_mmol(extra_u):
                units_ok = False
                break

        if units_ok:
            m1_val = parse_num(row.get("metal_1_amount_value", ""))
            l1_val = parse_num(row.get("linker_1_amount_value", ""))
            if m1_val is None or l1_val is None:
                ratio_fail_non_numeric += 1
            elif l1_val == 0:
                ratio_fail_zero += 1
            else:
                ratio = m1_val / l1_val
                ratio_col[idx] = f"{ratio:.2f}"
                ratio_ok += 1
        else:
            txt = row.get("metal_1_amount_text", "")
            if is_filled(txt) and RATIO_1_1_PAT.search(str(txt)):
                ratio_col[idx] = "1.00"
                ratio_fallback += 1
            else:
                if not is_mmol(m1_u) or not is_mmol(l1_u):
                    ratio_fail_unit += 1
                else:
                    ratio_fail_missing += 1

        # ---------- metel_concnertation (mM integer) ----------
        if is_mmol(m1_u):
            m1_val = parse_num(row.get("metal_1_amount_value", ""))
            vol_ml = parse_num(row.get("solvent_main_ml", ""))
            if m1_val is None or vol_ml is None:
                conc_fail_non_numeric += 1
            elif vol_ml <= 0:
                conc_fail_zero_vol += 1
            else:
                conc_M = m1_val / vol_ml              # mmol per mL equals mol per L
                if not np.isfinite(conc_M):
                    conc_fail_non_numeric += 1
                else:
                    conc_mM = conc_M * 1000.0         # convert to mM
                    conc_mM_col[idx] = str(int(round(conc_mM)))
                    conc_ok += 1
        else:
            conc_fail_unit += 1

    # Insert new columns before temperature_c
    insert_at = df.columns.get_loc("temperature_c") if "temperature_c" in df.columns else len(df.columns)
    df.insert(insert_at, "metel_concnertation", conc_mM_col)
    insert_at = df.columns.get_loc("temperature_c") if "temperature_c" in df.columns else len(df.columns)
    df.insert(insert_at, "M_L_ratio", ratio_col)

    # Save
    df = df.fillna("")
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    # Reports
    print_header("M:L ratio summary")
    print(f"Computed with mmol units: {ratio_ok}")
    print(f"Computed via '1:1' fallback in metal_1_amount_text: {ratio_fallback}")
    print(f"Failed due to non-mmol or inconsistent units: {ratio_fail_unit}")
    print(f"Failed due to non numeric values: {ratio_fail_non_numeric}")
    print(f"Failed due to zero linker_1 amount: {ratio_fail_zero}")
    print(f"Other failures or missing pieces: {ratio_fail_missing}")

    print_header("Concentration summary (metel_concnertation in mM, integer)")
    print(f"Computed: {conc_ok}")
    print(f"Failed due to metal_1 unit not mmol: {conc_fail_unit}")
    print(f"Failed due to non numeric amount or volume: {conc_fail_non_numeric}")
    print(f"Failed due to zero or nonpositive volume: {conc_fail_zero_vol}")

    print_header(f"Wrote updated CSV to {OUT_PATH.name}")
    return df
