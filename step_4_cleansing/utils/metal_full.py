"""Full metal normalization and amount cleanup for Step 4 cleansing."""
from __future__ import annotations

from pathlib import Path

def normalize_metals_full(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Run full metal normalization and amount conversion."""
    import re
    from fractions import Fraction
    from math import gcd

    import numpy as np
    import pandas as pd

    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_2.csv")
    def is_filled(x):
        if x is None: return False
        if isinstance(x, float) and np.isnan(x): return False
        return str(x).strip() != "" and str(x).strip().lower() not in {"nan","none"}

    def fmt_frac(n: float) -> str:
        if float(n).is_integer(): return str(int(n))
        f = Fraction(n).limit_denominator(12)
        return f"{f.numerator}/{f.denominator}"

    COMPLIANT = re.compile(r"^[\[\(]?[A-Z][a-z]?(?:[A-Za-z0-9\[\]\(\)]+)?(?:·(?:\d+(?:\.\d+)?(?:/\d+)?|x)H2O)?$", re.I)

    FRAMEWORK_PAT = re.compile(r"\b(MOF|ZIF|UiO|HKUST|MIL|PCN|NU|IRMOF|NOTT|DUT|MOP)\b", re.I)
    CLUSTER_PAT   = re.compile(r"\b(cluster|oxocluster|node|Zr6)\b", re.I)
    TEMPLATE_PAT  = re.compile(r"\b(HDS|template|MXene)\b", re.I)
    BTC_PAT       = re.compile(r"-\s*BTC\b", re.I)
    ZNEG_PAT      = re.compile(r"\b(?:Zn|zinc)\s*[-/]\s*EG\b|\bzinc[- ]ethylene glycol\b", re.I)
    SALT_PAT      = re.compile(r"\bsalt\b", re.I)
    ACID_PAT      = re.compile(r"\bacid\b", re.I)

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
        "cerous":"Ce","ceric":"Ce","cobaltous":"Co"
    }
    ADJ_OX = {"ferrous":2,"ferric":3,"cuprous":1,"cupric":2,"stannous":2,"stannic":4,"plumbous":2,"plumbic":4,
              "chromous":2,"chromic":3,"manganous":2,"manganic":3,"cerous":3,"ceric":4,"cobaltous":2}
    COMMON_OX = {"Ag":1,"Cu":2,"Au":3,"Zn":2,"Cd":2,"Hg":2,"Al":3,"Ga":3,"In":3,"Tl":3,
                 "Sc":3,"Y":3,"La":3,"Ce":3,"Pr":3,"Nd":3,"Sm":3,"Eu":3,"Gd":3,"Tb":3,"Dy":3,"Ho":3,"Er":3,"Tm":3,"Yb":3,"Lu":3,
                 "Ti":4,"Zr":4,"Hf":4,"V":3,"Nb":5,"Ta":5,"Cr":3,"Mo":6,"W":6,"Mn":2,"Fe":3,"Co":2,"Ni":2,
                 "Pb":2,"Sn":4,"Bi":3,"U":6,"Th":4,"Mg":2,"Ca":2,"Sr":2,"Ba":2,"Na":1,"K":1,"Li":1}
    ROMAN = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,"X":10}
    ANION = {
        "chloride":("Cl",-1),"bromide":("Br",-1),"iodide":("I",-1),"fluoride":("F",-1),
        "nitrate":("NO3",-1),"perchlorate":("ClO4",-1),"chlorate":("ClO3",-1),
        "acetate":("CH3COO",-1),"trifluoroacetate":("CF3COO",-1),"formate":("HCOO",-1),"benzoate":("PhCOO",-1),
        "triflate":("OTf",-1),"trifluoromethanesulfonate":("OTf",-1),"tosylate":("OTs",-1),"p-toluenesulfonate":("OTs",-1),
        "tetrafluoroborate":("BF4",-1),"hexafluorophosphate":("PF6",-1),
        "hexafluoroantimonate":("SbF6",-1),"hexafluoroarsenate":("AsF6",-1),
        "thiocyanate":("SCN",-1),"cyanide":("CN",-1),
        "hydroxide":("OH",-1),
        "carbonate":("CO3",-2),"sulfate":("SO4",-2),"sulphate":("SO4",-2),"oxalate":("C2O4",-2),
        "oxide":("O",-2)
    }
    MONO_ANIONS = {"Cl","Br","I","F","O","H","N","C","S"}

    HYDRATE_WORD = {
        "monohydrate":1,"dihydrate":2,"trihydrate":3,"tetrahydrate":4,"pentahydrate":5,
        "hexahydrate":6,"heptahydrate":7,"octahydrate":8,"nonahydrate":9,"decahydrate":10,
        "sesquihydrate":1.5,"hemihydrate":0.5,"hydrate":"x","hemi(pentahydrate)":2.5
    }
    PREFIX_TO_NUM = {"mono":1,"di":2,"tri":3,"tetra":4,"penta":5,"hexa":6,"hepta":7,"octa":8,"nona":9,"deca":10}

    def clean_unicode(s): 
        if not is_filled(s): return s
        t = str(s).replace("μ","u").replace("µ","u").replace("–","-").replace("—","-").replace("· ", "·")
        t = t.replace("{","(").replace("}",")")
        t = re.sub(r"\bc+admium\b","cadmium", t, flags=re.I)
        return t

    def replace_tokens(t):
        if not is_filled(t): return t
        s = str(t)
        s = re.sub(r"\bCH3CO2\b", "CH3COO", s, flags=re.I)
        s = re.sub(r"\(OAc\)", "(CH3COO)", s, flags=re.I)
        s = re.sub(r"\(OAC\)", "(CH3COO)", s, flags=re.I)
        s = re.sub(r"\(Ac\)",  "(CH3COO)", s, flags=re.I)
        s = re.sub(r"\(NO33", "(NO3)3", s, flags=re.I)
        s = s.replace("$","·")
        s = re.sub(r"\bOH2\b","H2O", s); s = re.sub(r"\(OH2\)","(OH)2", s)
        s = re.sub(r"\bTi\(i\-?OPr\)4\b", "Ti(OiPr)4", s, flags=re.I)
        s = re.sub(r"\btitanium\s+isopropoxyde\b", "Ti(OiPr)4", s, flags=re.I)
        s = re.sub(r"\btitanium\s+isopropylate\b", "Ti(OiPr)4", s, flags=re.I)
        s = re.sub(r"\btitanium\s+(tetra\-)?isopropoxide\b", "Ti(OiPr)4", s, flags=re.I)
        return s

    def unify_parentheses(s):
        if not is_filled(s): return s
        t = str(s)
        t = re.sub(r"\.(\d+)\s*\(H2O\)", r"·\1H2O", t)
        t = re.sub(r"·\s*(\d+(?:\.\d+)?)\s*\(H2O\)", r"·\1H2O", t)
        t = re.sub(r"·\s*\(H2O\)", "·1H2O", t)
        t = re.sub(r"\bdihydrate\s+and\s+a\s+half\b", "·2.5H2O", t, flags=re.I)
        t = re.sub(r"-half\s*·\s*H2O", "·0.5H2O", t, flags=re.I)
        t = re.sub(r"[- ]·\s*H2O", "·1H2O", t, flags=re.I)
        t = re.sub(r"[\)\]]+$","", t)
        return t

    QUAL_TAIL = re.compile(r"[,\s;]+(anhydrous|anhydrodous|solution|aq\.?|aqueous|powder|wire|foil|granules?|beads?|shot|pellets?|suspension|wastewater|leachate|precursor.*|seed[s]?|template.*|stock.*|ethanolic|nanosized|crystals?|nanowires?|nanosheets?)$", re.I)
    def strip_qualifiers(s):
        if not is_filled(s): return s
        out = str(s).strip()
        while True:
            new = re.sub(QUAL_TAIL, "", out).strip()
            if new == out: break
            out = new
        out = re.sub(r"\b\d+(\.\d+)?\s*%$","", out).strip()
        out = re.sub(r"\bin\s*\d+(\.\d+)?\s*M\s*[A-Za-z0-9\(\)]+","", out).strip()
        return out

    def cut_descriptor_tails(s):
        if not is_filled(s): return s
        t = str(s)
        t = re.sub(r"\b(heterometallic ring|polymer|intermediate|source|magnet|tubular monolith)\b.*$","",t,flags=re.I)
        t = re.sub(r"^\s*\d+[a-z]?\s*$","",t,flags=re.I)
        return t.strip()

    def normalize_dots_and_h2o(s):
        if not is_filled(s): return s
        out = str(s)
        out = re.sub(r"\s*[·∙•⋅xX\.]\s*([0-9]+(?:\.\d+)?(?:/\d+)?|n|x)\s*H\s*2\s*O", lambda m: "·" + m.group(1).lower().replace("n","x") + "H2O", out, flags=re.I)
        out = re.sub(r"([A-Za-z0-9\)\]])\s+((?:\d+(?:\.\d+)?(?:/\d+)?|x)\s*H\s*2\s*O\b)", lambda m: m.group(1) + "·" + re.sub(r"\s*","", m.group(2)), out, flags=re.I)
        out = re.sub(r"·\s*\(H2O\)","·1H2O", out)
        out = re.sub(r"·\s*H2O\b","·1H2O", out)
        out = re.sub(r"H\s*2\s*O","H2O", out, flags=re.I)
        out = re.sub(r"·{2,}","·", out)
        return out.strip()

    def consolidate_hydrates(s):
        if not is_filled(s): return s
        t = str(s)
        dots = re.findall(r"·([0-9]+(?:\.\d+)?(?:/\d+)?|x)H2O", t, re.I)
        pars = re.findall(r"\(H2O\)\s*([0-9]+(?:\.\d+)?)+", t, re.I)
        total, unknown = 0.0, False
        for d in dots:
            d = d.lower()
            if d == "x": unknown = True
            elif "/" in d:
                try:
                    a,b = d.split("/",1); total += float(a)/float(b)
                except: unknown = True
            else:
                total += float(d)
        for p in pars: total += float(p)
        t = re.sub(r"·([0-9]+(?:\.\d+)?(?:/\d+)?|x)H2O","",t,flags=re.I)
        t = re.sub(r"\(H2O\)\s*([0-9]+(?:\.\d+)?)+","",t,flags=re.I)
        t = re.sub(r"\s+"," ",t).strip()
        if unknown and total==0: return t+"·xH2O"
        if unknown and total>0:  return t+"·xH2O"
        return t + (f"·{fmt_frac(float(total))}H2O" if total>0 else "")

    def strip_nonwater_adducts(s):
        if not is_filled(s): return s
        out = str(s)
        while True:
            new = re.sub(r"·\s*(\d+(?:\.\d+)?)?\s*(?!H2O\b)[A-Za-z][A-Za-z0-9\(\)]+","",out)
            if new == out: break
            out = new
        return out.strip()

    def simplify_polyoxo_acids(s):
        if not is_filled(s): return s
        t = str(s)
        m = re.search(r"\[([^\]]+)\]", t)
        if m:
            inside = m.group(1)
            m2 = re.search(r"(Mo|W|V|Re)\d+O\d+", inside)
            if m2: t = inside[m2.start():] + t[m.end():]
        m3 = re.search(r"(Mo|W|V|Re)\d+O\d+", t)
        if m3: t = t[m3.start():]
        return t.strip()

    def strip_leading_cations_for_complex(s):
        if not is_filled(s): return s
        t = re.sub(r"^\s*\((?:Me\d*N|Et4N|NBu4|Bu3NH|TBA)\)\d*\s*(?=[\[\(])","", str(s), flags=re.I)
        m = re.search(r"\[[^\]]+\]", t)
        if m:
            head = t[:m.start()].strip()
            if re.fullmatch(r"(?:(?:\(?NH4\)?|K|Na|Li|Rb|Cs)\d*\s*)+", head, flags=re.I):
                t = t[m.start():] + t[m.end():]
        return t

    def drop_counterions_after_complex(s):
        if not is_filled(s): return s
        t = str(s)
        t = re.sub(r"^\[([^\]]+)\]\s*(PF6|BF4|BPh4|ClO4|NO3|Cl)(?:\s*·[A-Za-z0-9\(\)]+)*$", r"\1", t, flags=re.I)
        t = re.sub(r"^(.*\))\s*(PF6|BF4|BPh4|ClO4|NO3|Cl)(?:\s*·[A-Za-z0-9\(\)]+)*$", r"\1", t, flags=re.I)
        return t

    def final_trim(s):
        if not is_filled(s): return s
        t = re.sub(r"\s+"," ", str(s)).strip()
        t = re.sub(r"[,\.;:]+$","", t)
        return t

    TEXT_SALT_PAT = re.compile(
        r"^\s*(?P<metal>[A-Za-z]+)\s*(?:\(\s*(?P<roman>[ivxIVX]+)\s*\))?\s+(?P<anion>[A-Za-z\- ]+?)(?:\s|$)", re.I
    )

    def parse_hydrate_words(rest: str):
        if not is_filled(rest): return None
        r = rest.lower()
        m = re.search(r"hemi\((mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca)hydrate\)", r)
        if m: return 0.5 * {"mono":1,"di":2,"tri":3,"tetra":4,"penta":5,"hexa":6,"hepta":7,"octa":8,"nona":9,"deca":10}[m.group(1)]
        m2 = re.search(r"\b(\d+(?:\.\d+)?)\s*-\s*hydrate\b", r)
        if m2: return float(m2.group(1))
        for w,n in HYDRATE_WORD.items():
            if re.search(rf"\b{re.escape(w)}\b", r): return n
        if re.search(r"·\s*H2O", rest): return 1
        return None

    def build_stoich(m_sym, ox, anion_formula, anion_charge):
        c = abs(anion_charge)
        g = gcd(int(ox), c)
        a = c // g
        b = int(ox) // g
        if anion_formula in MONO_ANIONS:
            return f"{m_sym}{a if a>1 else ''}{anion_formula}{b if b>1 else ''}"
        return f"{m_sym}{a if a>1 else ''}({anion_formula}){b if b>1 else ''}"

    def snap_special_cores(s):
        x = s
        x = re.sub(r"\bzirconyl\s+nitrate\b", "ZrO(NO3)2", x, flags=re.I)
        x = re.sub(r"\bzirconyl\s+chloride\b", "ZrOCl2", x, flags=re.I)
        x = re.sub(r"\buranyl\s+nitrate\b",   "UO2(NO3)2", x, flags=re.I)
        return x

    def text_salt_to_formula(name: str):
        if not is_filled(name): return None
        s0 = snap_special_cores(str(name).strip())
        m = TEXT_SALT_PAT.match(s0)
        if not m: return None
        metal_word = m.group("metal"); roman = m.group("roman"); anion_words = m.group("anion")
        m_sym = METAL_NAME_TO_SYM.get(metal_word.lower())
        if not m_sym:
            if metal_word.lower() in ADJ_OX: m_sym = METAL_NAME_TO_SYM.get(metal_word.lower(), None) or metal_word.title()
            else: return None
        if roman:
            ox = ROMAN.get(roman.upper()); 
            if ox is None: return None
        elif metal_word.lower() in ADJ_OX:
            ox = ADJ_OX[metal_word.lower()]
        else:
            ox = COMMON_OX.get(m_sym); 
            if ox is None: return None

        akey = anion_words.lower().strip().replace("-", " ")
        akey = re.sub(r"\s+(hydrate|salt|solution).*$","", akey).strip()
        if akey.endswith(" acid"):
            acid = akey[:-5].strip()
            akey = {"acetic":"acetate","formic":"formate","benzoic":"benzoate"}.get(acid, akey)

        found = None
        for k,(form,chg) in ANION.items():
            if re.search(rf"\b{k}\b", akey): found = k; break
        if not found: return None

        an_form, an_charge = ANION[found]
        core = build_stoich(m_sym, ox, an_form, an_charge)

        n_h2o = parse_hydrate_words(s0)
        if n_h2o is None:
            m2 = re.search(r"·\s*([0-9]+(?:\.\d+)?(?:/\d+)?|x)\s*H2O", s0, re.I)
            if m2: return f"{core}·{m2.group(1)}H2O"
            if re.search(r"·\s*H2O", s0): return core + "·1H2O"
            return core
        if n_h2o == "x": return core + "·xH2O"
        return core + f"·{fmt_frac(float(n_h2o))}H2O"

    FORMULA_TOKEN = re.compile(r"[A-Z][A-Za-z]?(?:[A-Za-z0-9\[\]\(\)]+)(?:·(?:\d+(?:\.\d+)?(?:/\d+)?|x)H2O)?")
    def pick_first_formula(s):
        toks = FORMULA_TOKEN.findall(s)
        toks = [t for t in toks if not re.fullmatch(r"\(*[IVXivx]+\)*", t)]
        return toks[0] if toks else None

    # manual maps you listed (ensure not non-compliant)
    TEXT_SNAPS = {
        "zirconium acetylacetonate":"Zr(acac)4",
        "zirconium dichloride oxide octahydrate":"ZrOCl2·8H2O",
        "zirconium oxychloride octahydrate":"ZrOCl2·8H2O",
        "zirconium tetrachloride (anhydrous":"ZrCl4",
        "zirconium tetrachloride":"ZrCl4",
        "zirconyl chloride":"ZrOCl2",
        # NEW synonyms to fix your prints
        "zirconyl chloride octahydrate":"ZrOCl2·8H2O",
        "zirconyl nitrate":"ZrO(NO3)2",
        "zirconyl nitrate hexahydrate":"ZrO(NO3)2·6H2O",
        "ni(no3)2 hydrate":"Ni(NO3)2·xH2O",
        "tb(no3)3 0·5h2o":"Tb(NO3)3·0.5H2O",
        "ti(oipr)4":"Ti(OiPr)4",
        "ti(oipr)4,":"Ti(OiPr)4",
        "ferric trichloride hexahydrate":"FeCl3·6H2O",
        "hydrated copper nitrate":"Cu(NO3)2·xH2O",
        "iron fine":"Fe",
        "iron metal":"Fe",
        "nickel acetylacetonate":"Ni(acac)2",
        "nickel dichloride hexahydrate":"NiCl2·6H2O",
        # also from your list
        "aluminum":"Al","aluminium":"Al","calcium":"Ca",
        "aluminum isopropoxide":"Al(OiPr)3","aluminium isopropoxide":"Al(OiPr)3",
        "bismuth nitrate(iii) pentahydrate":"Bi(NO3)3·5H2O",
        "ammonium cerium (iv) nitrate":"(NH4)2Ce(NO3)6","ammonium cerium(iv) nitrate":"(NH4)2Ce(NO3)6",
        "zirconium(iv) oxychloride octahydrate":"ZrOCl2·8H2O",
        "zirconium(iv) oxynitrate hexahydrate":"ZrO(NO3)2·6H2O",
        "vanadium(iii) acetylacetonate":"V(acac)3","calcium(ii) acetylacetonate":"Ca(acac)2",
            "cd(scy)2": "Cd(SC6H11)2",
        "co(hfac)2]": "Co(C5HF6O2)2",
        "copper(i)": "Cu",
        "copper(ii)": "Cu",
        "cu(ida)]n·2h2o": "Cu(C4H5NO4)·2H2O",
        "cu2o)": "Cu2O",
        "cuo)": "CuO",
        "europium(iii)": "Eu",
        "indium": "In",
        "me4n)2(cu2[(s": "((CH3)4N)2Cu2S2",
        "mn(salen)](clo4·2h2o": "Mn(C16H14N2O2)(ClO4)·2H2O",
        "nh4)2ce(no3)6": "(NH4)2Ce(NO3)6",
        "nh4)2ce(no3)6·6h2o": "(NH4)2Ce(NO3)6·6H2O",
        "nbcl3(dme": "NbCl3(C4H10O2)",
        "nbcl3(dme)": "NbCl3(C4H10O2)",
        "nickel(ii)": "Ni",
        "rh2(esp)2": "Rh2(C20H22O4)2",
        "ti6o6(4": "Ti6O6",
        "zirconium(iv)": "Zr",
        "zrcl4)": "ZrCl4",
        "ammonium metavanadate": "NH4VO3",
        "basic aluminum diacetate": "Al(OH)(OAc)2",
        "bis(cyclopentadienyl)titanium(iv) dichloride": "Ti(C5H5)2Cl2",
        "cerium(iv) ammonium nitrate": "(NH4)2Ce(NO3)6",
        "cesium carbonate": "Cs2CO3",
        "sodium metavanadate": "NaVO3",
        "tetrabutyl titanate": "Ti(OC4H9)4",
        "tetraethyl titanate": "Ti(OC2H5)4",
        "titanium(iv) tert-butoxide": "Ti(OC4H9)4",
        "uranyl nitrate hexahydrate": "UO2(NO3)2·6H2O",
        "zirconium(iv) oxynitrate hydrate": "ZrO(NO3)2·xH2O",
        "zirconium(iv) propoxide": "Zr(OC3H7)4",
        "zirconium(iv) propoxide solution in 1-propanol": "Zr(OC3H7)4",
        "zirconium(iv) tetrachloride": "ZrCl4",
        "cdcl2·5/2h2o": "CdCl2·2.5H2O",
        "cu(no3)2·5/2h2o": "Cu(NO3)2·2.5H2O",
            "zn(otf)2": "Zn(CF3SO3)2",
        "zirconium dioxide": "ZrO2",
        "zirconium(iv) acetylacetonate": "Zr(acac)4",
        "zirconium(iv) dinitrate oxide hydrate": "ZrO(NO3)2·6H2O",
        "ticl3)3alcl3": "TiAlCl6",
        "zn(acetate)2·2h2o": "Zn(C2H3O2)2·2H2O",
        "aluminum carbide": "Al4C3",
        "cerium ammonium nitrate": "(NH4)2Ce(NO3)6",
        "cobalt(ii) acetylacetonate": "Co(acac)2",
        "hafnium tetrachloride": "HfCl4",
        "iron(iii) acetylacetonate": "Fe(acac)3",
        "magnesium borohydride": "Mg(BH4)2",
        "zirconium(iv)": "Zr",
        "zrcl4)": "ZrCl4",
        "cuo)": "CuO",
        "europium(iii)": "Eu",
        "indium": "In"
    
    }

    def normalize_entry(v: str) -> str:
        if not is_filled(v): return v
        s = clean_unicode(v)
        s = replace_tokens(s)
        s = unify_parentheses(s)
        s = strip_qualifiers(s)
        s = cut_descriptor_tails(s)

        if re.fullmatch(r"\(*[IVXivx]+\)*", s.strip()):  # orphan Roman
            return ""

        key = s.lower().strip()
        if key in TEXT_SNAPS:
            s = TEXT_SNAPS[key]

        # pure metal name to symbol
        if key in METAL_NAME_TO_SYM and re.fullmatch(r"[A-Za-z]+", key):
            s = METAL_NAME_TO_SYM[key]

        if not re.match(r"^[A-Z][a-z]?\b", s):
            tok = pick_first_formula(s)
            if tok: s = tok

        cand = text_salt_to_formula(s)
        if cand: s = cand

        s = simplify_polyoxo_acids(s)
        s = strip_leading_cations_for_complex(s)
        s = drop_counterions_after_complex(s)

        s = normalize_dots_and_h2o(s)
        s = consolidate_hydrates(s)
        s = strip_nonwater_adducts(s)
        s = normalize_dots_and_h2o(s)
        s = consolidate_hydrates(s)

        s = final_trim(s)
        if re.fullmatch(r"\(*[IVXivx]+\)*", s): s = ""
        return s

    # ---------- run ----------
    df = pd.read_csv(input_path, dtype=str)

    # ---------- NEW: amount cleanup and inference ----------
    for c in ["metal_1_amount_text", "metal_1_amount_value", "metal_1_amount_unit"]:
        if c not in df.columns:
            df[c] = ""

    # 1) drop rows where all three are empty
    all_three_empty = (~df["metal_1_amount_text"].apply(is_filled)) & \
                      (~df["metal_1_amount_value"].apply(is_filled)) & \
                      (~df["metal_1_amount_unit"].apply(is_filled))
    df = df[~all_three_empty].copy()

    # 2) Always prefer explicit mol information from the text, even if mg/g are present
    def grab_num_unit_from_text(s):
        t = str(s)
        hits = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(umol|μmol|µmol|mmol|mol)\b", t, flags=re.I))
        if hits:
            m = hits[-1]
            num = m.group(1)
            unit = m.group(2).lower()
            if unit in {"μmol","µmol"}: unit = "umol"
            return num, unit
        return None, None

    sub = df["metal_1_amount_text"].apply(grab_num_unit_from_text)
    nums = sub.apply(lambda x: x[0] if x[0] is not None else "")
    units = sub.apply(lambda x: x[1] if x[1] is not None else "")

    text_mask = nums.str.strip().ne("") & units.str.strip().ne("")
    df.loc[text_mask, "metal_1_amount_value"] = nums[text_mask]
    df.loc[text_mask, "metal_1_amount_unit"]  = units[text_mask]

    # ---------- overwrite normalized metals ----------
    for col in ["metal_1","metal_2","metal_3"]:
        if col in df.columns:
            df[col] = df[col].astype(str).apply(normalize_entry)

    # ---------- NEW: unit conversion to mmol when possible ----------
    ATOM_MASS = {
        "H":1.0079,"B":10.811,"C":12.011,"N":14.0067,"O":15.999,"F":18.998,"Na":22.989,"Mg":24.305,"Al":26.982,"Si":28.085,
        "P":30.974,"S":32.065,"Cl":35.453,"K":39.098,"Ca":40.078,"Sc":44.956,"Ti":47.867,"V":50.942,"Cr":51.996,
        "Mn":54.938,"Fe":55.845,"Co":58.933,"Ni":58.693,"Cu":63.546,"Zn":65.38,"Ga":69.723,"Ge":72.64,"As":74.922,
        "Se":78.96,"Br":79.904,"Rb":85.468,"Sr":87.62,"Y":88.906,"Zr":91.224,"Nb":92.906,"Mo":95.95,"Ag":107.868,
        "Cd":112.411,"In":114.818,"Sn":118.71,"Sb":121.760,"Te":127.60,"I":126.904,"Ba":137.327,"La":138.905,"Ce":140.116,
        "Pr":140.908,"Nd":144.24,"Sm":150.36,"Eu":151.964,"Gd":157.25,"Tb":158.925,"Dy":162.500,"Ho":164.930,"Er":167.259,
        "Tm":168.934,"Yb":173.04,"Lu":174.967,"Hf":178.49,"Ta":180.948,"W":183.84,"Re":186.207,"Os":190.23,"Ir":192.217,
        "Pt":195.084,"Au":196.967,"Hg":200.59,"Tl":204.383,"Pb":207.2,"Bi":208.980,"Th":232.038,"U":238.029,"Li":6.941
    }

    def expand_abbrev_for_mass(s: str) -> str:
        if not is_filled(s): return s
        t = str(s)
        t = t.replace("]", "")
        repl = [
            (r"(?<![A-Za-z])MeCN(?![A-Za-z])", "C2H3N"),
            (r"(?<![A-Za-z])DMF(?![A-Za-z])", "C3H7NO"),
            (r"(?<![A-Za-z])DMSO(?![A-Za-z])", "C2H6OS"),
            (r"(?:OiPr|iPrO)", "OC3H7"),
            (r"(?:OtBu|tBuO)", "OC4H9"),
            (r"(?<![A-Za-z])(?:OAc|AcO)(?![A-Za-z])", "C2H3O2"),
            (r"(?<![A-Za-z])OMc(?![A-Za-z])", "C4H5O2"),
            (r"(?<![A-Za-z])acac(?![A-Za-z])", "C5H7O2"),
            (r"(?<![A-Za-z])Cy(?![A-Za-z])", "C6H11"),
            (r"(?<![A-Za-z])Ph(?![A-Za-z])", "C6H5"),
        ]
        for pat, rep in repl:
            t = re.sub(pat, rep, t)
        return t

    FNUM = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?")
    def _read_num(seg, i):
        m = FNUM.match(seg[i:])
        if not m: return None, i
        tok = m.group(0)
        if "/" in tok:
            a,b = tok.split("/",1)
            try: val = float(a)/float(b)
            except: val = float(a)
        else:
            val = float(tok)
        return val, i + len(tok)

    EL = re.compile(r"[A-Z][a-z]?")

    def _parse_segment(seg, mult=1.0):
        i = 0
        L = len(seg)
        counts = {}
        while i < L:
            if seg[i] in "([":
                stack = [seg[i]]
                j = i + 1
                while j < L and stack:
                    if seg[j] in "([": stack.append(seg[j])
                    elif seg[j] in ")]": stack.pop()
                    j += 1
                if stack: raise ValueError("unmatched parenthesis")
                group = seg[i+1:j-1]
                mval, k = _read_num(seg, j)
                gm = mval if mval is not None else 1.0
                sub = _parse_segment(group, mult=mult*gm)
                for e,v in sub.items(): counts[e] = counts.get(e,0.0) + v
                i = k
                continue
            mval, ni = _read_num(seg, i)
            if mval is not None:
                i = ni
                if i < L and seg[i] in "([":
                    sub = _parse_segment(seg[i:], mult=mult*mval)
                    for e,v in sub.items(): counts[e] = counts.get(e,0.0) + v
                    return counts
                m = EL.match(seg[i:])
                if not m: raise ValueError("numeric without following element")
                elem = m.group(0); i += len(elem)
                cval, i2 = _read_num(seg, i); i = i2
                n = cval if cval is not None else 1.0
                counts[elem] = counts.get(elem,0.0) + mult*mval*n
                continue
            m = EL.match(seg[i:])
            if not m: raise ValueError(f"bad token at '{seg[i:]}'")
            elem = m.group(0); i += len(elem)
            cval, i2 = _read_num(seg, i); i = i2
            n = cval if cval is not None else 1.0
            counts[elem] = counts.get(elem,0.0) + mult*n
        return counts

    def parse_formula_counts(formula: str):
        f = expand_abbrev_for_mass(formula)
        parts = [p for p in re.split(r"[·∙•⋅]", f) if p.strip() != ""]
        total = {}
        for p in parts:
            seg_counts = _parse_segment(p, 1.0)
            for e,v in seg_counts.items():
                total[e] = total.get(e, 0.0) + v
        return total

    def molar_mass(formula: str):
        counts = parse_formula_counts(formula)
        mm = 0.0
        unknown = []
        for e, n in counts.items():
            if e not in ATOM_MASS:
                unknown.append(e)
            else:
                mm += ATOM_MASS[e] * n
        if unknown:
            raise KeyError(f"unknown elements: {','.join(sorted(set(unknown)))}")
        return mm

    unparsed_formulas = set()
    unknown_tokens = set()

    def try_convert_to_mol(row):
        v = str(row.get("metal_1_amount_value","")).strip()
        u = str(row.get("metal_1_amount_unit","")).strip()
        if not is_filled(v) or not is_filled(u): return None
        try:
            val = float(v)
        except:
            return None
        u_low = u.lower()
        if u_low == "mol":
            return val*1000.0, "mmol"
        if u_low == "mmol":
            return val, "mmol"
        if u_low in {"umol","μmol","µmol"}:
            return val/1000.0, "mmol"
        if u_low in {"g","mg"}:
            formula = str(row.get("metal_1","")).strip()
            if not is_filled(formula):
                unparsed_formulas.add(("no_formula", row.get("metal_1_amount_text","")))
                return None
            try:
                mm = molar_mass(formula)
            except KeyError as e:
                unknown_tokens.add((formula, str(e)))
                return None
            except Exception:
                unparsed_formulas.add((formula, row.get("metal_1_amount_text","")))
                return None
            grams = val/1000.0 if u_low=="mg" else val
            mols = grams / mm if mm>0 else None
            if mols is None:
                unparsed_formulas.add((formula, row.get("metal_1_amount_text","")))
                return None
            return mols*1000.0, "mmol"
        return None

    conv_results = df.apply(try_convert_to_mol, axis=1)
    mask_conv = conv_results.notna()
    if mask_conv.any():
        df.loc[mask_conv, "metal_1_amount_value"] = conv_results[mask_conv].apply(lambda x: f"{x[0]:.6g}")
        df.loc[mask_conv, "metal_1_amount_unit"]  = conv_results[mask_conv].apply(lambda x: x[1])

    # report items needing review
    #if unknown_tokens:
       # print("Unknown element tokens during molar mass calc (review these formulas):")
       # for f, msg in sorted(unknown_tokens):
           # print(f"  {f} -> {msg}")
    #if unparsed_formulas:
        #print("Unparsed or complex formulas for mass conversion (left as is):")
        #for f, context in sorted(unparsed_formulas):
            #print(f"  {f} | context: {context}")

    # ---------- drop rows if any metal column contains framework/BTC/Zn-EG/acid/salt ----------
    def row_should_drop(row):
        for c in ["metal_1","metal_2","metal_3"]:
            if c not in row: continue
            val = row[c]
            if not is_filled(val): continue
            if FRAMEWORK_PAT.search(val) or CLUSTER_PAT.search(val) or TEMPLATE_PAT.search(val): return True
            if BTC_PAT.search(val) or ZNEG_PAT.search(val): return True
            if SALT_PAT.search(val) or ACID_PAT.search(val): return True
        return False

    drop_mask0 = df.apply(row_should_drop, axis=1)
    dropped0 = int(drop_mask0.sum())
    df = df[~drop_mask0].copy()

    # 1) drop if metal_1 is NaN or empty
    drop_mask_nan = ~df["metal_1"].apply(is_filled)
    dropped_nan = int(drop_mask_nan.sum())
    df = df[~drop_mask_nan].copy()

    # 2) drop if metal_1 non-compliant
    noncomp_m1_vals = set(v.strip() for v in df["metal_1"].astype(str) if v.strip() and not COMPLIANT.fullmatch(v.strip()))
    drop_mask_nc = df["metal_1"].astype(str).str.strip().isin(noncomp_m1_vals)
    dropped_nc = int(drop_mask_nc.sum())
    df = df[~drop_mask_nc].copy()

    # 3) drop if metal_1 value occurs once and length ≤ 10 and has no '(' or ')'
    m1_clean = df["metal_1"].astype(str).str.strip()
    counts = m1_clean.value_counts()
    singles = set(counts[counts==1].index)
    def is_unique_short_no_paren(x):
        x = str(x).strip()
        if x in singles and len(x) <= 10 and ("(" not in x and ")" not in x):
            return True
        return False
    drop_mask_unique = m1_clean.apply(is_unique_short_no_paren)
    dropped_unique = int(drop_mask_unique.sum())
    df = df[~drop_mask_unique].copy()

    # ---------- final filter on amount fields before save ----------
    bad_unit = (~df["metal_1_amount_unit"].apply(is_filled)) | (df["metal_1_amount_unit"].isin(["mL","mM"]))
    text_has_keys = df["metal_1_amount_text"].astype(str).str.contains(r"\beq\b|\bmolar\b|\bratio\b|:", case=False, na=False)
    df = df[~(bad_unit & ~text_has_keys)].copy()

    # save
    df = df.fillna("")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    # stats
    print(f"Dropped framework/BTC/Zn-EG/acid/salt rows: {dropped0}")
    print(f"Dropped metal_1 NaN/empty rows: {dropped_nan}")
    print(f"Dropped metal_1 non-compliant rows: {dropped_nc}")
    print(f"Dropped metal_1 unique-short-no-paren rows: {dropped_unique}")
    print(f"Rows left: {len(df)}")

    # metal_1 stats
    m1 = df["metal_1"].astype(str).str.strip()
    m1 = m1[m1!=""]
    uniq = m1.nunique()
    print(f"Unique metal_1 values: {uniq}")

    vc = m1.value_counts()
    print("\nTop 50 metal_1:")
    print(vc.head(50).to_string())

    print("\nLeast 50 metal_1:")
    print(vc.sort_values(ascending=True).head(50).to_string())
    return Path(output_path)

