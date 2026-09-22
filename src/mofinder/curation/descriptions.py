"""MOF descriptions from curated precursor and structure fields."""

def clean_positive(input_path, output_path):
    """Build MOF descriptions and write the resulting CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    # - Sensitive to "a"/"an" based on the metal name's initial sound
    # - Uses metal_1 to infer the primary metal (robust to salts/complexes)
    # - Combines with metal_cluster_connectivity and topology_code when present
    # - Skips rows without a detectable metal or without linker_1
    # - Inserts 'mof_description' before 'mof_name' (or at column 0 if 'mof_name' is missing)
    # - Prints per-case counts and total non-empty descriptions

    import re
    import pandas as pd
    import numpy as np
    from pathlib import Path




    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH.name} not found")

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

        text = str(s).replace("·", "").strip()
        low = text.lower()

        # Check full metal names before parsing formula tokens.
        # This prevents "Copper" from being interpreted as "Co" = cobalt.
        for name in sorted(METAL_NAME_TO_SYM.keys(), key=len, reverse=True):
            if re.search(
                rf"(?<![a-z]){re.escape(name)}(?![a-z])",
                low
            ):
                return METAL_NAME_TO_SYM[name]

        # Only if no textual metal name is found, parse as a formula.
        # Example: Cu(NO3)2·3H2O -> Cu
        tokens = EL_TOKEN.findall(text)

        for t in tokens:
            if t in METAL_SYMBOLS and t not in NON_METAL_LIKELY:
                return t

        for t in tokens:
            if t in {"B", "Si"} and t in METAL_SYMBOLS:
                return t

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

    df = pd.read_csv(IN_PATH, dtype=str, encoding="utf-8")

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
        m1_abbr = row.get("metal_1_abbr", "")

        l1 = row.get("linker_1", "")
        l2 = row.get("linker_2", "")
        l3 = row.get("linker_3", "")

        # Infer the metal from the precursor name, with an abbreviation fallback.
        sym_from_name = first_metal_symbol_from_formula(m1)
        # Only inspect metal_1_abbr if metal_1 cannot be parsed.
        if sym_from_name:
            sym_from_abbr = None
            sym = sym_from_name
        else:
            sym_from_abbr = (
                first_metal_symbol_from_formula(m1_abbr)
                if is_filled(m1_abbr)
                else None
            )
            sym = sym_from_abbr



        # Prefer metal_1; use metal_1_abbr only when metal_1 could not be parsed.
        sym = sym_from_name or sym_from_abbr

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
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print_header(f"Wrote updated CSV to {OUT_PATH.name}")
    return df


def clean_negative(input_path, output_path):
    """Build MOF descriptions and write the resulting CSV."""
    from pathlib import Path
    input_path, output_path = Path(input_path), Path(output_path)
    in_path = IN = IN_PATH = INOUT = input_path
    out_path = OUT = OUT_PATH = output_path
    # - Sensitive to "a"/"an" based on the metal name's initial sound
    # - Uses metal_1 to infer the primary metal (robust to salts/complexes)
    # - Combines with metal_cluster_connectivity and topology_code when present
    # - Skips rows without a detectable metal or without linker_1
    # - Inserts 'mof_description' before 'mof_name' (or at column 0 if 'mof_name' is missing)
    # - Prints per-case counts and total non-empty descriptions

    import re
    import pandas as pd
    import numpy as np
    from pathlib import Path




    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH.name} not found")

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

    df = pd.read_csv(IN_PATH, dtype=str, encoding="utf-8")

    for c in ["metal_1", "linker_1", "linker_2", "linker_3", "metal_cluster_connectivity", "topology_code"]:
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

        cluster = str(row.get("metal_cluster_connectivity", "") or "").strip()
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
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print_header(f"Wrote updated CSV to {OUT_PATH.name}")
    return df
