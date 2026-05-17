"""Derived feature construction for Step 4 cleansing."""
from __future__ import annotations

from pathlib import Path

def compute_ratio_and_concentration(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Compute M:L ratio and metel_concnertation, then write the _5 CSV."""
    import math
    import re

    import numpy as np
    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_5.csv")
    # Compute M:L ratio and metel_concnertation (mM, integer), then insert before "temperature_c"
    # - M:L ratio uses mmol units only, same logic as before plus a 1:1 text fallback
    # - metel_concnertation = round( (metal_1_amount_value / solvent_main_ml) * 1000 ) as an integer string
    # - Any legacy "metal_1_concentration_M" column is removed
    # - Prints success and failure counts for both calculations

    import re
    import math
    import numpy as np
    import pandas as pd
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found")

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

    df = pd.read_csv(input_path, dtype=str, encoding="utf-8")

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
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

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

    print_header(f"Wrote updated CSV to {output_path.name}")
    return Path(output_path)


def classify_connectivity(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Classify metal_cluster_connectivity in-place or to a supplied output path."""
    import re
    from collections import Counter

    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path
    # Stronger, metal-agnostic connectivity classification (30–50 labels)
    # - Avoids "topology" wording; uses "... connectivity" or "... SBU/cluster SBU"
    # - Merges 2D variants into a single "2D layer connectivity"
    # - Replaces too-generic buckets with more specific, presentation-ready labels
    # - Writes to `metal_cluster_connectivity_classified` next to the original column
    #
    # Input/Output: mof_extraction_1_2_3_4_5.csv (overwrite in place)

    import re
    import pandas as pd
    from collections import Counter

    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found")
    COL = "metal_cluster_connectivity"
    NEW = "metal_cluster_connectivity_classified"
    df = pd.read_csv(input_path, dtype=str, encoding="utf-8-sig")
    if COL not in df.columns:
        raise KeyError(f"Column '{COL}' not found")

    def print_header(msg):
        print("\n" + "=" * 80)
        print(msg)
        print("=" * 80)

    def is_filled(x: str) -> bool:
        return isinstance(x, str) and x.strip() != "" and x.strip().lower() not in {"nan", "none"}

    def norm(s: str) -> str:
        s = re.sub(r"\s+", " ", str(s)).strip()
        s = s.replace("–", "-").replace("—", "-").replace("·", ".")
        return s

    # ---------- label builders (metal-agnostic, description-friendly) ----------
    def L_cluster(size=None, shape=None):
        parts = []
        if size: parts.append(size)
        if shape: parts.append(shape)
        parts.append("cluster SBU")
        return " ".join(parts)

    def L_dimer_paddle(): return "paddlewheel dimer SBU"
    def L_rod(kind):      return f"1D rod SBU ({kind})"
    def L_layer(kind=None): return "2D layer connectivity" if not kind else f"2D layer connectivity ({kind})"
    def L_pillared():       return "pillared layer connectivity"
    def L_3D_named(name):   return f"3D named-net connectivity ({name})"     # avoids topology codes while retaining detail
    def L_3D_xconn():       return "3D x-connected connectivity"
    def L_cyanide():        return "Hofmann-type cyanide connectivity"
    def L_pom(kind):        return f"{kind} POM cluster SBU"
    def L_framework():      return "3D multinodal connectivity"

    # ---------- pattern helpers ----------
    ANY = re.I
    def like(s, pat): return re.search(pat, s, flags=ANY) is not None

    # connectivity tuple or N-connected
    TUPLE_CONN = re.compile(r"\(\s*\d+(?:\s*,\s*\d+)+\s*\)")
    N_CONN      = re.compile(r"\b(\d+)\s*-\s*connected\b|\b(\d+)\s*connected\b", re.I)

    # nuclearity tokens map
    NUC_MAP = {
        3: "trinuclear", 4: "tetranuclear", 5: "pentanuclear", 6: "hexanuclear",
        7: "heptanuclear", 8: "octanuclear", 9: "nonanuclear", 10: "decanuclear",
        11: "undecanuclear", 12: "dodecanuclear", 14: "tetradecanuclear", 18: "octadecanuclear"
    }

    def infer_nuclearity(s: str):
        # explicit words
        for n, word in NUC_MAP.items():
            if like(s, rf"\b{word}\b"): return word
        # patterns like Zn5, Zr6, RE9, Ln6, etc. but return metal-agnostic word
        for n, word in NUC_MAP.items():
            if like(s, rf"\b[A-Z][a-z]?\s*{n}\b") or like(s, rf"\b(?:RE|Ln)\s*{n}\b") or like(s, rf"\b{n}\s*-\s*connected\b") or like(s, rf"\b{n}\s*connected\b"):
                return word
        # Zn4O → tetranuclear-like
        if like(s, r"\b[A-Z][a-z]?4O\b"):
            return "tetranuclear"
        return None

    def is_mu3_oxo_trimer(s): return like(s, r"\bμ?3[- ]?O[H]?\b") or "μ3-oxo" in s.lower() or like(s, r"M3\(μ3-O")
    def is_cubane(s):         return like(s, r"\bcubane\b|D4R\b")
    def is_cage(s):           return like(s, r"\bcage\b|nanocage|mop\b|polyhedron|metallamacrocycle")
    def is_pinwheel(s):       return "pinwheel" in s.lower() or "hourglass" in s.lower() or "wheel" in s.lower()

    def classify(text: str) -> str:
        if not is_filled(text): return ""
        t = norm(text)

        # -------- POM families (0D clusters) --------
        if like(t, r"\bKeggin\b|PMo12|BW12|SiW12|PW12"): return L_pom("Keggin")
        if like(t, r"\bDawson\b|P2W18"):                return L_pom("Dawson")
        if like(t, r"\bMo8O?26\b|(?:^|[^A-Za-z])Mo8([^A-Za-z]|$)|β-?Mo8|α-?Mo8|R-?Mo8"): return L_pom("Mo8")
        if like(t, r"\[(?:Mo|W)\(CN\)8\]"):             return "POM cyanometal connectivity"

        # -------- Paddlewheel dimers (0D) --------
        if like(t, r"paddle[- ]?wheel|\[M2\(COO\)4\]") or (like(t, r"\b(Cu|Zn|Co|Ni|Cd)2\b") and "paddle" in t.lower()):
            return L_dimer_paddle()

        # -------- μ3-oxo trimer (0D) --------
        if is_mu3_oxo_trimer(t): return L_cluster("trinuclear", "μ3-oxo trimer")

        # -------- shape-specific clusters (0D) --------
        if is_cubane(t):   return L_cluster("tetranuclear", "cubane")
        if is_cage(t):     return L_cluster(None, "cage")
        if is_pinwheel(t): return L_cluster(None, "pinwheel")

        # -------- nuclearity-driven clusters (0D, metal-agnostic) --------
        nuc = infer_nuclearity(t)
        if nuc: return L_cluster(nuc)

        # Catch Zn4O-like without naming metal -> μ4-oxo tetrahedral cluster SBU
        if like(t, r"\b[A-Z][a-z]?4O\b"): return L_cluster("tetranuclear", "μ4-oxo tetrahedral")

        # Generic "cluster"/"SBU" mentions (0D) with weak descriptors → "polynuclear cluster SBU"
        if like(t, r"\bcluster\b|\bSBU\b"):
            # try to salvage hints: "tetrahedral", "octahedral" > still keep as cluster SBU
            return L_cluster("polynuclear")

        # -------- 1D rods (chains) --------
        if like(t, r"\brod SBU\b|\b1D\b.*chain|\binfinite .*chain|\bzig-?zag chain|\bhelical chain"):
            if like(t, r"(metal|M)[- ]?O[- ]?M|oxo|μ[- ]?OH|μ[- ]?O\b"): return L_rod("metal-oxo chain")
            if like(t, r"face[- ]?sharing|LnO9|anticube|dodecahedron"):  return L_rod("lanthanide face-sharing")
            return L_rod("coordination chain")

        # -------- 2D layers (merge all variants) --------
        if like(t, r"\b2D\b.*(layer|sheet|grid|honeycomb)|\b\(4,4\)\b|\bsql\b|\bhcb\b|\bkagome|\bkgd\b|CdCl2-?type|CdSO4-?type"):
            return L_layer()  # single label for all 2D layers

        # -------- Pillared layers --------
        if like(t, r"\bpillar[- ]?layer|\bpillared\b"): return L_pillared()

        # -------- Named 3D nets → “3D named-net connectivity (name)” (avoids topology word) --------
        if like(t, r"\bdia\b|diamond"):                   return L_3D_named("dia")
        if like(t, r"\bpcu\b|primitive cubic|a-?Po"):     return L_3D_named("pcu")
        if like(t, r"\bpts\b"):                           return L_3D_named("pts")
        if like(t, r"\brht\b|\bscu\b|\bsrs\b|\bkgm\b"):   return L_3D_named("rht/scu/srs/kgm")
        if like(t, r"zeolit(ic|e)|\bSOD\b|AFI|D4R|D6R"):  return L_3D_named("zeolitic")

        # -------- Cyanide families (Hofmann etc.) --------
        if like(t, r"\[Ni\(CN\)4\]|\[Pt\(CN\)4\]|\[Pd\(CN\)4\]|\bcyanide\b|Cu\(CN\)"): return L_cyanide()

        # -------- Explicit x-connected tuple/count in text → x-connected 3D --------
        if TUPLE_CONN.search(t) or N_CONN.search(t): return L_3D_xconn()

        # -------- Framework / network cues (final fallback for 3D) --------
        if like(t, r"\b3D\b.*(framework|network)|\bframework\b|\bnetwork\b"): return L_framework()

        # Last mild fallback: if it mentions layer/chain rod again
        if "layer" in t.lower() or "sheet" in t.lower(): return L_layer()
        if "chain" in t.lower() or "rod" in t.lower():  return L_rod("coordination chain")
        return L_framework()

    series = df[COL].astype(str).fillna("")
    classified = series.apply(classify)

    # Post-process: collapse a few very rare verbose shapes into core buckets to keep 30–50 labels
    REMAP = {
        "3D named-net connectivity (rht/scu/srs/kgm)": "3D named-net connectivity (other)",
        "3D named-net connectivity (zeolitic)":        "3D named-net connectivity (other)",
    }
    classified = classified.replace(REMAP)

    # Insert NEW column next to original
    if NEW in df.columns:
        df.drop(columns=[NEW], inplace=True)
    insert_at = list(df.columns).index(COL) + 1
    df.insert(insert_at, NEW, classified)

    # Report palette size and top labels
    print_header("Palette size and top labels")
    cnt = Counter([x for x in classified if is_filled(x)])
    print(f"Number of unique labels: {len(cnt)}")
    for k, v in cnt.most_common(40):
        print(f"{k:<40s} {v}")

    # Save
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print_header(f"Wrote updated file with '{NEW}' to {output_path.name}")
    return Path(output_path)


def build_mof_description(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Build the mof_description column and write the _6 CSV."""
    import re

    import numpy as np
    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_6.csv")
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

    # ---------------- metal dictionaries ----------------
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
        # adjective forms
        "ferrous":"Fe","ferric":"Fe","cuprous":"Cu","cupric":"Cu","stannous":"Sn","stannic":"Sn",
        "plumbous":"Pb","plumbic":"Pb","chromous":"Cr","chromic":"Cr","manganous":"Mn","manganic":"Mn",
        "cerous":"Ce","ceric":"Ce","cobaltous":"Co",
        # textual variants sometimes present
        "zinc(ii)":"Zn","nickel(ii)":"Ni","copper(ii)":"Cu","chromium(iii)":"Cr",
        "ytterbium(iii)":"Yb","zinc(ii) nitrate":"Zn",
    }

    # symbol -> plain English
    METAL_SYM_TO_NAME = {}
    for k, v in METAL_NAME_TO_SYM.items():
        if k in {"aluminium"}:
            continue
        METAL_SYM_TO_NAME.setdefault(v, k)
    # preferred spellings
    METAL_SYM_TO_NAME.update({
        "Al": "aluminum", "Si": "silicon", "Fe": "iron", "Cu": "copper", "Ce": "cerium",
        "Zr": "zirconium", "Zn": "zinc", "Ni": "nickel", "Co": "cobalt", "Cd": "cadmium",
        "Tb": "terbium", "Eu": "europium", "La": "lanthanum", "Nd": "neodymium", "Gd": "gadolinium",
    })

    METAL_SYMBOLS = set(METAL_SYM_TO_NAME.keys())
    NON_METAL_LIKELY = {"H","C","N","O","F","Cl","Br","I","Si","P","S","B"}  # skim common non-metals first
    EL_TOKEN = re.compile(r"[A-Z][a-z]?")

    def first_metal_symbol_from_formula(s: str):
        if not is_filled(s):
            return None
        text = str(s).replace("·", "")
        tokens = EL_TOKEN.findall(text)
        for t in tokens:
            if t in METAL_SYMBOLS and t not in NON_METAL_LIKELY:
                return t
        for t in tokens:
            if t in {"B","Si"} and t in METAL_SYMBOLS:
                return t
        low = text.lower()
        for name in sorted(METAL_NAME_TO_SYM.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", low):
                return METAL_NAME_TO_SYM[name]
        return None

    def metal_name_from_symbol(sym: str):
        return METAL_SYM_TO_NAME.get(sym)

    def choose_article(name: str) -> str:
        """Return 'a' or 'an' for the given metal name."""
        if not is_filled(name):
            return "a"
        n = name.strip().lower()
        # vowel starts, common English usage
        if n.startswith(("a","e","i","o")):
            # exceptions where the vowel is pronounced "yoo"
            if n.startswith(("eu",)):
                return "a"
            return "an"
        # u-initial metals pronounced "yoo"
        if n.startswith("u"):
            return "a"  # uranium
        # y-initial rare earths often vowel sound
        if n in {"yttrium","ytterbium"}:
            return "an"
        return "a"

    def linker_phrase(l1, l2, l3):
        names = [x.strip() for x in [l1, l2, l3] if is_filled(x)]
        if not names:
            return None
        if len(names) == 1:
            return f"built by organic linker {names[0]}"
        if len(names) == 2:
            return f"built by organic linkers {names[0]} and {names[1]}"
        return f"built by organic linkers {names[0]}, {names[1]} and {names[2]}"

    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found")
    df = pd.read_csv(input_path, dtype=str, encoding="utf-8")

    for c in ["metal_1", "linker_1", "linker_2", "linker_3", "metal_cluster_connectivity_classified", "topology_code"]:
        if c not in df.columns:
            df[c] = ""

    desc_before_nonempty = int(df["mof_description"].apply(is_filled).sum()) if "mof_description" in df.columns else 0
    descriptions = [""] * len(df)

    cnt_both = 0
    cnt_cluster_only = 0
    cnt_topology_only = 0
    cnt_basic = 0
    cnt_skipped = 0

    for idx, row in df.iterrows():
        m1 = row.get("metal_1", "")
        l1 = row.get("linker_1", "")
        l2 = row.get("linker_2", "")
        l3 = row.get("linker_3", "")

        sym = first_metal_symbol_from_formula(m1)
        if not sym:
            cnt_skipped += 1
            continue
        metal_name = metal_name_from_symbol(sym)
        if not metal_name or not is_filled(l1):
            cnt_skipped += 1
            continue

        article = choose_article(metal_name)

        topo = str(row.get("topology_code", "") or "").strip()
        topo_ok = is_filled(topo)
        topo_str = f"{topo.lower()} topology" if topo_ok else ""

        cluster = str(row.get("metal_cluster_connectivity_classified", "") or "").strip()
        cluster_ok = is_filled(cluster)

        lphrase = linker_phrase(l1, l2, l3)
        if not lphrase:
            cnt_skipped += 1
            continue

        if cluster_ok and topo_ok:
            desc = f"{article} {metal_name} metal-organic framework with {cluster} and {topo_str} {lphrase}"
            cnt_both += 1
        elif cluster_ok:
            desc = f"{article} {metal_name} metal-organic framework with {cluster} {lphrase}"
            cnt_cluster_only += 1
        elif topo_ok:
            desc = f"{article} {metal_name} metal-organic framework with {topo_str} {lphrase}"
            cnt_topology_only += 1
        else:
            desc = f"{article} {metal_name} metal-organic framework {lphrase}"
            cnt_basic += 1

        descriptions[idx] = desc.strip()

    # Remove existing column to avoid duplicates, then insert before 'mof_name'
    if "mof_description" in df.columns:
        df = df.drop(columns=["mof_description"])

    insert_at = df.columns.get_loc("mof_name") if "mof_name" in df.columns else 0
    df.insert(insert_at, "mof_description", descriptions)

    after_nonempty = int(pd.Series(descriptions).apply(is_filled).sum())

    print_header("MOF description summary")
    print(f"Created with both cluster and topology: {cnt_both}")
    print(f"Created with cluster only: {cnt_cluster_only}")
    print(f"Created with topology only: {cnt_topology_only}")
    print(f"Created basic description: {cnt_basic}")
    print(f"Skipped due to missing metal or linker_1: {cnt_skipped}")
    print(f"Non-empty descriptions before: {desc_before_nonempty}")
    print(f"Non-empty descriptions after:  {after_nonempty}")

    df = df.fillna("")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print_header(f"Wrote updated CSV to {output_path.name}")
    return Path(output_path)

