from __future__ import annotations

import argparse
from pathlib import Path

from utils import FULL_BRANCHES, branch_paths, configure_utf8_stdio


def run_analysis_report(input_path: str | Path | None = None, *, data_dir: str | Path | None = None, top_n_metals=None, top_n_linkers=None, pairs_csv_basename: str = "metal_linker_pairs_report") -> Path:
    """Run the final analysis/report routine and return the dataset path used."""
    import re
    from collections import Counter

    import numpy as np
    import pandas as pd

    from utils import DATA_DIR

    data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    input_path = Path(input_path) if input_path is not None else None
    # Summaries, time/temperature analysis, and Metal × Linker CSV
    import pandas as pd
    import numpy as np
    import re
    from collections import Counter

    # ---------------- helpers ----------------
    def print_header(msg: str):
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

    def first_existing(paths):
        for p in paths:
            if Path(p).exists():
                return Path(p)
        return None

    def find_latest_dataset():
        preferred = [
            data_dir / "mof_extraction_1_2_3_4_5_6.csv",
            data_dir / "mof_extraction_1_2_3_4_5.csv",
            data_dir / "mof_extraction_1_2_3_4.csv",
            data_dir / "mof_extraction_1_2_3.csv",
            data_dir / "mof_extraction_1_2.csv",
            data_dir / "mof_extraction_1.csv",
            data_dir / "mof_extraction.csv",
        ]
        p = first_existing(preferred)
        if p:
            return p
        cands = list(data_dir.glob("mof_extraction*.csv"))
        if not cands:
            raise FileNotFoundError("No mof_extraction*.csv files found")
        def score(path):
            nums = re.findall(r"\d+", path.name)
            return (len(nums), path.stat().st_mtime)
        cands.sort(key=score, reverse=True)
        return cands[0]

    def flattened_series(df, cols, include_empty=False):
        parts = []
        for c in cols:
            if c in df.columns:
                parts.append(df[c].astype(str).fillna("").str.strip())
        if not parts:
            return pd.Series([], dtype=str)
        s = pd.concat(parts, ignore_index=True)
        return s if include_empty else s[s != ""]

    def value_counts_table(series, top=30, include_empty=False, empty_label="(empty)"):
        s = series.astype(str).str.strip()
        if include_empty:
            s = s.replace({"": empty_label})
        else:
            s = s[s != ""]
        vc = s.value_counts()
        if vc.empty:
            print("None")
        else:
            if top is None:
                print(vc.to_string())
            else:
                print(vc.head(top).to_string())

    def parse_num_series(series):
        s = series.astype(str).str.strip()
        s = s[s != ""]
        nums = pd.to_numeric(s, errors="coerce").dropna()
        return nums

    def binned_counts(values, bins, labels):
        cats = pd.cut(values, bins=bins, labels=labels, include_lowest=True, right=True)
        return cats.value_counts().reindex(labels, fill_value=0)

    # metal element extraction from a precursor string or formula
    METAL_NAME_TO_SYM = {
        "lithium":"Li","sodium":"Na","potassium":"K","rubidium":"Rb","cesium":"Cs",
        "beryllium":"Be","magnesium":"Mg","calcium":"Ca","strontium":"Sr","barium":"Ba",
        "aluminum":"Al","aluminium":"Al","gallium":"Ga","indium":"In","thallium":"Tl",
        "germanium":"Ge","silicon":"Si","tin":"Sn","lead":"Pb","antimony":"Sb","bismuth":"Bi","boron":"B",
        "scandium":"Sc","yttrium":"Y","titanium":"Ti","zirconium":"Zr","hafnium":"Hf",
        "vanadium":"V","niobium":"Nb","tantalum":"Ta","chromium":"Cr","molybdenum":"Mo","tungsten":"W",
        "manganese":"Mn","technetium":"Tc","rhenium":"Re","iron":"Fe","ruthenium":"Ru","osmium":"Os",
        "cobalt":"Co","rhodium":"Rh","iridium":"Ir","nickel":"Ni","palladium":"Pd","platinum":"Pt",
        "copper":"Cu","silver":"Ag","gold":"Au","zinc":"Zn","cadmium":"Cd","mercury":"Hg",
        "lanthanum":"La","cerium":"Ce","praseodymium":"Pr","neodymium":"Nd","promethium":"Pm",
        "samarium":"Sm","europium":"Eu","gadolinium":"Gd","terbium":"Tb","dysprosium":"Dy",
        "holmium":"Ho","erbium":"Er","thulium":"Tm","ytterbium":"Yb","lutetium":"Lu",
        "thorium":"Th","uranium":"U",
        "ferrous":"Fe","ferric":"Fe","cuprous":"Cu","cupric":"Cu","stannous":"Sn","stannic":"Sn",
        "plumbous":"Pb","plumbic":"Pb","chromous":"Cr","chromic":"Cr","manganous":"Mn","manganic":"Mn",
        "cerous":"Ce","ceric":"Ce","cobaltous":"Co",
        "zinc(ii)":"Zn","nickel(ii)":"Ni","copper(ii)":"Cu","chromium(iii)":"Cr",
        "ytterbium(iii)":"Yb","zinc(ii) nitrate":"Zn",
    }
    METAL_SYMBOLS = set(METAL_NAME_TO_SYM.values())
    NON_METAL_LIKELY = {"H","C","N","O","F","Cl","Br","I","P","S"}
    EL_TOKEN = re.compile(r"[A-Z][a-z]?")

    def first_metal_symbol_from_formula(s: str):
        if not is_filled(s):
            return None
        text = str(s).replace("·", "")
        for t in EL_TOKEN.findall(text):
            if t in METAL_SYMBOLS and t not in NON_METAL_LIKELY:
                return t
        for t in EL_TOKEN.findall(text):
            if t in {"B","Si"}:
                return t
        low = text.lower()
        for name, sym in sorted(METAL_NAME_TO_SYM.items(), key=lambda kv: len(kv[0]), reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", low):
                return sym
        return None

    # ---------------- load ----------------
    csv_path = Path(input_path) if input_path is not None else find_latest_dataset()
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig", low_memory=False)
    print_header(f"Dataset used: {csv_path.name}")
    print(f"Rows: {len(df)}")
    if "applications" not in df.columns and "application" in df.columns:
        df["applications"] = df["application"]

    # ensure needed columns exist
    for c in [
        "metal_1","metal_2","metal_3",
        "linker_1","linker_2","linker_3",
        "modulator_1","modulator_2","modulator_3",
        "solvent_main","solvent_main_abbr","solvent_secondary","solvent_secondary_abbr",
        "M_L_ratio","metel_concnertation","time_h","temperature_c","doi",
        "metal_cluster_connectivity_classified","metal_cluster_connectivity",
        "topology_code","tga_decomposition_temp_c","water_stable","air_stable","applications"
    ]:
        if c not in df.columns:
            df[c] = ""

    # ---------------- core rankings and counts ----------------
    # metal precursors
    metal_precursors = flattened_series(df, ["metal_1","metal_2","metal_3"])
    print_header("Metal precursors - ranking")
    print(f"Unique metal precursors: {metal_precursors.nunique()}")
    value_counts_table(metal_precursors, top=50)

    # metals (elements)
    metals_all = []
    for c in ["metal_1","metal_2","metal_3"]:
        metals_all.extend(df[c].astype(str).map(first_metal_symbol_from_formula).dropna().tolist())
    metals_series = pd.Series(metals_all, dtype=str)
    unique_metals = sorted(metals_series.unique().tolist())
    print_header("Metals (elements) - ranking")
    print(f"Unique metals: {len(unique_metals)}")
    vc_met = metals_series.value_counts()
    print(vc_met.to_string())

    # linkers
    linkers_all = flattened_series(df, ["linker_1","linker_2","linker_3"])
    print_header("Organic linkers - ranking")
    print(f"Unique organic linkers: {linkers_all.nunique()}")
    value_counts_table(linkers_all, top=50)

    # modulators (empty included as a category)
    mods_all = flattened_series(df, ["modulator_1","modulator_2","modulator_3"], include_empty=True)
    print_header("Modulators - ranking (empty counted as one)")
    print(f"Unique modulators including empty: {mods_all.replace({'': '(empty)'}).nunique()}")
    value_counts_table(mods_all, top=50, include_empty=True)

    # solvents (prefer abbreviations, then names)
    solv_parts = []
    for col in ["solvent_main_abbr","solvent_secondary_abbr","solvent_main","solvent_secondary"]:
        if col in df.columns:
            s = df[col].astype(str).str.strip()
            solv_parts.append(s[s != ""])
    solvents_all = pd.concat(solv_parts, ignore_index=True) if solv_parts else pd.Series([], dtype=str)
    print_header("Solvents - ranking")
    print(f"Unique solvents: {solvents_all.nunique()}")
    value_counts_table(solvents_all, top=50)

    # M:L ratio
    ratio_series = df["M_L_ratio"].astype(str).str.strip()
    ratio_series = ratio_series[ratio_series != ""]
    print_header("M:L ratio - ranking")
    print(f"Unique M:L ratios: {ratio_series.nunique()}")
    value_counts_table(ratio_series, top=30)

    # concentration (mM, integer in your pipeline)
    conc_col = "metel_concnertation" if "metel_concnertation" in df.columns else None
    conc_series = df[conc_col].astype(str).str.strip() if conc_col else pd.Series([], dtype=str)
    conc_series = conc_series[conc_series != ""]
    print_header("Metal concentration (mM) - ranking")
    print(f"Unique concentrations: {conc_series.nunique()}")
    value_counts_table(conc_series, top=30)

    # time_h analysis
    print_header("time_h analysis")
    time_vals = parse_num_series(df["time_h"])
    print(f"Unit: h")
    print(f"Non empty numeric count: {len(time_vals)}")
    if len(time_vals) > 0:
        print(f"Unique numeric values: {pd.Series(time_vals).nunique()}")
        print(f"Min: {time_vals.min():.3g}  Q1: {time_vals.quantile(0.25):.3g}  Median: {time_vals.median():.3g}  Q3: {time_vals.quantile(0.75):.3g}  Max: {time_vals.max():.3g}  Mean: {time_vals.mean():.3g}")
        bins_t = [-np.inf, 1, 6, 24, 72, np.inf]
        labels_t = ["<=1 h","1-6 h","6-24 h","24-72 h",">72 h"]
        print("\nTime buckets:")
        print(binned_counts(time_vals, bins=bins_t, labels=labels_t).to_string())
    print("\nTop 20 raw time_h entries:")
    value_counts_table(df["time_h"], top=20, include_empty=False)

    # temperature_c analysis
    print_header("temperature_c analysis")
    temp_vals = parse_num_series(df["temperature_c"])
    print(f"Unit: C")
    print(f"Non empty numeric count: {len(temp_vals)}")
    if len(temp_vals) > 0:
        print(f"Unique numeric values: {pd.Series(temp_vals).nunique()}")
        print(f"Min: {temp_vals.min():.3g}  Q1: {temp_vals.quantile(0.25):.3g}  Median: {temp_vals.median():.3g}  Q3: {temp_vals.quantile(0.75):.3g}  Max: {temp_vals.max():.3g}  Mean: {temp_vals.mean():.3g}")
        bins_T = [-np.inf, 40, 80, 120, 200, np.inf]
        labels_T = ["<=40 C","40-80 C","80-120 C","120-200 C",">200 C"]
        print("\nTemperature buckets:")
        print(binned_counts(temp_vals, bins=bins_T, labels=labels_T).to_string())
    print("\nTop 20 raw temperature_c entries:")
    value_counts_table(df["temperature_c"], top=20, include_empty=False)

    # units present by column name
    time_units = set()
    temp_units = set()
    for col in df.columns:
        m = re.match(r"^time_([A-Za-z]+)$", col)
        if m and df[col].apply(is_filled).any():
            time_units.add(m.group(1))
        t = re.match(r"^temperature_([A-Za-z]+)$", col)
        if t and df[col].apply(is_filled).any():
            temp_units.add(t.group(1))
    print_header("Units present")
    print(f"Time units present: {sorted(time_units) if time_units else ['h'] if 'time_h' in df.columns else []} "
          f"(count: {len(time_units) if time_units else (1 if 'time_h' in df.columns else 0)})")
    print(f"Temperature units present: {sorted(temp_units) if temp_units else ['c'] if 'temperature_c' in df.columns else []} "
          f"(count: {len(temp_units) if temp_units else (1 if 'temperature_c' in df.columns else 0)})")

    # connectivity classification
    conn_col = "metal_cluster_connectivity_classified" if df["metal_cluster_connectivity_classified"].astype(str).str.strip().any() else "metal_cluster_connectivity"
    conn_series = df[conn_col].astype(str).str.strip()
    conn_series = conn_series[conn_series != ""]
    print_header("Metal connectivity classification - ranking")
    print(f"Unique labels: {conn_series.nunique()}")
    value_counts_table(conn_series, top=40)

    # topology codes
    topo_series = df["topology_code"].astype(str).str.strip()
    topo_series = topo_series[topo_series != ""]
    print_header("Topology codes - ranking")
    print(f"Unique topology codes: {topo_series.str.lower().nunique()}")
    value_counts_table(topo_series.str.lower(), top=40)

    # TGA decomposition temperature
    tga_series = df["tga_decomposition_temp_c"].astype(str).str.strip()
    tga_series = tga_series[tga_series != ""]
    tga_num = pd.to_numeric(tga_series, errors="coerce").dropna()
    print_header("TGA decomposition temperature (C)")
    print(f"Non empty numeric count: {len(tga_num)}")
    print(f"Unique temperatures: {pd.Series(tga_num).nunique()}")
    if len(tga_num) > 0:
        print(f"Min: {tga_num.min():.1f}  Max: {tga_num.max():.1f}  Mean: {tga_num.mean():.1f}")

    # stability
    def stability_block(col):
        s = df[col].astype(str).str.strip().str.lower()
        s = s.replace({"": "(empty)"})
        print_header(f"{col} - distribution")
        print(f"Unique labels including empty: {s.nunique()}")
        print(s.value_counts().to_string())

    stability_block("water_stable")
    stability_block("air_stable")

    # applications
    app_series = df["applications"].astype(str).str.strip()
    app_nonempty = app_series[app_series != ""]
    print_header("Application - ranking")
    print(f"Unique application entries (raw): {app_nonempty.nunique()}")
    value_counts_table(app_nonempty, top=30)
    tags = []
    for v in app_nonempty:
        parts = [p.strip() for p in re.split(r"[;,/]| and ", v) if p.strip()]
        tags.extend(parts)
    if tags:
        print("\nTag-level top 30:")
        print(pd.Series(tags).value_counts().head(30).to_string())

    # ---------------- Metal × Linker coverage and CSV ----------------
    print_header("Metal × Linker coverage gap")

    # marginals
    all_metals_sorted  = metals_series.value_counts().index.tolist()
    all_linkers_sorted = linkers_all.value_counts().index.tolist()

    all_metals = sorted(set(all_metals_sorted))
    all_linkers = sorted(set(all_linkers_sorted))

    # observed pairs and DOI aggregation
    pair_to_dois = {}
    observed_pairs = set()
    for _, row in df.iterrows():
        row_metals = set()
        for mc in ["metal_1","metal_2","metal_3"]:
            sym = first_metal_symbol_from_formula(row.get(mc, ""))
            if sym:
                row_metals.add(sym)
        row_linkers = set()
        for lc in ["linker_1","linker_2","linker_3"]:
            val = str(row.get(lc, "")).strip()
            if is_filled(val):
                row_linkers.add(val)
        if not row_metals or not row_linkers:
            continue
        doi = str(row.get("doi","")).strip()
        for m in row_metals:
            for lk in row_linkers:
                observed_pairs.add((m, lk))
                if is_filled(doi):
                    pair_to_dois.setdefault((m, lk), set()).add(doi)

    # all-pairs universe for gap printout
    all_pairs_universe = {(m, lk) for m in all_metals for lk in all_linkers}
    missing_pairs_universe = sorted(all_pairs_universe - observed_pairs)

    print(f"Unique metals: {len(all_metals)}")
    print(f"Unique linkers: {len(all_linkers)}")
    print(f"Total possible pairs: {len(all_pairs_universe)}")
    print(f"Observed pairs: {len(observed_pairs)}")
    print(f"Missing pairs: {len(missing_pairs_universe)}")
    if missing_pairs_universe:
        miss_df = pd.DataFrame(missing_pairs_universe, columns=["metal", "linker"])
        print("\nFirst 50 missing pairs in full universe:")
        print(miss_df.head(50).to_string(index=False))

    # pair CSV with optional top limits
    metal_pop  = metals_series.value_counts()
    linker_pop = linkers_all.value_counts()

    if top_n_metals is not None:
        metals_sel = all_metals_sorted[:int(top_n_metals)]
    else:
        metals_sel = all_metals_sorted

    if top_n_linkers is not None:
        linkers_sel = all_linkers_sorted[:int(top_n_linkers)]
    else:
        linkers_sel = all_linkers_sorted

    if metals_sel and linkers_sel:
        metal_rank  = {m:i for i,m in enumerate(all_metals_sorted)}
        linker_rank = {l:i for i,l in enumerate(all_linkers_sorted)}

        rows = []
        for m in metals_sel:
            for lk in linkers_sel:
                dois = sorted(pair_to_dois.get((m, lk), []))
                rows.append({
                    "metal": m,
                    "linker": lk,
                    "doi_list": "; ".join(dois) if dois else "",
                    "_metal_pop": int(metal_pop.get(m, 0)),
                    "_linker_pop": int(linker_pop.get(lk, 0)),
                    "_metal_rank": metal_rank.get(m, 10**9),
                    "_linker_rank": linker_rank.get(lk, 10**9),
                    "_observed": (m, lk) in observed_pairs
                })
        pair_df = pd.DataFrame(rows)
        pair_df.sort_values(
            by=["_metal_pop","_linker_pop","metal","linker"],
            ascending=[False, False, True, True],
            inplace=True
        )

        # save
        if top_n_metals is None and top_n_linkers is None:
            out_name = f"{pairs_csv_basename}_all.csv"
        else:
            mtag = str(top_n_metals) if top_n_metals is not None else "allM"
            ltag = str(top_n_linkers) if top_n_linkers is not None else "allL"
            out_name = f"{pairs_csv_basename}_top{mtag}x{ltag}.csv"
        out_path = csv_path.with_name(out_name)
        pair_df.loc[:, ["metal","linker","doi_list"]].to_csv(out_path, index=False, encoding="utf-8-sig")

        total_pairs_grid = len(metals_sel) * len(linkers_sel)
        observed_in_grid = int(pair_df["_observed"].sum())
        with_doi_in_grid = int((pair_df["doi_list"].str.strip() != "").sum())
        missing_in_grid = total_pairs_grid - observed_in_grid

        print_header("Metal × Linker coverage in selected grid")
        print(f"Metals considered: {len(metals_sel)}")
        print(f"Linkers considered: {len(linkers_sel)}")
        print(f"Total pairs: {total_pairs_grid}")
        print(f"Observed pairs (any row, DOI may be missing): {observed_in_grid}")
        print(f"Pairs with at least one DOI listed: {with_doi_in_grid}")
        print(f"Missing pairs: {missing_in_grid}")
        print(f"\nWrote pair report CSV: {out_path}")

        # optional missing list CSV
        missing_pairs_df = pair_df.loc[~pair_df["_observed"], ["metal","linker"]]
        if not missing_pairs_df.empty:
            miss_path = out_path.with_name(out_path.stem + "_missing.csv")
            missing_pairs_df.to_csv(miss_path, index=False, encoding="utf-8-sig")
            print(f"Wrote missing pairs CSV: {miss_path}")
    else:
        print_header("Pair table could not be built: no metals or no linkers detected")

    # ---------------- Precursors used for each metal ----------------
    print_header("Precursors used for each metal")
    precursors_by_metal = {}
    for col in ["metal_1","metal_2","metal_3"]:
        for v in df[col].astype(str):
            sym = first_metal_symbol_from_formula(v)
            if sym:
                precursors_by_metal.setdefault(sym, set()).add(v.strip())

    if precursors_by_metal:
        rows = []
        for sym in sorted(precursors_by_metal.keys(), key=lambda x: (-metal_pop.get(x,0), x)):
            precs = sorted(precursors_by_metal[sym])
            rows.append({"metal": sym, "n_precursors": len(precs), "precursors": "; ".join(precs)})
        prec_df = pd.DataFrame(rows)
        print(prec_df.to_string(index=False))
    else:
        print("No metal precursors found.")
    return csv_path



def run(branch: str, input_path: str | Path | None = None) -> Path:
    configure_utf8_stdio()
    if branch not in FULL_BRANCHES:
        raise ValueError("Step 4.4 is only defined for positive and negative-plans branches; negative-basic stops after Step 4.1.")
    paths = branch_paths(branch)
    dataset = Path(input_path) if input_path else paths["s6"]
    return run_analysis_report(dataset)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 4.4: final summary/report tables and metal-linker pair CSV.")
    parser.add_argument("--branch", choices=sorted(FULL_BRANCHES), default="positive")
    parser.add_argument("--input", dest="input_path", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.branch, args.input_path)


if __name__ == "__main__":
    main()
