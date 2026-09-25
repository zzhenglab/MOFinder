"""Connectivity rules for synthesis-record curation."""

def clean(input_path, output_path):
    """Apply the connectivity stage and write the resulting CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    # - Avoids "topology" wording; uses "... connectivity" or "... SBU/cluster SBU"
    # - Merges 2D variants into a single "2D layer connectivity"
    # - Uses specific labels for cluster shape and connectivity
    # - Writes to `metal_cluster_connectivity_classified` next to the original column
    #
    # Augment the fifth intermediate CSV in place.

    import re
    import pandas as pd
    from pathlib import Path
    from collections import Counter


    COL = "metal_cluster_connectivity"
    NEW = "metal_cluster_connectivity_classified"

    if not INOUT.exists():
        raise FileNotFoundError(f"{INOUT.name} not found")

    df = pd.read_csv(INOUT, dtype=str, encoding="utf-8-sig")
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
    def L_3D_named(name):   return f"3D named-net connectivity ({name})"     # avoids topology codes but preserves info
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
            # Retain tetrahedral or octahedral descriptors within the cluster SBU label.
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

        # Classify remaining layer, chain, or rod descriptions.
        if "layer" in t.lower() or "sheet" in t.lower(): return L_layer()
        if "chain" in t.lower() or "rod" in t.lower():  return L_rod("coordination chain")
        return L_framework()

    series = df[COL].astype(str).fillna("")
    classified = series.apply(classify)

    # Merge rare shape descriptions, targeting approximately 30-50 connectivity labels.
    REMAP = {
        "3D named-net connectivity (rht/scu/srs/kgm)": "3D named-net connectivity (other)",
        "3D named-net connectivity (zeolitic)":        "3D named-net connectivity (other)",
    }
    classified = classified.replace(REMAP)

    # Insert the classified column next to the original connectivity text.
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
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print_header(f"Wrote updated file with '{NEW}' to {INOUT.name}")
    return df
