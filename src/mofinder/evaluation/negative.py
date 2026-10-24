"""Evaluate saved negative-synthesis rows against the reviewed constraint benchmark.

Run ``python -m mofinder.evaluation.negative model_rows.csv --ground-truth reference.xlsx``.
No model requests are made. Negative-only evaluation is the default. A ground-truth
window represents a documented failure constraint, sometimes an open-ended family;
it is not necessarily one fully specified experimental protocol. Consequently row
precision and window coverage recall have different true-positive denominators.
The separate fixed-reference panel reports numeric accuracy from covered failure
windows and retention of associated recorded successful-control profiles.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import zlib

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.packaging.custom import StringProperty

from mofinder.display import display_path
from mofinder.run_paths import create_run_directory
from mofinder.evaluation.positive import doi_key


# Chemistry and reference-window matching definitions.
from types import SimpleNamespace

from fractions import Fraction
import functools
import itertools
from math import gcd
from pathlib import Path
import re

import numpy as np

# ---------------- Copied from step 4 clean data.ipynb, cells 5, 7, and 8 ----------------

def remove_linker_trailing_parens(val):
    """For linker names like 'salicylic acid (H2L1)' remove trailing ' (H2L1)'"""
    if not is_filled(val):
        return val, False
    s = str(val).strip()
    new_s = re.sub(r"\s\([^)]*\)\s*$", "", s)
    return new_s, new_s != s


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


def fmt_frac(n: float) -> str:
    if float(n).is_integer(): return str(int(n))
    f = Fraction(n).limit_denominator(12)
    return f"{f.numerator}/{f.denominator}"


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
    # Corrected source typo: H3BTB is distinct from terephthalic acid (H2BDC).
    "h3btb": "1,3,5-tris(4-carboxyphenyl)benzene",
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

# ---------------- Matcher interface ----------------

LINKER_MW_FILE = Path(__file__).resolve().parents[3] / "benchmarks/negative_reconstruction/linker_molecular_weights.csv"
LINKER_MW_DATA = None  # Optional calibration embedded in a single-sheet reference workbook.


@functools.lru_cache(maxsize=None)
def linker_molar_masses():
    """{lowercase linker name: g/mol} from LINKER_MW_FILE; rows without a number are skipped."""
    import pandas as pd

    if LINKER_MW_DATA is not None:
        return {str(name).strip().lower(): float(value) for name, value in LINKER_MW_DATA.items()}
    masses = {}
    if not LINKER_MW_FILE.exists():
        return masses
    table = pd.read_csv(LINKER_MW_FILE, header=None, names=["linker_name", "mw"], dtype=str, encoding="utf-8")
    for _, row in table.iterrows():
        try:
            value = float(str(row["mw"]).strip())
        except Exception:
            continue
        if str(row["linker_name"]).strip() and np.isfinite(value):
            masses[str(row["linker_name"]).strip().lower()] = value
    return masses


def _blank_name(name):
    return name is None or (isinstance(name, float) and name != name) or not str(name).strip()


def _molar_mass_with_hydrate(formula):
    """The notebook's molar_mass, with the water of crystallization added back correctly. Its own parse_formula_counts applies the
    hydrate count to the H atoms only (CoCl2.6H2O -> O counted once: 157.9 g/mol instead of 237.9; 'Zn(NO3)2.6H2O' with a plain dot
    is mis-parsed entirely), so every mg -> mmol conversion of a hydrated metal salt in the training data comes out high."""
    f = str(formula).strip()
    m = re.match(r"^(?P<base>.+?)\s*(?:[·•\*]|\.(?=\d*H2O$))\s*(?P<n>\d+(?:\.\d+)?)?\s*H2O$", f)
    if m and m.group("base"):
        n = float(m.group("n")) if m.group("n") else 1.0
        return float(molar_mass(m.group("base"))) + n * 18.0148
    return float(molar_mass(f))


@functools.lru_cache(maxsize=None)
def clean_metal(name):
    """Canonical metal string (formula form when one can be built), or None for a blank name."""
    if _blank_name(name):
        return None
    try:
        return str(canon_metal(normalize_entry(str(name)))).strip() or None
    except Exception:
        return str(name).strip()


@functools.lru_cache(maxsize=None)
def clean_linker(name):
    """Canonical linker string, or None for a blank name."""
    if _blank_name(name):
        return None
    s = str(name).strip()
    try:
        s = str(canon_linker(s)).strip()
        mapped = LINKER_MAP.get(s.lower())
        return mapped or s
    except Exception:
        return s


@functools.lru_cache(maxsize=None)
def molar_mass_of(name, kind):
    """g/mol of a metal salt (from its formula) or a linker (from LINKER_MW_FILE), or None."""
    try:
        if kind == "metal":
            f = normalize_entry(str(name))
            return _molar_mass_with_hydrate(f) if f else None
        masses = linker_molar_masses()
        return masses.get(clean_linker(name).lower()) or masses.get(str(name).strip().lower())
    except Exception:
        return None


def mass_to_mmol(value, unit, name, kind):
    """The notebook's unit rules (try_convert_to_mol for metals, convert_row for linkers): umol/mol/mmol scale directly;
    mg/g need the reagent's molar mass."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = str(unit).strip().lower() if unit is not None else ""
    if u == "mmol":
        return v
    if u in ("umol", "μmol", "µmol"):
        return v / 1000.0
    if u == "mol":
        return v * 1000.0
    if u in ("mg", "g", "milligram", "milligrams", "gram", "grams"):
        mm = molar_mass_of(name, kind)
        if not mm:
            return None
        return v / mm if u in ("mg", "milligram", "milligrams") else v * 1000.0 / mm
    return None

# The window matcher calls these four functions as negative_reagent_names.<name>, as in the package.
negative_reagent_names = SimpleNamespace(clean_metal=clean_metal, clean_linker=clean_linker,
                                         molar_mass_of=molar_mass_of, mass_to_mmol=mass_to_mmol)

import re
import unicodedata

import numpy as np
import pandas as pd

# ---------------- Text normalization ----------------

def norm_str(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().lower()
    if s in ("none", "null", "nan", ""):
        return None
    # Fold typographic prime (′) / double-prime (″) and curly
    # apostrophe (’), used interchangeably with a plain "'" in chemical
    # names (e.g. "2,2'-bipyridine" vs "2,2′-bipyridine"), to their plain
    # ASCII form -- otherwise categorical_distance treats the identical
    # compound as "different" whenever one side uses the other's convention.
    s = s.replace("′", "'").replace("″", "''").replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s


LOOSE_MATCH_MIN_LEN = 8  # shorter string must be at least this long (post-normalization)
                         # before a substring match counts -- guards against short/generic
                         # anchors like "acid" or "none" matching almost anything


def norm_loose(s) -> str:
    """Punctuation- and Unicode-variant-insensitive normalization for fuzzy
    categorical matching. Folds prime (u2032) and curly apostrophe (u2019) to a
    plain apostrophe, then strips everything but letters/digits and lowercases.
    Deliberately does NOT strip parenthetical content -- "iron(II)" and
    "iron(III)" normalize to "ironii" and "ironiii", which stay distinct."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.replace("′", "'").replace("’", "'")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _loose_tokens(s):
    """Split a chemical name into (token, is_bracketed) pairs for whole-token
    matching. Splits only on whitespace, brackets and ", " (comma+space) --
    NOT on a bare comma or hyphen, which sit inside real names ("1,3-bis",
    "4,4'-bipyridine") -- then strips each token down to letters/digits, so
    prime/apostrophe variants ("2′,5′-" vs "2',5'-") compare equal."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    s = unicodedata.normalize("NFKD", str(s)).lower()
    out, depth = [], 0
    for piece in re.split(r"(\s+|[()\[\]{}]|,\s)", s):
        if piece in ("(", "[", "{"):
            depth += 1
        elif piece in (")", "]", "}"):
            depth = max(depth - 1, 0)
        else:
            tok = re.sub(r"[^a-z0-9]", "", piece)
            if tok:
                out.append((tok, depth > 0))
    return out


def loose_categorical_match(value, categorical) -> bool:
    """True if the two strings refer to the same thing modulo formatting --
    the shorter one's tokens appear as a contiguous WHOLE-TOKEN run inside the
    longer one, e.g. a bracketed formula suffix ("... [Cu(NO3)2.3H2O]"), an
    appended label (", 6(Cl)"), or a trailing descriptor ("(aqueous, 2 M)").
    Short strings (under LOOSE_MATCH_MIN_LEN) only match when everything extra
    on the longer side is bracketed ("water" vs "water (as KOH aq.)"), so a
    generic "acid" still can't match "acetic acid".
    Replaces a raw substring test on the punctuation-stripped strings (fixed
    2026-09-28): that let "imidazole" match "1-methylimidazole", and rejected
    "water" vs "water (as KOH aq.)" outright on length."""
    a, b = _loose_tokens(value), _loose_tokens(categorical)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    st = [t for t, _ in shorter]
    for i in range(len(longer) - len(st) + 1):
        if [t for t, _ in longer[i:i + len(st)]] == st:
            if len("".join(st)) >= LOOSE_MATCH_MIN_LEN:
                return True
            extra = longer[:i] + longer[i + len(st):]
            if all(br for _, br in extra):
                return True
    return False


def same_component(cand_name, parent_name, cand_abbr=None, parent_abbr=None) -> bool:
    """Do two slot entries name the same reagent? Exact (normalized) name,
    whole-token loose name match, a shared abbreviation, or one side's name
    equal to the other side's abbreviation ("HTT" vs "...hexathiol" / abbr HTT)."""
    if norm_str(cand_name) is not None and norm_str(cand_name) == norm_str(parent_name):
        return True
    if loose_categorical_match(cand_name, parent_name):
        return True
    ca, pa = norm_loose(cand_abbr), norm_loose(parent_abbr)
    if ca and pa and ca == pa:
        return True
    if ca and ca == norm_loose(parent_name):
        return True
    if pa and pa == norm_loose(cand_name):
        return True
    return _bridge_same_name(cand_name, parent_name)


# --- names via the cleaning notebook (added 2026-09-29) -------------------------------------------------------------
# Two spellings of one reagent should match the way the pipeline itself would merge them: the notebook's metal/linker
# normalizers (formula form, synonym maps), plus a shared hyphenated code token ("GU-3") when the names also share a
# descriptive word, so "clathrochelate linker GU-3" == "iron(II) clathrochelate ligand GU-3 (phenyl-substituted)".
_CODE_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,5}-\d+[A-Za-z]{0,2}(?![A-Za-z0-9])")


def _bridge_same_name(a, b) -> bool:
    if _blank(a) or _blank(b):
        return False
    try:
        for clean in (negative_reagent_names.clean_metal, negative_reagent_names.clean_linker):
            ca, cb_ = clean(a), clean(b)
            if ca and cb_ and len(norm_loose(ca)) >= 4 and norm_loose(ca) == norm_loose(cb_):
                return True
    except Exception:
        pass
    ta = {t.lower() for t in _CODE_TOKEN.findall(str(a))}
    tb = {t.lower() for t in _CODE_TOKEN.findall(str(b))}
    if ta and ta == tb:
        wa = {w for w in re.findall(r"[a-z]{6,}", str(a).lower())}
        wb = {w for w in re.findall(r"[a-z]{6,}", str(b).lower())}
        return bool(wa & wb)
    return False

# ---------------- Numeric tolerance ----------------
# Distance is measured in standard deviations of each field's own spread across
# the parent records, log1p-transformed for concentration- and time-like fields.

LOG_SCALE_FIELDS = {
    "metal_1_amount_value", "metal_2_amount_value", "metal_3_amount_value",
    "linker_1_amount_value", "linker_2_amount_value", "linker_3_amount_value",
    "modulator_1_amount_value", "modulator_2_amount_value",
    "solvent_main_ml", "solvent_secondary_ml",
    "time_h", "activation_time_h",
}
LINEAR_FIELDS = {
    "temperature_c", "activation_temp_c", "tga_decomposition_temp_c",
}
RELATIVE_FIELDS = {  # measurement-precision-limited, scored as % of GT value
    "yield_percent", "pore_diameter_A", "BET_surface_area_m2g",
}
ALL_NUMERIC_FIELDS = LOG_SCALE_FIELDS | LINEAR_FIELDS | RELATIVE_FIELDS


def field_scale(gt_df, field):
    """Empirical spread of a field across the ground truth Positive Records --
    this IS the 'acceptable range' calibration, replacing any fixed number."""
    col = pd.to_numeric(gt_df[field], errors="coerce")
    if field in LOG_SCALE_FIELDS:
        col = np.log1p(col.clip(lower=0))
    scale = col.std(skipna=True)
    if not scale or pd.isna(scale):
        scale = 1.0
    return scale


def numeric_distance(query_val, gt_val, field, scale):
    if query_val is None or (isinstance(query_val, float) and pd.isna(query_val)):
        return 1.0 if gt_val is not None and not pd.isna(gt_val) else 0.0
    if gt_val is None or pd.isna(gt_val):
        return 1.0
    try:
        qv, gv = float(query_val), float(gt_val)
    except (TypeError, ValueError):
        # A nominally numeric cell holding text (a copy/paste error) is reported
        # as a full mismatch rather than crashing the evaluation.
        return 1.0
    if field in LOG_SCALE_FIELDS:
        qv, gv = np.log1p(max(qv, 0)), np.log1p(max(gv, 0))
    elif field in RELATIVE_FIELDS and gv != 0:
        # relative (%) distance for measurement-limited quantities
        return min(abs(qv - gv) / abs(gv), 1.0)
    d = abs(qv - gv) / scale
    return min(d / 3.0, 1.0)  # clip at 3 std devs, normalize to [0,1]

# ---------------- Amount units ----------------
# Amount units -> (dimension, factor to the base unit of that dimension: mmol, mg, mL).
# Mole <-> mass can't be converted without a molar mass, so those stay incomparable.
_UNIT_PREFIX = {"": 1.0, "k": 1e3, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "n": 1e-9}
_UNIT_BASE = {"mol": ("mol", 1e3), "g": ("mass", 1e3), "l": ("vol", 1e3)}


def parse_unit(unit):
    """'mmol', 'µmol', 'μmol', 'mmol (Zn)', 'mg', 'g', 'mL', 'µL' -> (dimension, factor);
    None for anything else ('equiv', '% v/v of solvent', blank)."""
    u = norm_str(unit)
    if u is None:
        return None
    u = re.sub(r"\s*\(.*\)$", "", u).strip()
    m = re.fullmatch(r"(k|m|u|µ|μ|n)?(mol|g|l)", u)
    if not m:
        return None
    dim, base = _UNIT_BASE[m.group(2)]
    return dim, _UNIT_PREFIX[m.group(1) or ""] * base


def convert_amount(value, from_unit, to_unit):
    """Express `value` (in from_unit) in to_unit. Returns the value unchanged if
    the units already match textually, None if they can't be reconciled."""
    if norm_str(from_unit) == norm_str(to_unit):
        return value
    fu, tu = parse_unit(from_unit), parse_unit(to_unit)
    if fu is None or tu is None or fu[0] != tu[0]:
        return None
    try:
        return float(value) * fu[1] / tu[1]
    except (TypeError, ValueError):
        return None


def convert_amount_named(value, from_unit, to_unit, cand_name=None, parent_name=None, field=""):
    """convert_amount, plus mass <-> mole through the cleaning notebook's own molar masses (metals: formula from the name;
    linkers: 'linker and mw.csv'), so 400 mg of Mn(OAc)2*4H2O can be compared with a base written in mmol."""
    out = convert_amount(value, from_unit, to_unit)
    if out is not None:
        return out
    kind = "metal" if str(field).startswith("metal") else "linker" if str(field).startswith("linker") else None
    fu, tu = parse_unit(from_unit), parse_unit(to_unit)
    if kind is None or fu is None or tu is None:
        return None
    try:
        if fu[0] == "mass" and tu[0] == "mol":            # mass -> mmol (candidate's own reagent) -> target mole unit
            mmol = negative_reagent_names.mass_to_mmol(float(value) * fu[1], "mg", cand_name, kind)
            return None if mmol is None else mmol / tu[1]
        if fu[0] == "mol" and tu[0] == "mass":            # mole -> mass, via the parent's reagent
            mm = negative_reagent_names.molar_mass_of(parent_name, kind)
            return None if not mm else float(value) * fu[1] * mm / tu[1]
    except Exception:
        return None
    return None

# ---------------- Field checks ----------------

AMOUNT_REL_TOL = 0.05  # amounts/volumes within 5% of each other are the same value (rounding in the paper)


def _blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or norm_str(v) is None


def field_differs_from_parent(candidate: dict, parent: dict, field: str, gt_df) -> bool:
    """True if candidate[field] is a real change from parent[field] (not just
    missing/noise). Fixed 2026-09-28:
      - a blank PARENT value is not a conflict (the base recipe simply didn't
        record it -- e.g. no solvent_secondary on the base while the miner
        reports the 0.037 mL of water the paper mentions);
      - amounts are compared in the same unit (µmol vs mmol, mg vs g), and an
        amount whose unit can't be reconciled with the base's (mg vs mmol) is
        not treated as a conflict -- there's no molar mass to check it with;
      - amounts and volumes use a 5% relative tolerance instead of the
        std-dev-scaled one, which was loose enough to call 0.08 and 0.10 mmol
        the same;
      - names match on whole-token loose matching and abbreviations, not only
        an exact normalized string."""
    cv, pv = candidate.get(field), parent.get(field)
    if _blank(pv):
        return False
    if field.endswith("_amount_value") or field.endswith("_ml"):
        if _blank(cv):
            return True
        if field.endswith("_amount_value"):
            unit_field = field.replace("_amount_value", "_amount_unit")
            cv = convert_amount_named(cv, candidate.get(unit_field), parent.get(unit_field),
                                      candidate.get(field.replace("_amount_value", "")), parent.get(field.replace("_amount_value", "")), field)
            if cv is None:
                return False
        try:
            c, p = float(cv), float(pv)
        except (TypeError, ValueError):
            return True
        return abs(c - p) > AMOUNT_REL_TOL * max(abs(c), abs(p), 1e-12)
    if field in ALL_NUMERIC_FIELDS:
        scale = field_scale(gt_df, field)
        return numeric_distance(cv, pv, field, scale) > 0.05  # small tolerance for float noise
    return not same_component(cv, pv, candidate.get(field + "_abbr"), parent.get(field + "_abbr"))


def predicate_satisfied(value, field_row: dict) -> bool:
    """Does `value` (the candidate's own proposed value for this field) fall
    inside the bucket field's acceptable predicate?"""
    ptype = field_row["predicate_type"]
    if ptype == "categorical_equals":
        if norm_str(value) == norm_str(field_row["predicate_categorical"]):
            return True
        return (loose_categorical_match(value, field_row["predicate_categorical"])
                or _bridge_same_name(value, field_row["predicate_categorical"]))
    if ptype == "exclusion":
        if norm_str(value) == norm_str(field_row["predicate_categorical"]):
            return False
        if loose_categorical_match(value, field_row["predicate_categorical"]):
            return False
        if _bridge_same_name(value, field_row["predicate_categorical"]):
            return False
        return True
    if ptype == "discrete_set":
        # discrete_set holds EITHER a numeric list ("1 ||| 3 ||| 5") OR a
        # categorical list ("acetic acid ||| sodium hydroxide ||| ..."); try
        # numeric first, fall back to a normalized-string membership check.
        # Checking type here (before the blanket float() cast below) is a fix --
        # the old code unconditionally tried float(value) first and silently
        # rejected every categorical discrete_set as a side effect.
        # NOT a bare comma: real member names are full of legitimate commas
        # ("4,4'-bipyridine", "1,10-phenanthroline", "2,2'-bipyridine") --
        # splitting on those shreds a single correct member into garbage
        # fragments that can never match anything (a real bug this fixes).
        members = [m.strip() for m in str(field_row["predicate_categorical"]).split(" ||| ")]
        try:
            allowed_nums = [float(m) for m in members]
            v = float(value)
            return any(abs(v - a) < 1e-6 for a in allowed_nums)
        except (TypeError, ValueError):
            if norm_str(value) in {norm_str(m) for m in members}:
                return True
            return any(loose_categorical_match(value, m) or _bridge_same_name(value, m) for m in members)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if ptype == "range":
        return field_row["predicate_value_1"] <= v <= field_row["predicate_value_2"]
    if ptype == "gt":
        return v > field_row["predicate_value_1"]
    if ptype == "lt":
        return v < field_row["predicate_value_1"]
    return False  # unparsed_freetext -- cannot be automatically checked yet

# ---------------- Window parents ----------------

def resolve_bucket_parent(bucket_row, positives_df):
    """The specific positive record THIS bucket declares as its parent (by the
    paper's own success_index numbering), independent of any other bucket."""
    if pd.isna(bucket_row["based_on_success_index"]):
        return None
    rows = positives_df[(positives_df["doi"] == bucket_row["doi"]) &
                         (positives_df["success_index"] == int(bucket_row["based_on_success_index"]))]
    return rows.iloc[0].to_dict() if len(rows) == 1 else None

# ---------------- Window fit ----------------

# Only these fields decide whether a candidate is describing the same base
# synthesis as a bucket's parent: metal/linker/modulator IDENTITY (name only,
# not amount) plus solvent info, temperature, and time. Explicitly NOT washing
# (not important for negative data at all) and NOT modulator amounts in this
# general check (an amount can still be an explicit ANCHOR when a bucket is
# specifically testing one, e.g. the AcOH-range or bulk-synthesis-scale
# buckets -- this only scopes the generic "same base synthesis" consistency
# check for non-anchor fields).
CONSISTENCY_CHECK_FIELDS = {
    "metal_1", "metal_2", "metal_3",
    "metal_1_amount_value", "metal_2_amount_value", "metal_3_amount_value",
    "linker_1", "linker_2", "linker_3",
    "linker_1_amount_value", "linker_2_amount_value", "linker_3_amount_value",
    "modulator_1", "modulator_2",  # name only -- modulator AMOUNT is excluded
    "solvent_main", "solvent_secondary", "solvent_main_ml", "solvent_secondary_ml",
    "temperature_c", "time_h",
}


# Multi-slot component systems and the per-slot sub-fields that travel with a
# slot when it's re-aligned (see align_slots).
SLOT_SYSTEMS = {
    "metal": ["metal_1", "metal_2", "metal_3"],
    "linker": ["linker_1", "linker_2", "linker_3"],
    "modulator": ["modulator_1", "modulator_2"],
    "solvent": ["solvent_main", "solvent_secondary"],
}
SLOT_SUBFIELDS = ["", "_abbr", "_amount_text", "_amount_value", "_amount_unit"]
SOLVENT_SUBFIELDS = ["", "_abbr", "_amount_text", "_ml"]


def align_slots(candidate: dict, parent: dict) -> dict:
    """Re-order the candidate's slots within each component system so a reagent
    the parent also has sits in the SAME slot the parent keeps it in. Slot
    numbers are positional bookkeeping, not chemistry: when the miner removes
    modulator_1 (pyrazole) it moves the remaining dilute HNO3 up from
    modulator_2 into modulator_1, and the positive miner may file a reagent
    in a different slot than the base recipe does (Fe salt in metal_1 vs the
    base's metal_3). Without this, both cases read as "the candidate changed
    the modulator/metal" and the row was rejected (fixed 2026-09-28).
    Reagents the parent doesn't have keep their own slot where it's free."""
    out = dict(candidate)
    for system, slots in SLOT_SYSTEMS.items():
        subs = SOLVENT_SUBFIELDS if system == "solvent" else SLOT_SUBFIELDS
        entries = [{s: candidate.get(slot + s) for s in subs} for slot in slots]
        filled = [i for i, e in enumerate(entries) if not _blank(e[""])]
        target = {}
        for i in filled:  # pass 1: follow the parent's slot for shared reagents (prefer staying put)
            order = [i] + [j for j in range(len(slots)) if j != i]
            for j in order:
                if j in target.values():
                    continue
                if same_component(entries[i][""], parent.get(slots[j]),
                                  entries[i]["_abbr"], parent.get(slots[j] + "_abbr")):
                    target[i] = j
                    break
        for i in filled:  # pass 2: everything else keeps its slot if free, else the next free one
            if i in target:
                continue
            free = [j for j in range(len(slots)) if j not in target.values()]
            target[i] = i if i in free else free[0]
        if all(target.get(i) == i for i in filled):
            continue
        for slot in slots:
            for s in subs:
                out[slot + s] = None
        for i, j in target.items():
            for s in subs:
                out[slots[j] + s] = entries[i][s]
    return out


NUMERIC_PREDICATES = {"range", "gt", "lt"}


def _all_numeric(members) -> bool:
    try:
        [float(m) for m in str(members).split(" ||| ")]
        return True
    except ValueError:
        return False


def _effective_anchor_value(candidate: dict, parent: dict, field: str, f):
    """The value an anchor predicate should see. Numeric fields: a blank value
    means the miner left that quantity at the base recipe's value, so it
    inherits the parent's (a blank solvent volume on the pure-water row is not
    "outside 1.9-5.1 mL"); amounts are converted into the parent's unit first,
    since the window's thresholds are written in the base recipe's unit."""
    v = candidate.get(field)
    numeric = f["predicate_type"] in NUMERIC_PREDICATES or (
        f["predicate_type"] == "discrete_set" and _all_numeric(f["predicate_categorical"]))
    if not numeric:
        return v
    required_unit = f.get("required_unit")
    if required_unit:
        # Explicit opt-in policy for newly adjudicated constraints. Cross-dimension
        # conversion requires a source-documented multiplier in the reference.
        if _blank(v):
            return None
        unit_field = field.replace("_amount_value", "_amount_unit")
        unit = candidate.get(unit_field)
        converted = convert_amount(v, unit, required_unit)
        if converted is not None:
            return converted
        for bridge_unit, factor in (f.get("unit_conversions") or {}).items():
            bridged = convert_amount(v, unit, bridge_unit)
            if bridged is not None:
                try:
                    return float(bridged) * float(factor)
                except (TypeError, ValueError):
                    return None
        return None
    if _blank(v):
        return parent.get(field)
    if field.endswith("_amount_value"):
        unit_field = field.replace("_amount_value", "_amount_unit")
        # plain unit conversion only (mass <-> mole is deliberately NOT bridged here: some windows write mmol thresholds on a gram
        # base -- cg700979r -- so a mass<->mole conversion would move the value away from the threshold's own unit)
        converted = convert_amount(v, candidate.get(unit_field), parent.get(unit_field))
        # No conversion possible (mmol vs g): use the raw value -- some windows'
        # thresholds are written in the miner's own unit rather than the base
        # recipe's (cg700979r: mmol thresholds on a gram-unit base).
        return v if converted is None else converted
    return v


def anchor_satisfied(candidate: dict, parent: dict, f) -> bool:
    """predicate_satisfied, plus: a categorical anchor on a reagent-name field
    also accepts the candidate's abbreviation column (anchor "tpbz" vs miner
    name "1,3,5-tris(4-pyridyl)benzene" with abbr tpbz), and an exclusion
    anchor rejects the candidate if EITHER its name or its abbreviation is the
    excluded reagent (fixed 2026-09-28)."""
    field = f["field_name"]
    numeric = f["predicate_type"] in NUMERIC_PREDICATES or (
        f["predicate_type"] == "discrete_set" and _all_numeric(f["predicate_categorical"]))
    if f.get("require_explicit_numeric_anchor", False) and numeric and _blank(candidate.get(field)):
        return False
    v = _effective_anchor_value(candidate, parent, field, f)
    ok = predicate_satisfied(v, f)
    abbr = candidate.get(field + "_abbr") if not field.endswith(("_value", "_ml", "_text")) else None
    if _blank(abbr) or f["predicate_type"] in NUMERIC_PREDICATES:
        return ok
    ok_abbr = predicate_satisfied(abbr, f)
    if f["predicate_type"] == "exclusion":
        return ok and ok_abbr
    return ok or ok_abbr


def explain_candidate(candidate: dict, parent: dict, bucket_field_rows: pd.DataFrame,
                      positives_df: pd.DataFrame, bucket_logic: str = "all_required"):
    """Every reason `candidate` fails this bucket, as (check, field, candidate_value,
    parent_or_predicate) tuples -- an empty list means it satisfies the bucket.
    None if the bucket has an unparsed_freetext anchor. candidate_satisfies_bucket
    is just `not explain_candidate(...)`, so diagnostics and scoring can't drift apart."""
    anchors = bucket_field_rows[bucket_field_rows["field_role"] == "anchor"]
    if anchors["predicate_type"].eq("unparsed_freetext").any():
        return None
    # Slot layout is ambiguous in both directions: some windows are themselves
    # written in the shifted layout (acsomega.3c09256_B1 anchors the Fe salt in
    # metal_1 after the base's metal_1 is removed), others assume the base's
    # layout. A candidate satisfies the bucket if EITHER its own layout or the
    # parent-aligned layout does; diagnostics report the reading with fewer fails.
    raw = _explain(candidate, parent, anchors, positives_df, bucket_logic)
    if not raw:
        return raw
    aligned = align_slots(candidate, parent)
    if aligned == candidate:
        return raw
    al = _explain(aligned, parent, anchors, positives_df, bucket_logic)
    return al if len(al) < len(raw) else raw


def _substitution_exempt_fields(candidate: dict, parent: dict, anchor_names: set) -> set:
    """Slot-forgiving substitution (2026-09-29). When a window anchors ANY slot of a component system (metal / linker /
    modulator / solvent), a reagent the candidate brings that the parent does not have may sit in ANY slot of that system, and
    its amount / volume belongs to it, not to the base recipe -- so those slot fields are exempt from the consistency check.
    Only one new reagent per system is forgiven (a substitution); two or more new reagents in a system are still a second change."""
    out = set()
    for system, slots in SLOT_SYSTEMS.items():
        if not any(a in anchor_names or a.startswith(tuple(sl + "_" for sl in slots)) for a in anchor_names):
            continue
        if not any(a in slots or any(a.startswith(sl + "_") for sl in slots) for a in anchor_names):
            continue
        new_slots = []
        for sl in slots:
            name = candidate.get(sl)
            if _blank(name):
                continue
            if not any(same_component(name, parent.get(pl), candidate.get(sl + "_abbr"), parent.get(pl + "_abbr")) for pl in slots):
                new_slots.append(sl)
        if len(new_slots) == 1:
            sl = new_slots[0]
            out |= {sl, sl + "_abbr", sl + "_amount_value", sl + "_ml"}
    return out


_SCALE_FIELDS = ["metal_1_amount_value", "metal_2_amount_value", "metal_3_amount_value", "linker_1_amount_value",
                 "linker_2_amount_value", "linker_3_amount_value", "solvent_main_ml", "solvent_secondary_ml"]


def _scale_equivalent_fields(candidate: dict, parent: dict, anchor_names: set) -> set:
    """Same recipe at a different scale (2026-09-29). If every quantity the candidate and the parent both report (metal / linker
    amounts, solvent volumes; mass <-> mole converted through the cleaning notebook) differs by ONE common factor (>= 1.3x or
    <= 1/1.3, spread within 15%), the candidate is the parent scaled up/down, not a different condition: those quantities are
    exempt from the consistency check (amount anchors are unaffected)."""
    ratios = {}
    for f in _SCALE_FIELDS:
        c, p = candidate.get(f), parent.get(f)
        if _blank(c) or _blank(p):
            continue
        try:
            if f.endswith("_amount_value"):
                uf = f.replace("_amount_value", "_amount_unit")
                c = convert_amount_named(c, candidate.get(uf), parent.get(uf), candidate.get(f.replace("_amount_value", "")),
                                         parent.get(f.replace("_amount_value", "")), f)
                if c is None:
                    continue
            c, p = float(c), float(p)
        except (TypeError, ValueError):
            continue
        if c > 0 and p > 0:
            ratios[f] = c / p
    if len(ratios) < 3:
        return set()
    lo, hi = min(ratios.values()), max(ratios.values())
    gm = (lo * hi) ** 0.5
    if hi / lo <= 1.15 and (gm >= 1.3 or gm <= 1 / 1.3):
        return set(ratios)
    return set()


# "Extra reasonable variables" switch (2026-10-03: the miner should not be penalized for proposing additional
# reasonable variation -- modulator, temperature, time -- alongside the window's own variable). DEFAULT OFF: with the
# defaults below the matcher behaves exactly as before. Set from a scoring script, e.g.
#   negative_window_matching.TOLERATED_EXTRA_FIELDS = {"modulator_1", "modulator_2", "temperature_c", "time_h"}
#   negative_window_matching.TOLERATED_MAX_EXTRA = None   # any number of tolerated fields may differ, or an int cap
# A row that differs from the parent in a tolerated field (that is not one of this window's own anchors) is no longer
# rejected by the consistency check for that field. Composition fields (metals, linkers, solvents, amounts) stay strict.
TOLERATED_EXTRA_FIELDS = frozenset()
TOLERATED_MAX_EXTRA = None


def _explain_vs_parent(candidate, parent, anchors, positives_df, bucket_logic):
    anchor_names = set(anchors["field_name"])
    fails = []
    tolerated_diffs = []
    # Generalized identity-consistency check: a candidate should only satisfy
    # THIS bucket's parent if everything it reports, other than the fields
    # this bucket is itself anchored on, is actually consistent with that
    # parent -- not just the one anchor field. Fields the candidate leaves
    # blank are not penalized (a partial submission is normal); only fields
    # it actually populates are checked, using the same tolerance-based
    # distance already used for anchors (so float noise in amounts doesn't
    # cause false rejections). Real bug this fixes: two analogous compounds
    # in one paper (e.g. two POM-MOFs differing only in a reagent amount, or
    # a Dy- vs Tb-based pair) failing the same way -- a candidate correctly
    # built for one was satisfying the OTHER's bucket too, since only the
    # anchor field itself was ever checked before.
    exempt = _substitution_exempt_fields(candidate, parent, anchor_names)
    # An explicitly adjudicated absolute-dose rule is calibrated to its stated
    # parent loading. Exempting scaled stable amounts while leaving the dose
    # threshold unscaled can turn a scaled successful recipe into a false hit.
    strict_parent = "strict_parent_consistency" in anchors and anchors["strict_parent_consistency"].any()
    if not strict_parent:
        exempt |= _scale_equivalent_fields(candidate, parent, anchor_names)
    for field in sorted(CONSISTENCY_CHECK_FIELDS - anchor_names - exempt):
        val = candidate.get(field)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if field_differs_from_parent(candidate, parent, field, positives_df):
            if field in TOLERATED_EXTRA_FIELDS:
                tolerated_diffs.append((field, val))
                continue
            fails.append(("consistency", field, val, parent.get(field)))
    if TOLERATED_MAX_EXTRA is not None and len(tolerated_diffs) > TOLERATED_MAX_EXTRA:
        fails.extend(("consistency", f_, v_, parent.get(f_)) for f_, v_ in tolerated_diffs)
    # For anchor fields, predicate_satisfied is the authoritative test -- it
    # already encodes exactly what counts as a valid failing value. Do NOT
    # also require field_differs_from_parent here: that empirical-tolerance
    # check exists for the generic consistency check above (no predicate to
    # test against there), but for anchors it actively misfires whenever a
    # bucket's threshold sits close to the parent's own value -- e.g. a
    # "time_h > 48" bucket whose parent's own time_h IS 48: a candidate of
    # 49 genuinely satisfies "> 48" but was being rejected as "not different
    # enough" from 48 by the noise-tolerance check.
    # bucket_logic decides how multiple anchors combine. This was previously
    # ignored entirely -- every anchor was required regardless of the label,
    # which silently treated every multi-anchor 'single' bucket (any ONE
    # anchor alone is a complete correct answer, e.g. acs.cgd.9b00759_B1's
    # metal/modulator/solvent list of independently-sufficient failures) as
    # if it were 'all_required'.
    results = [(f, anchor_satisfied(candidate, parent, f)) for _, f in anchors.iterrows()]
    if bucket_logic == "single":
        if not any(ok for _, ok in results):
            fails.append(("anchor(any)", "/".join(anchors["field_name"]),
                          candidate.get(results[0][0]["field_name"]), _predicate_str(results[0][0])))
    elif str(bucket_logic).startswith("at_least_"):
        # "at_least_K": the row must satisfy at least K of this window's anchors (2026-10-08, c8tc04442b_B1: the paper changed
        # three parameters together, and a row that reproduces any two of them counts). Existing windows never use this value.
        k = int(str(bucket_logic).split("_")[-1])
        if sum(1 for _, ok in results if ok) < k:
            for f, ok in results:
                if not ok:
                    fails.append(("anchor(>=%d)" % k, f["field_name"], candidate.get(f["field_name"]), _predicate_str(f)))
    else:
        for f, ok in results:
            if not ok:
                fails.append(("anchor", f["field_name"], candidate.get(f["field_name"]), _predicate_str(f)))
    return fails


_POS_BY_DOI_CACHE = {}


def _positives_of(positives_df, doi):
    key = (id(positives_df), len(positives_df))
    if key not in _POS_BY_DOI_CACHE:
        _POS_BY_DOI_CACHE.clear()
        _POS_BY_DOI_CACHE[key] = {d: [r.to_dict() for _, r in g.iterrows()] for d, g in positives_df.groupby("doi")}
    return _POS_BY_DOI_CACHE[key].get(doi, [])


def _explain(candidate, parent, anchors, positives_df, bucket_logic):
    """Closest-parent rule (2026-10-02). The base-recipe consistency check used to demand that the candidate
    match THIS window's parent on every non-anchor field. Now, if the anchors are satisfied and the ONLY failures are
    consistency drift, the candidate still fits when this window's parent is the closest success recipe of the paper (fewest
    consistency differences) or tied for closest. A candidate that is closer to a different recipe still fails, so it cannot slide
    into a window whose parent is not its real base. Simulation: xhigh 206 -> 213 of 244 exact windows, success-recipe leaks
    unchanged at 8, reviewer-N leaks 8 -> 11."""
    fails = _explain_vs_parent(candidate, parent, anchors, positives_df, bucket_logic)
    if "strict_parent_consistency" in anchors and anchors["strict_parent_consistency"].any():
        return fails
    if not fails or any(f[0] != "consistency" for f in fails):
        return fails
    n = len(fails)
    for q in _positives_of(positives_df, candidate.get("doi")):
        if q.get("success_index") == parent.get("success_index"):
            continue
        nq = sum(1 for f in _explain_vs_parent(candidate, q, anchors, positives_df, bucket_logic) if f[0] == "consistency")
        if nq < n:
            return fails
    return []


def _predicate_str(f):
    if pd.notna(f["predicate_categorical"]):
        return f["predicate_categorical"]
    return f"{f['predicate_type']} {f['predicate_value_1']}..{f['predicate_value_2']}"


def candidate_satisfies_bucket(candidate: dict, parent: dict, bucket_field_rows: pd.DataFrame,
                               positives_df: pd.DataFrame, bucket_logic: str = "all_required") -> bool | None:
    fails = explain_candidate(candidate, parent, bucket_field_rows, positives_df, bucket_logic)
    return None if fails is None else not fails

# ---------------- Slot matching ----------------
# A bucket with expected_records=N is expanded into N identical "slots" (any
# candidate that satisfies the bucket satisfies every slot of it equally) --
# this turns "N distinct candidates required" into a standard 1-candidate-per-
# slot matching problem, so a single candidate can never be double-counted
# across multiple buckets. Solved with Kuhn's algorithm (augmenting-path search
# over a compatibility graph).

def build_slots(buckets_df: pd.DataFrame, positives_df: pd.DataFrame, bucket_fields_df: pd.DataFrame, doi: str):
    """One 'slot' per expected_records unit of every bucket for this paper.
    Slots from an un-scoreable bucket (broken parent / unparsed_freetext) are
    marked as such and excluded from matching, not silently dropped."""
    slots = []
    for _, b in buckets_df[buckets_df["doi"] == doi].iterrows():
        if b.get("scoring_status", "scored") == "optional":
            continue  # modulator-amount-only windows: documented but never scored
        parent = resolve_bucket_parent(b, positives_df)
        bf = bucket_fields_df[bucket_fields_df["bucket_id"] == b["bucket_id"]]
        n = int(b.get("expected_records", 1) or 1)
        bucket_logic = b.get("bucket_logic", "all_required")
        if parent is None:
            slots.append({"bucket_id": b["bucket_id"], "slot": 0, "scoreable": False,
                          "reason": "parent has no confirmed Positive Record"})
            continue
        scoreability_probe = candidate_satisfies_bucket({}, parent, bf, positives_df, bucket_logic)
        if scoreability_probe is None:
            slots.append({"bucket_id": b["bucket_id"], "slot": 0, "scoreable": False,
                          "reason": "unparsed_freetext anchor"})
            continue
        for i in range(n):
            slots.append({"bucket_id": b["bucket_id"], "slot": i, "scoreable": True,
                          "parent": parent, "fields": bf, "bucket_logic": bucket_logic})
    return slots


# Common abbreviations/formulas -> the same key as the full name, for dedup only.
_SYNONYMS = {
    "hcl": "hydrochloricacid", "concentratedhydrochloricacid": "hydrochloricacid", "conchcl": "hydrochloricacid",
    "acoh": "aceticacid", "ach": "aceticacid", "hac": "aceticacid", "glacialaceticacid": "aceticacid",
    "hcooh": "formicacid", "tfa": "trifluoroaceticacid", "hno3": "nitricacid", "naoh": "sodiumhydroxide",
    "dmf": "nndimethylformamide", "def": "nndiethylformamide", "dbf": "nndinbutylformamide",
    "h2o": "water", "deionizedwater": "water", "meoh": "methanol", "etoh": "ethanol",
}


def _canonical(v):
    if _blank(v):
        return None
    try:
        return float(f"{float(v):.6g}")
    except (TypeError, ValueError):
        k = norm_loose(v)
        return _SYNONYMS.get(k, k)


def kuhns_max_matching(compat: dict):
    """compat: {slot_idx: set(candidate_idx that fit)}. Returns {slot_idx: candidate_idx}
    maximizing the number of matched slots, each candidate used at most once."""
    match_for_candidate = {}

    def try_assign(slot, seen):
        for cand in compat.get(slot, ()):
            if cand in seen:
                continue
            seen.add(cand)
            if cand not in match_for_candidate or try_assign(match_for_candidate[cand], seen):
                match_for_candidate[cand] = slot
                return True
        return False

    for slot in compat:
        try_assign(slot, set())

    return {slot: cand for cand, slot in match_for_candidate.items()}


def score_paper(candidates: list, doi: str, positives_df: pd.DataFrame,
                buckets_df: pd.DataFrame, bucket_fields_df: pd.DataFrame):
    slots = build_slots(buckets_df, positives_df, bucket_fields_df, doi)
    scoreable_slots = [s for s in slots if s["scoreable"]]
    unscoreable_slots = [s for s in slots if not s["scoreable"]]

    # Compatibility is computed PER BUCKET (not per slot) first, then
    # deduplicated by the candidate's actual anchor-field value signature --
    # two candidates proposing the SAME value (e.g. both "100 uL") represent
    # the same real-world claim, not two distinct pieces of evidence, so only
    # one of them may ever fill a slot for that bucket. All slots of the same
    # bucket then share this identical deduplicated candidate pool.
    # The signature (fixed 2026-09-28) uses canonical values -- "HCl" and
    # "hydrochloric acid", or 2.9 umol and 0.0029 mmol, are the same claim --
    # and includes the base recipe the row was built on: two otherwise
    # identical rows for DIFFERENT compounds (anie.202421132's compound 1 and
    # 2, both with Na2WO4 removed) are two separate pieces of evidence, and
    # collapsing them let only one of the two compounds' windows be filled.
    reps_by_bucket = {}
    for bid in {s["bucket_id"] for s in scoreable_slots}:
        b_slot = next(s for s in scoreable_slots if s["bucket_id"] == bid)
        anchor_rows = b_slot["fields"][b_slot["fields"]["field_role"] == "anchor"]
        anchor_fields = [(fr["field_name"], fr) for _, fr in anchor_rows.iterrows()]
        seen_sigs = {}
        for ci, cand in enumerate(candidates):
            if not candidate_satisfies_bucket(cand, b_slot["parent"], b_slot["fields"], positives_df,
                                              b_slot["bucket_logic"]):
                continue
            anchors_df = b_slot["fields"][b_slot["fields"]["field_role"] == "anchor"]
            aligned = cand if not _explain(cand, b_slot["parent"], anchors_df, positives_df, b_slot["bucket_logic"]) \
                else align_slots(cand, b_slot["parent"])
            sig = (cand.get("based_on_success_index"),) + tuple(
                _canonical(_effective_anchor_value(aligned, b_slot["parent"], f, fr)) for f, fr in anchor_fields)
            if all(fr["predicate_type"] == "exclusion" for _, fr in anchor_fields):
                # An exclusion anchor ("no iron salt") reads the same value (blank) on every row that satisfies it, so all such
                # rows collapsed to one signature and starved the sibling windows sharing them (ejic.201500431_B5/B6, 2026-09-29).
                # What distinguishes the rows is the reagent they substitute, so their identities join the signature.
                sig += tuple(_canonical(aligned.get(sl)) for slots in SLOT_SYSTEMS.values() for sl in slots)
            seen_sigs.setdefault(sig, ci)  # keep only the FIRST candidate per distinct value signature
        reps_by_bucket[bid] = set(seen_sigs.values())

    compat = {si: reps_by_bucket[s["bucket_id"]] for si, s in enumerate(scoreable_slots)}

    matching = kuhns_max_matching(compat)  # {slot_index: candidate_index}

    per_bucket_hits = {}
    for si, s in enumerate(scoreable_slots):
        per_bucket_hits.setdefault(s["bucket_id"], []).append(si in matching)

    used_candidates = set(matching.values())
    unmatched_candidates = [ci for ci in range(len(candidates)) if ci not in used_candidates]

    report = {}
    for bid, hits in per_bucket_hits.items():
        report[bid] = {"expected": len(hits), "filled": sum(hits), "exact": all(hits)}
    for s in unscoreable_slots:
        report.setdefault(s["bucket_id"], {"expected": None, "filled": None, "exact": None,
                                           "unscoreable_reason": s["reason"]})
    return report, unmatched_candidates

# ---------------- SingleSlot layout ----------------
# Every SingleSlot window holds exactly one negative record (expected_records = 1), so every row of the
# SingleSlot sheet is one place a negative row can go. Windows cut from one older multi-record window share
# a link_group:
#   - closed group (more_allowed False): N interchangeable windows with the same rules. Each needs its own
#     distinct fitting row, exactly as the older N-record window did.
#   - open group (more_allowed True: one side of an OR window, a one-sided threshold, or an 'other X' rule):
#     the whole group is found when at least one distinct fitting row is found, and every distinct fitting
#     row counts (group_fits), also past the group's row count.
# The parent consistency check, the same-value dedup and the matching are score_paper's, unchanged; an open
# group enters the matching as one slot (its first window). strict=True scores every window as its own slot
# (no open-group rule).
#
# Amount units: the matcher compares an amount it cannot convert (mol vs g) as the raw number. Where a
# paper's SingleSlot rules hold an amount in grams and miner rows write it in moles, GRAMS_PER_MOL turns the
# rows' moles into grams first (to_rule_units). Use to_rule_units for any other check of a row against
# SingleSlot windows (e.g. whether a row fits a window).

# (doi, slot) -> g/mol of the reagent in that slot, for papers whose SingleSlot amount rules are in grams
GRAMS_PER_MOL = {("10.1021/cg700979r", "metal_1"): 308.48}   # Cd(NO3)2·4H2O; every parent 0.308 g = 1.0 mmol
_MMOL_PER = {"mol": 1000.0, "mmol": 1.0, "umol": 1e-3, "µmol": 1e-3, "μmol": 1e-3}


def to_rule_units(candidate: dict) -> dict:
    """The candidate with mole amounts turned into grams where its paper's SingleSlot rules are in grams."""
    c = dict(candidate)
    for (doi, slot), mw in GRAMS_PER_MOL.items():
        if c.get("doi") != doi:
            continue
        per = _MMOL_PER.get(str(c.get(f"{slot}_amount_unit") or "").strip().lower())
        try:
            v = float(c.get(f"{slot}_amount_value"))
        except (TypeError, ValueError):
            continue
        if per is None or pd.isna(v):
            continue
        c[f"{slot}_amount_value"], c[f"{slot}_amount_unit"] = round(v * per * mw / 1000.0, 6), "g"
    return c


def _is_open(b):
    return b["more_allowed"].fillna(False).astype(bool)


def score_paper_singleslot(candidates: list, doi: str, positives_df: pd.DataFrame,
                           buckets_ss: pd.DataFrame, fields_ss: pd.DataFrame, strict: bool = False):
    """Returns ({window_id: dict(expected, filled, exact, link_group, more_allowed, group_found, group_fits)},
    unmatched candidate indices). Optional windows are left out, as in score_paper."""
    candidates = [to_rule_units(c) for c in candidates]
    b = buckets_ss[buckets_ss["doi"] == doi]
    open_b = b[_is_open(b) & b["link_group"].notna()] if not strict else b.iloc[0:0]
    reps = open_b.groupby("link_group", sort=False)["bucket_id"].first()
    others = set(open_b["bucket_id"]) - set(reps)
    report, unmatched = score_paper(candidates, doi, positives_df, b[~b["bucket_id"].isin(others)], fields_ss)

    out = {}
    group_of = dict(zip(b["bucket_id"], b["link_group"]))
    rep_ids = set(reps)
    for bid, r in report.items():
        if bid in rep_ids:
            continue
        out[bid] = dict(r, link_group=group_of.get(bid), more_allowed=False, group_found=None, group_fits=None)
    for g, rep in reps.items():
        r = report.get(rep)
        members = list(open_b.loc[open_b["link_group"] == g, "bucket_id"])
        if r is None:  # optional window: not scored
            continue
        if r.get("expected") is None:  # unscoreable: every member says so
            for bid in members:
                out[bid] = dict(r, link_group=g, more_allowed=True, group_found=None, group_fits=None)
            continue
        found = bool(r["filled"])
        # distinct fitting rows: the same matcher, with room in the group's first window for every candidate
        probe = b[b["bucket_id"] == rep].assign(expected_records=max(1, len(candidates)))
        fits = score_paper(candidates, doi, positives_df, probe, fields_ss)[0].get(rep, {}).get("filled", 0) or 0
        for bid in members:
            out[bid] = dict(expected=1, filled=int(found), exact=found, link_group=g, more_allowed=True,
                            group_found=found, group_fits=int(fits))
    return out, unmatched

# The steps below call the matcher as matching.<name>, as in the package.
matching = SimpleNamespace(**globals())

from pathlib import Path
import re

import pandas as pd


SHEET_NAME = "SingleSlot GT"
ROW_TYPES = ("PAPER", "POSITIVE", "POSITIVE_OTHER", "NEGATIVE")
SCORING_STATUSES = ("scored", "optional")
SLOT_FIELDS = ("metal_1", "metal_2", "metal_3", "linker_1", "linker_2", "linker_3", "modulator_1", "modulator_2")
SOLVENT_FIELDS = ("solvent_main", "solvent_secondary")
# Window-parent columns: every field the matcher and the scorer read from a parent record. The *_text
# columns stay blank; a model row's own texts still pass through the matcher as before.
PARENT_COLUMNS = (
    ("doi", "mof_name", "success_index")
    + tuple(f"{slot}{part}" for slot in SLOT_FIELDS
            for part in ("", "_abbr", "_amount_text", "_amount_value", "_amount_unit"))
    + tuple(f"{solvent}{part}" for solvent in SOLVENT_FIELDS for part in ("", "_abbr", "_amount_text", "_ml"))
    + ("temperature_c", "temperature_c_text", "time_h", "time_text")
)
WINDOW_COLUMNS = ("bucket_id", "doi", "mof_name", "bucket_logic", "based_on_success_index", "expected_records",
                  "scoring_status", "legacy_window_id", "link_group", "rows_in_group", "more_allowed", "label")
RULE_COLUMNS = ("bucket_id", "field_name", "field_role", "predicate_type", "predicate_value_1", "predicate_value_2",
                "predicate_categorical")
# Sheet columns read for each row type.
SHEET_COLUMNS = ("label", "row_type", "mof_name", "link_group", "rows_in_group", "more_allowed", "paper_id", "doi",
                    "window_logic", "window_id", "legacy_window_id", "success_index", "scoring_status",
                    "scoring_rules", "scoring_recipe")
LOGIC_WORDS = {"all changes": "all_required", "one change": "single", "any one change": "single",
               "one change (either modulator field)": "single"}
_AT_LEAST_WORDS = re.compile(r"at least (\d+) changes?")
_RULE_FORMS = (  # tried in this order; the field name never holds a space
    ("range", re.compile(r"(\S+) from (\S+) to (\S+)")),
    ("gt", re.compile(r"(\S+) > (\S+)")),
    ("lt", re.compile(r"(\S+) < (\S+)")),
    ("exclusion", re.compile(r"(\S+) is not (.+)")),
    ("discrete_set", re.compile(r"(\S+) one of: (.+)")),
    ("categorical_equals", re.compile(r"(\S+) = (.+)")),
)
_RECIPE_LINE = re.compile(r"([a-z0-9_]+): (.*)")


def format_number(value):
    """A number as the shortest text that reads back to the same float: 60, 0.438, 1e-05."""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def _number_or_text(text):
    try:
        return float(text)
    except ValueError:
        return text


def _blank_cell(value):
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _one_line(value):
    """A value on one line of a scoring cell: a line break inside it is written as \\n."""
    return str(value).replace("\r\n", "\n").replace("\n", "\\n")


def _from_line(text):
    return text.replace("\\n", "\n")


def _value_text(value):
    """A recipe value: numbers (also numbers kept as text) in the shortest form, other text as it is."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return format_number(value)
    number = _number_or_text(str(value).strip())
    return format_number(number) if isinstance(number, float) else str(value)


def format_rules(rules):
    """The scoring_rules cell of one window: one rule per line, from its window_rules rows."""
    lines = []
    for rule in rules.to_dict("records") if isinstance(rules, pd.DataFrame) else rules:
        field, kind = rule["field_name"], rule["predicate_type"]
        if kind == "range":
            lines.append(f"{field} from {format_number(rule['predicate_value_1'])} to "
                         f"{format_number(rule['predicate_value_2'])}")
        elif kind in ("gt", "lt"):
            lines.append(f"{field} {'>' if kind == 'gt' else '<'} {format_number(rule['predicate_value_1'])}")
        elif kind == "exclusion":
            lines.append(f"{field} is not {_one_line(rule['predicate_categorical'])}")
        elif kind == "discrete_set":
            lines.append(f"{field} one of: {_one_line(rule['predicate_categorical'])}")
        elif kind == "categorical_equals":
            lines.append(f"{field} = {_one_line(rule['predicate_categorical'])}")
        else:
            raise ValueError(f"No scoring_rules form for the rule type {kind!r} ({field}).")
    return "\n".join(lines)


def parse_rules(text, window_id=None):
    """window_rules rows from a scoring_rules cell (see format_rules)."""
    rules = []
    for line in str(text).replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        for kind, form in _RULE_FORMS:
            match = form.fullmatch(line.rstrip("\r"))
            if not match:
                continue
            rule = {"bucket_id": window_id, "field_name": match.group(1), "field_role": "anchor",
                    "predicate_type": kind, "predicate_value_1": None, "predicate_value_2": None,
                    "predicate_categorical": None}
            if kind in ("range", "gt", "lt"):
                try:
                    values = [float(value) for value in match.groups()[1:]]
                except ValueError:
                    continue  # not a number: try the remaining forms
                rule["predicate_value_1"] = values[0]
                if kind == "range":
                    rule["predicate_value_2"] = values[1]
            else:
                rule["predicate_categorical"] = _from_line(match.group(2))
            rules.append(rule)
            break
        else:
            raise ValueError(f"{window_id or 'A window'}: cannot read the rule {line!r}. Use 'field > 150', "
                             f"'field < 2', 'field from 70 to 90', 'field = name', 'field is not name' or "
                             f"'field one of: a ||| b'.")
    if not rules:
        raise ValueError(f"{window_id or 'A window'} has no scoring rules.")
    return rules


def format_recipe(parent):
    """The scoring_recipe cell of one parent record: the matcher's fields, one 'field: value' per line."""
    lines = []

    def add(field, value):
        lines.append(f"{field}: {_one_line(value)}")

    for slot in SLOT_FIELDS:
        for suffix in ("", "_abbr"):
            if not _blank_cell(parent.get(slot + suffix)):
                add(slot + suffix, parent[slot + suffix])
        value, unit = parent.get(f"{slot}_amount_value"), parent.get(f"{slot}_amount_unit")
        if not _blank_cell(value):
            text = _value_text(value)
            if isinstance(_number_or_text(text), float):
                add(f"{slot}_amount", text + ("" if _blank_cell(unit) else f" {unit}"))
            else:  # an amount that is not a number keeps its own line, so the unit stays apart
                add(f"{slot}_amount_value", text)
                if not _blank_cell(unit):
                    add(f"{slot}_amount_unit", unit)
        elif not _blank_cell(unit):
            add(f"{slot}_amount_unit", unit)
    for solvent in SOLVENT_FIELDS:
        for suffix in ("", "_abbr"):
            if not _blank_cell(parent.get(solvent + suffix)):
                add(solvent + suffix, parent[solvent + suffix])
        if not _blank_cell(parent.get(f"{solvent}_ml")):
            add(f"{solvent}_ml", _value_text(parent[f"{solvent}_ml"]))
    for field in ("temperature_c", "time_h"):
        if not _blank_cell(parent.get(field)):
            add(field, _value_text(parent[field]))
    return "\n".join(lines)


_RECIPE_KEYS = (
    {f"{slot}{suffix}" for slot in SLOT_FIELDS for suffix in ("", "_abbr", "_amount", "_amount_value", "_amount_unit")}
    | {f"{solvent}{suffix}" for solvent in SOLVENT_FIELDS for suffix in ("", "_abbr", "_ml")}
    | {"temperature_c", "time_h"}
)


def parse_recipe(text, label=None):
    """The parent fields of a scoring_recipe cell (see format_recipe)."""
    parent = {}
    for line in str(text).replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        match = _RECIPE_LINE.fullmatch(line.rstrip("\r"))
        if not match or match.group(1) not in _RECIPE_KEYS:
            raise ValueError(f"{label or 'A positive row'}: cannot read the recipe line {line!r}; "
                             f"write 'field: value' with a field such as metal_1, metal_1_abbr, metal_1_amount, "
                             f"solvent_main_ml, temperature_c or time_h.")
        key, value = match.group(1), _from_line(match.group(2))
        if key.endswith("_amount"):
            number, _, unit = value.partition(" ")
            parent[key + "_value"] = float(number)
            if unit.strip():
                parent[key + "_unit"] = unit.strip()
        elif key.endswith(("_amount_value", "_ml")) or key in ("temperature_c", "time_h"):
            parent[key] = _number_or_text(value)
        else:
            parent[key] = value
    return parent


def read_sheet(path):
    """The SingleSlot GT sheet as text, blank cells as empty strings, from a workbook or a CSV."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing negative ground truth: {path}.")
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, header=None, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        with pd.ExcelFile(path) as book:
            sheet = SHEET_NAME if SHEET_NAME in book.sheet_names else book.sheet_names[0]
            raw = pd.read_excel(book, sheet_name=sheet, header=None, dtype=str).fillna("")
    for number in range(min(5, len(raw))):  # the column names are on the row that has label and row_type
        names = [str(value).strip() for value in raw.iloc[number]]
        if "label" in names and "row_type" in names:
            frame = raw.iloc[number + 1:].copy()
            frame.columns = names
            break
    else:
        raise ValueError(f"{path.name}: no row with the column names label and row_type in the first five rows.")
    missing = [column for column in SHEET_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"{path.name} lacks the columns {missing}.")
    frame = frame.loc[:, ~frame.columns.duplicated()].reset_index(drop=True)
    for column in frame:
        frame[column] = frame[column].astype(str).str.replace("\r\n", "\n")
    frame["sheet_row"] = range(number + 2, number + 2 + len(frame))  # spreadsheet row number, for messages
    return frame


def _logic(words, window_id):
    words = str(words).strip().lower()
    match = _AT_LEAST_WORDS.fullmatch(words)
    if match:
        return f"at_least_{match.group(1)}"
    if words in LOGIC_WORDS:
        return LOGIC_WORDS[words]
    raise ValueError(f"{window_id}: window_logic {words!r} is not one of {sorted(LOGIC_WORDS)} or 'at least N changes'.")


def _index(text, label):
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{label}: success_index {text!r} is not a number.") from None
    if number != int(number):
        raise ValueError(f"{label}: success_index {text!r} is not a whole number.")
    return int(number)


def tables_from_sheet(path):
    """Read the sheet and return ({doi: paper_id}, {"windows", "window_rules", "window_parents"}).

    Raises ValueError, naming the sheet row, for a row the scorer cannot read.
    """
    sheet = path.copy() if isinstance(path, pd.DataFrame) else read_sheet(path)
    text = {column: sheet[column].str.strip() for column in sheet if column != "sheet_row"}
    kind = text["row_type"]
    unknown = sheet[(kind != "") & ~kind.isin(ROW_TYPES)]
    if len(unknown):
        raise ValueError(f"Rows {list(unknown['sheet_row'][:10])} have a row_type outside {list(ROW_TYPES)}.")

    paper_rows = sheet[kind == "PAPER"]
    papers = {}
    for row in paper_rows.to_dict("records"):
        doi, paper_id = row["doi"].strip(), row["paper_id"].strip()
        if not doi or not paper_id:
            raise ValueError(f"Row {row['sheet_row']}: a PAPER row needs paper_id and doi.")
        if doi in papers:
            raise ValueError(f"Row {row['sheet_row']}: the paper {doi} is listed twice.")
        papers[doi] = paper_id

    parents = []
    for row in sheet[kind.isin(("POSITIVE", "POSITIVE_OTHER"))].to_dict("records"):
        label = f"Row {row['sheet_row']} ({row['label'].strip()})"
        parent = dict.fromkeys(PARENT_COLUMNS)
        parent.update(parse_recipe(row["scoring_recipe"], label))
        parent.update(doi=row["doi"].strip(), mof_name=row["mof_name"].strip() or None,
                      success_index=_index(row["success_index"].strip(), label))
        parents.append(parent)
    parents = pd.DataFrame(parents, columns=list(PARENT_COLUMNS))
    repeated = parents[parents.duplicated(["doi", "success_index"])]
    if len(repeated):
        raise ValueError("Positive records listed twice: "
                         + ", ".join(f"{d} #{i}" for d, i in zip(repeated["doi"], repeated["success_index"])) + ".")

    windows, rules = [], []
    known_parents = set(zip(parents["doi"], parents["success_index"]))
    for row in sheet[kind == "NEGATIVE"].to_dict("records"):
        window_id = row["window_id"].strip()
        label = f"Row {row['sheet_row']} ({row['label'].strip() or window_id})"
        if not window_id:
            raise ValueError(f"{label}: a NEGATIVE row needs a window_id.")
        status = row["scoring_status"].strip().lower()
        if status not in SCORING_STATUSES:
            raise ValueError(f"{label}: scoring_status must be one of {list(SCORING_STATUSES)}.")
        doi, index = row["doi"].strip(), _index(row["success_index"].strip(), label)
        if (doi, index) not in known_parents and status == "scored":  # an optional window without a parent never fits
            raise ValueError(f"{label}: no POSITIVE or POSITIVE_OTHER row for its parent {doi} #{index}.")
        more_allowed = row["more_allowed"].strip().lower()
        windows.append({
            "bucket_id": window_id, "doi": doi, "mof_name": row["mof_name"].strip() or None,
            "bucket_logic": _logic(row["window_logic"], window_id), "based_on_success_index": float(index),
            "expected_records": 1, "scoring_status": status,
            "legacy_window_id": row["legacy_window_id"].strip() or None,
            "link_group": row["link_group"].strip() or None,
            "rows_in_group": int(float(row["rows_in_group"])) if row["rows_in_group"].strip() else None,
            "more_allowed": more_allowed in ("yes", "true"), "label": row["label"].strip() or None})
        rules += parse_rules(row["scoring_rules"], window_id)
    windows = pd.DataFrame(windows, columns=list(WINDOW_COLUMNS))
    repeated = windows["bucket_id"][windows["bucket_id"].duplicated()]
    if len(repeated):
        raise ValueError(f"Windows listed twice: {sorted(set(repeated))[:10]}.")
    outside = sorted(set(windows["doi"]) - set(papers))
    if outside:
        raise ValueError(f"NEGATIVE rows on papers without a PAPER row: {outside[:10]}.")
    tables = {"windows": windows, "window_rules": pd.DataFrame(rules, columns=list(RULE_COLUMNS)),
              "window_parents": parents}
    return papers, tables

from collections import Counter
import math
import re

import pandas as pd


FIELD_CLASSES = ("metal", "linker", "modulator", "solvent", "temperature", "time")
# Prefixes of the record columns that make up each class; names and amounts count alike.
CLASS_PREFIXES = {
    "metal": ("metal_1", "metal_2", "metal_3"),
    "linker": ("linker_1", "linker_2", "linker_3"),
    "modulator": ("modulator_1", "modulator_2"),
    "solvent": ("solvent_main", "solvent_secondary"),
    "temperature": ("temperature_c",),
    "time": ("time_h", "time_text"),
}
# Fields whose only difference from the parent makes a row modulator-amount-only. The solvent volumes
# are included because they carry the modulator solution.
AMOUNT_ONLY_FIELDS = frozenset({"modulator_1_amount_value", "modulator_2_amount_value",
                                "solvent_main_ml", "solvent_secondary_ml"})
MODULATOR_AMOUNT_FIELDS = frozenset({"modulator_1_amount_value", "modulator_2_amount_value"})
ROW_OUTCOMES = ("TP", "FP", "TN")
_SPLIT = re.compile(r"[;,|]")


def field_class(field):
    """Parameter class of a record column, or None for columns outside the six classes."""
    field = str(field).strip()
    for name, prefixes in CLASS_PREFIXES.items():
        if any(field == prefix or field.startswith(prefix + "_") for prefix in prefixes):
            return name
    return None


def parse_varied_classes(value):
    """Return the classes named in a varied_classes cell and the tokens that name no class."""
    classes, unknown = set(), []
    for token in _SPLIT.split("" if value is None else str(value)):
        token = token.strip()
        if not token or token.lower() in ("nan", "none"):
            continue
        name = field_class(token)
        if name is None:
            unknown.append(token)
        else:
            classes.add(name)
    return classes, unknown


def window_change_classes(anchors, parent_satisfies):
    """Classes a window changes, and whether they came from the fallback.

    anchors is a list of (field, rule) pairs. An anchor the parent itself
    satisfies only fixes a value (or frees a field), so it changes nothing.
    When the parent satisfies every anchor, as in a few single-rule windows
    whose threshold sits next to the parent value, every anchor counts.
    """
    changed, every = set(), set()
    for field, rule in anchors:
        name = field_class(field)
        if name is None:
            continue
        every.add(name)
        if not parent_satisfies(field, rule):
            changed.add(name)
    if changed:
        return changed, False
    return every, bool(every)


def is_modulator_amount_only(differing_fields):
    """True when a row differs from its parent only in modulator amounts (and solvent volumes)."""
    differing = set(differing_fields)
    return bool(differing & MODULATOR_AMOUNT_FIELDS) and differing <= AMOUNT_ONLY_FIELDS


def row_outcomes(classes, fits, dropped=False):
    """Outcome of one row for each class: TP, FP, TN, or None when the row does not count."""
    if dropped:
        return {name: None for name in FIELD_CLASSES}
    outcomes = {}
    for name in FIELD_CLASSES:
        if name in classes:
            outcomes[name] = "TP" if fits else "FP"
        else:
            outcomes[name] = "TN" if fits else None
    return outcomes


def ratio(numerator, denominator):
    return numerator / denominator if denominator else math.nan


def f1(precision, recall):
    if math.isnan(precision) or math.isnan(recall) or precision + recall == 0:
        return math.nan
    return 2 * precision * recall / (precision + recall)


def field_table(rows, windows):
    """Field-level counts from scored rows and scored windows.

    rows needs the columns classes (set), fits (bool), and dropped (bool);
    windows needs classes (set), expected (int), and filled (int). The last
    line pools the rows and slots once each, without the per-class double
    counting, so it matches the row precision and slot recall of the window
    scorer.
    """
    records = []
    for name in FIELD_CLASSES:
        outcome = Counter(row_outcomes(r.classes, r.fits, r.dropped)[name] for r in rows.itertuples())
        own = windows.loc[windows["classes"].map(lambda classes: name in classes).astype(bool)]
        slots = int(own["expected"].sum())
        filled = int(own[["expected", "filled"]].min(axis=1).sum()) if len(own) else 0
        precision = ratio(outcome["TP"], outcome["TP"] + outcome["FP"])
        recall = ratio(filled, slots)
        records.append({
            "field": name, "rows_changing_field": outcome["TP"] + outcome["FP"],
            "TP_rows": outcome["TP"], "FP_rows": outcome["FP"], "TN_rows": outcome["TN"],
            "windows": len(own), "slots": slots, "TP_slots": filled, "FN_slots": slots - filled,
            "precision": precision, "recall": recall, "F1": f1(precision, recall)})
    counted = rows[~rows["dropped"]]
    fit = int(counted["fits"].sum())
    slots = int(windows["expected"].sum())
    filled = int(windows[["expected", "filled"]].min(axis=1).sum()) if len(windows) else 0
    precision, recall = ratio(fit, len(counted)), ratio(filled, slots)
    records.append({
        "field": "all rows and slots", "rows_changing_field": len(counted), "TP_rows": fit,
        "FP_rows": len(counted) - fit, "TN_rows": math.nan, "windows": len(windows), "slots": slots,
        "TP_slots": filled, "FN_slots": slots - filled, "precision": precision, "recall": recall,
        "F1": f1(precision, recall)})
    return pd.DataFrame(records)


def row_table(rows):
    """One line per row with its outcome for each class."""
    out = rows.copy()
    for name in FIELD_CLASSES:
        out[name] = [row_outcomes(r.classes, r.fits, r.dropped)[name] or "" for r in rows.itertuples()]
    out["classes"] = out["classes"].map(lambda classes: ";".join(c for c in FIELD_CLASSES if c in classes))
    return out


def window_table(windows):
    """One line per scored window with its change classes and one FN count per class."""
    out = windows.copy()
    unfilled = (out["expected"] - out[["expected", "filled"]].min(axis=1)).astype(int)
    for name in FIELD_CLASSES:
        out[f"FN_{name}"] = [count if name in classes else 0 for count, classes in zip(unfilled, out["classes"])]
    out["classes"] = out["classes"].map(lambda classes: ";".join(c for c in FIELD_CLASSES if c in classes))
    return out


def paper_table(rows, windows):
    """Per-paper TP, FP, and FN counts for each class."""
    records = {}
    for r in rows.itertuples():
        entry = records.setdefault(r.doi, Counter())
        for name, outcome in row_outcomes(r.classes, r.fits, r.dropped).items():
            if outcome in ("TP", "FP"):
                entry[f"{outcome}_rows_{name}"] += 1
    for w in windows.itertuples():
        entry = records.setdefault(w.doi, Counter())
        for name in w.classes:
            entry[f"slots_{name}"] += int(w.expected)
            entry[f"FN_slots_{name}"] += int(w.expected) - min(int(w.expected), int(w.filled))
    columns = [f"{kind}_{name}" for name in FIELD_CLASSES
               for kind in ("TP_rows", "FP_rows", "slots", "FN_slots")]
    table = pd.DataFrame([{"doi": doi, **{column: counts.get(column, 0) for column in columns}}
                          for doi, counts in sorted(records.items())], columns=["doi", *columns])
    return table

import csv
import math
from pathlib import Path
import re

import pandas as pd


WINDOW_LAYOUTS = ("windows", "singleslot")


SINGLESLOT_RULES = ("open", "strict")


SINGLESLOT_COLUMNS = ("legacy_window_id", "link_group", "rows_in_group", "more_allowed")


NEGATIVE_COLUMNS = ("doi", "based_on_success_index", "varied_classes")


_NUMERIC = re.compile(r"(_amount_value|_ml|^temperature_c|^time_h|^based_on_success_index)$")


class SingleSlotMatching:
    """negative_window_matching with SingleSlot window filling.

    score_paper fills the windows with score_paper_singleslot, and a row is put into the rules'
    units (to_rule_units) before a fit check. Every other function is negative_window_matching's.
    """

    def __init__(self, strict=False):
        self.strict = strict

    def __getattr__(self, name):
        return getattr(matching, name)

    def score_paper(self, candidates, doi, positives_df, buckets_df, bucket_fields_df):
        return matching.score_paper_singleslot(candidates, doi, positives_df, buckets_df, bucket_fields_df,
                                               strict=self.strict)

    def candidate_satisfies_bucket(self, candidate, parent, bucket_field_rows, positives_df,
                                   bucket_logic="all_required"):
        return matching.candidate_satisfies_bucket(matching.to_rule_units(candidate), parent, bucket_field_rows,
                                                   positives_df, bucket_logic)


def window_matcher(window_layout="windows", singleslot_rule="open"):
    """The window matcher for a window layout: the matching module, or its SingleSlot form."""
    if window_layout not in WINDOW_LAYOUTS:
        raise ValueError(f"window_layout must be one of {list(WINDOW_LAYOUTS)}.")
    if window_layout == "windows":
        return matching
    if singleslot_rule not in SINGLESLOT_RULES:
        raise ValueError(f"singleslot_rule must be one of {list(SINGLESLOT_RULES)}.")
    return SingleSlotMatching(strict=singleslot_rule == "strict")


def read_rows(path):
    """Read a CSV of records as text with blank cells kept as empty strings."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing rows file: {path}.")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    frame.columns = [str(column).strip() for column in frame.columns]
    if "doi" in frame:
        frame["doi"] = frame["doi"].str.strip()
    return frame


def _candidate(row, fields):
    # The matcher expects None for blank cells and numbers in the numeric columns.
    out = {}
    for field in fields:
        value = row.get(field, "")
        if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == "":
            out[field] = None
        elif _NUMERIC.search(field):
            try:
                out[field] = float(value)
            except ValueError:
                out[field] = value
        else:
            out[field] = value
    return out


def _prediction_rows(entry, papers):
    negatives = read_rows(entry["negative_rows"])
    missing = [column for column in NEGATIVE_COLUMNS if column not in negatives]
    if missing:
        raise ValueError(f"{Path(entry['negative_rows']).name} lacks the columns {missing}.")
    report = {"negative_rows_read": len(negatives)}
    outside = ~negatives["doi"].isin(papers)
    report["negative_rows_outside_reference"] = int(outside.sum())
    negatives = negatives[~outside].reset_index(drop=True)
    positives = read_rows(entry["positive_rows"]) if entry.get("positive_rows") else pd.DataFrame(columns=["doi"])
    positives = positives[positives["doi"].isin(papers)].reset_index(drop=True)
    report.update(negative_rows_kept=len(negatives), papers_with_negative_rows=int(negatives["doi"].nunique()),
                  positive_rows_kept=len(positives))
    return negatives, positives, report


def score_rows(matcher, windows, negatives, positives, papers):
    """Fit every negative row to the windows of its paper and fill the scored windows.

    matcher is negative_window_matching or the result of window_matcher. Returns the row frame and
    the scored-window frame that field_table expects, plus checks. SingleSlot windows also carry
    legacy_window_id, link_group, more_allowed, and group_fits.
    """
    buckets, rules, parents = windows["windows"], windows["window_rules"], windows["window_parents"]
    fields = sorted(set(parents.columns) - {"doi"})
    compare = sorted(set(matcher.CONSISTENCY_CHECK_FIELDS) | MODULATOR_AMOUNT_FIELDS)
    by_paper, parent_of_window = {}, {}
    for bucket in buckets[buckets["doi"].isin(papers)].to_dict("records"):
        parent = matcher.resolve_bucket_parent(bucket, parents)
        if parent is not None:
            parent_of_window[bucket["bucket_id"]] = parent
            by_paper.setdefault(bucket["doi"], []).append(
                (bucket["bucket_id"], parent, rules[rules["bucket_id"] == bucket["bucket_id"]],
                 bucket.get("bucket_logic") or "all_required"))
    parent_of = {(row["doi"], _index_key(row["success_index"])): row
                 for row in parents.to_dict("records")}

    def candidate(row):
        return dict(_candidate(row, fields), doi=row["doi"],
                    based_on_success_index=_candidate(row, ["based_on_success_index"])["based_on_success_index"])

    def differing(cand):
        parent = parent_of.get((cand["doi"], _index_key(cand.get("based_on_success_index"))))
        if parent is None:
            return None
        out = set()
        for field in compare:
            value, base = matcher._canonical(cand.get(field)), matcher._canonical(parent.get(field))
            if field.endswith(("_amount_value", "_ml")) and value in (None, ""):
                continue  # a blank amount keeps the parent's value (matcher rule)
            if value != base:
                out.add(field)
        return out

    records, unknown = [], []
    for row in negatives.to_dict("records"):
        cand = candidate(row)
        hits = [bucket_id for bucket_id, parent, bucket_rules, logic in by_paper.get(row["doi"], [])
                if matcher.candidate_satisfies_bucket(cand, parent, bucket_rules, parents, logic) is True]
        classes, tokens = parse_varied_classes(row["varied_classes"])
        unknown += tokens
        diff = differing(cand)
        amount_only = diff is not None and is_modulator_amount_only(diff)
        records.append({"paper_id": papers[row["doi"]], "doi": row["doi"], "mof_name": row.get("mof_name", ""),
                        "based_on_success_index": row["based_on_success_index"],
                        "varied_classes": row["varied_classes"], "source_file": row.get("source_file", ""),
                        "classes": classes, "fits_windows": ";".join(hits), "fits": bool(hits),
                        "modulator_amount_only": amount_only, "dropped": amount_only and not hits})
    rows = pd.DataFrame(records, columns=["paper_id", "doi", "mof_name", "based_on_success_index", "varied_classes",
                                          "source_file", "classes", "fits_windows", "fits",
                                          "modulator_amount_only", "dropped"])

    singleslot = all(column in buckets for column in SINGLESLOT_COLUMNS)
    window_columns = ["window_id", "paper_id", "doi", "mof_name", "logic", "expected", "filled", "classes",
                      "class_source", "anchor_fields"]
    if singleslot:
        window_columns += ["legacy_window_id", "link_group", "more_allowed", "group_fits"]
    window_records, unscoreable = [], []
    meta = buckets.set_index("bucket_id")
    for doi in sorted(set(buckets["doi"]) & set(papers)):
        pool = [candidate(row) for row in positives[positives["doi"] == doi].to_dict("records")]
        pool += [candidate(row) for row in negatives[negatives["doi"] == doi].to_dict("records")]
        report, _ = matcher.score_paper(pool, doi, parents, buckets, rules)
        for bucket_id, result in report.items():
            if result.get("expected") is None:
                unscoreable.append({"window_id": bucket_id, "reason": result.get("unscoreable_reason", "")})
                continue
            bucket, parent = meta.loc[bucket_id], parent_of_window[bucket_id]
            anchors = rules[(rules["bucket_id"] == bucket_id) & (rules["field_role"] == "anchor")]
            classes, fallback = window_change_classes(
                [(rule["field_name"], rule) for _, rule in anchors.iterrows()],
                lambda field, rule: bool(matcher.anchor_satisfied(parent, parent, rule)))
            record = {
                "window_id": bucket_id, "paper_id": papers[doi], "doi": doi, "mof_name": bucket.get("mof_name", ""),
                "logic": bucket.get("bucket_logic", ""), "expected": int(result["expected"]),
                "filled": min(int(result["filled"]), int(result["expected"])), "classes": classes,
                "class_source": "fallback" if fallback else "rules failed by the parent",
                "anchor_fields": ";".join(anchors["field_name"])}
            if singleslot:
                record.update(legacy_window_id=bucket.get("legacy_window_id"), link_group=result.get("link_group"),
                              more_allowed=bool(result.get("more_allowed")), group_fits=result.get("group_fits"))
            window_records.append(record)
    scored = pd.DataFrame(window_records, columns=window_columns)
    in_scope = buckets[buckets["doi"].isin(papers)]
    checks = [
        ("windows on reference papers", len(in_scope), ""),
        ("scored windows", len(scored), ""),
        ("optional windows (rows may fit them; no slots)",
         int(in_scope["scoring_status"].eq("optional").sum()) if "scoring_status" in in_scope else 0, ""),
        ("scored windows that could not be scored", len(unscoreable),
         "; ".join(f"{item['window_id']} ({item['reason']})" for item in unscoreable)),
        ("scored windows whose classes come from the fallback", int(scored["class_source"].eq("fallback").sum()),
         "; ".join(scored.loc[scored["class_source"].eq("fallback"), "window_id"])),
        ("scored windows that change no class", int(scored["classes"].map(len).eq(0).sum()),
         "; ".join(scored.loc[scored["classes"].map(len).eq(0), "window_id"])),
        ("rows naming no class", int(rows["classes"].map(len).eq(0).sum()), ""),
        ("varied_classes tokens that name no class", len(unknown), "; ".join(sorted(set(unknown)))),
        ("rows whose parent is not among the window parents",
         sum(1 for row in negatives.to_dict("records")
             if (row["doi"], _index_key(row["based_on_success_index"])) not in parent_of), ""),
        ("rows on papers without windows", int((~rows["doi"].isin(set(buckets["doi"]))).sum()), ""),
        ("modulator-amount-only rows left out", int(rows["dropped"].sum()), ""),
    ]
    return rows, scored, pd.DataFrame(checks, columns=["check", "count", "detail"])


def _index_key(value):
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def evaluate_prediction(matcher, windows, papers, entry):
    """Score one prediction entry and return its tables."""
    negatives, positives, report = _prediction_rows(entry, papers)
    rows, scored, checks = score_rows(matcher, windows, negatives, positives, papers)
    return {"name": entry["name"], "report": report, "field_level": field_table(rows, scored),
            "rows": row_table(rows), "windows": window_table(scored), "papers": paper_table(rows, scored),
            "checks": checks}


def _save_csv(frame, path):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(frame.columns)
        for row in frame.itertuples(index=False, name=None):
            writer.writerow(["" if (value is None or isinstance(value, float) and not math.isfinite(value)) else
                             ("yes" if value is True else "no" if value is False else value) for value in row])
    return Path(path)


def _write_workbook(path, sheets):
    # Values only: strings that start with "=" are stored as text, never as formulas.
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, table in sheets:
        sheet = workbook.create_sheet(name)
        sheet.append([str(column) for column in table.columns])
        for row_number, row in enumerate(table.itertuples(index=False, name=None), 2):
            values = []
            for value in row:
                if hasattr(value, "item") and not isinstance(value, str):
                    value = value.item()
                if isinstance(value, bool):
                    value = "yes" if value else "no"
                elif isinstance(value, float) and not math.isfinite(value):
                    value = None
                elif isinstance(value, str):
                    value = ILLEGAL_CHARACTERS_RE.sub("", value)
                values.append(value)
            sheet.append(values)
            for column, value in enumerate(values, 1):
                if isinstance(value, str) and value.startswith("="):
                    sheet.cell(row=row_number, column=column).data_type = "s"
    workbook.save(path)
    return Path(path)



# Public reference loader, evaluation summaries, and CLI.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REFERENCE = REPO_ROOT / "benchmarks/negative_reconstruction/ground_truth.xlsx"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "results/negative_extraction"
SCHEMA_VERSION = "negative-evaluation-v5-reference-rows"
REFERENCE_METADATA_PREFIX = "MOFinder.NegativeReference."
REFERENCE_METADATA_SCHEMA = "negative-reference-embedded-v1"
REFERENCE_METADATA_ENCODING = "json+gzip+base64-v1"
SINGLE_SHEET_COLUMNS = ("paper_id", "window_id", "doi", "mof_name", "Negative condition",
                        "A1 contribution", "A2 contribution", "A3 contribution", "A4 contribution",
                        "Optional: comment by contributing annotator")
LEGACY_SINGLE_SHEET_COLUMNS = ("paper_id", "window_id", "doi", "mof_name", "scoring_rules", "A1", "A2", "A3", "A4")
NO_NEGATIVE_EVIDENCE = "No negative evidence annotated"
_VISIBLE_WINDOW_ID = re.compile(r"(?P<paper>N[0-9]{3,})-PR(?P<parent>[0-9]+)-.+")
_COMPACT_RULE_HEADER = re.compile(r"(?:(OPTIONAL) )?(ALL|ANY|AT_LEAST\(([1-9][0-9]*)\)):")
DETAIL_GROUPS = {
    "metal_name": tuple(f"metal_{i}" for i in range(1, 4)),
    "metal_amount": tuple(f"metal_{i}_amount_value" for i in range(1, 4)),
    "linker_name": tuple(f"linker_{i}" for i in range(1, 4)),
    "linker_amount": tuple(f"linker_{i}_amount_value" for i in range(1, 4)),
    "modulator_name": ("modulator_1", "modulator_2"),
    "modulator_amount": ("modulator_1_amount_value", "modulator_2_amount_value"),
    "solvent_name": ("solvent_main", "solvent_secondary"),
    "solvent_amount": ("solvent_main_ml", "solvent_secondary_ml"),
    "temperature_c": ("temperature_c",),
    "time_h": ("time_h",),
}
DEFINITIONS = {
    "reference_row_metrics": "A fixed reference panel combines scored failure windows with distinct successful "
        "parent IDs associated with those windows. TP/FN retain the reference window coverage rules. A successful "
        "control profile is FP when any substantive negative output matches all of its known fields, otherwise TN. "
        "TN means the recorded successful-control profile was not emitted as negative; it does not establish "
        "independent positive extraction. Ingredient identities must agree within each role without extras. "
        "Known amounts are required within 5% after compatible unit conversion; temperature/time agree to numerical "
        "precision. Unknown reference numeric values remain unconstrained and are disclosed. Model parent/change "
        "labels and source row-exclusion flags are ignored for controls. Unsupported outputs outside this fixed "
        "panel remain in the separate output-row diagnostics. No control is filtered according to model output.",
    "reference_field_metrics": "Each field panel contains scored windows involving that field plus their distinct "
        "associated successful parent IDs with at least one known value in the field category. Failure TP/FN are "
        "window coverage, including OR-window coverage through other fields; control FP/TN use the whole known-field "
        "profile, not that field alone. Categories overlap. These are field-associated reference-case metrics, "
        "not exact-cell extraction accuracy.",
    "paper_detection": "Presence of at least one submitted negative row before protocol exclusions. "
        "Primary confusion uses scored-window papers as positive and papers with no windows as negative; "
        "optional-only papers are excluded. TP does not establish that a particular protocol is correct.",
    "paper_missed_protocols": "Papers with at least one unfilled scored window; can overlap paper TP.",
    "paper_recovery": "Among papers with scored windows, a paper is recovered when at least one scored "
        "window is fulfilled. The source window matcher checks annotated change constraints under its parent "
        "consistency rules; complete recovery of every window is not required. This content-supported paper "
        "recovery is separate from binary presence detection and is not an ordinary confusion matrix. Mean "
        "and median per-paper coverage use filled scored windows / scored windows for each eligible paper, "
        "giving each paper equal weight; no-window and optional-only papers are excluded from this denominator.",
    "parent_negative_coverage": "A paper meets the primary parent-coverage criterion when every positive "
        "parent synthesis with at least one scored negative reference window has at least one compatible "
        "negative prediction. Compatibility is mapped through the matched reference window's parent, never "
        "the model's claimed parent. Optional-only parents are excluded. One negative per eligible parent "
        "suffices; neither every associated negative window nor every recipe field must be recovered. "
        "Extra unsupported rows affect precision separately. Primary coverage uses maximum bipartite matching: "
        "each distinct predicted recipe can cover at most one eligible parent. Exact machine-field recipe "
        "duplicates are collapsed when predictions are supplied. Compatible-parent union coverage and "
        "single-parent-only evidence are separate sensitivities. Positive-assisted rows do not enter this metric.",
    "protocol_precision": "TP_rows / (TP_rows + FP_rows); a row is supported if it fits any scored or optional "
        "window. Source-policy unsupported modulator-amount-only rows are excluded and reported.",
    "protocol_recall": "TP_slots / (TP_slots + FN_slots); scored-window coverage. Under the open rule, "
        "one distinct row can fill every member of an open link group. Closed groups need distinct rows.",
    "protocol_F1": "Harmonic mean of row precision and window coverage recall; different observation units. "
        "This is not an ordinary binary-confusion F1. No finite universe of non-protocols defines TN or accuracy.",
    "field_metrics": "Original six change classes from the model's varied_classes and reference predicates. "
        "valid_rows_without_class counts supported rows without that declared change; it is conditional, not TN.",
    "field_detail_metrics": "Ten derived change-field categories, inferred by comparing each prediction with "
        "its declared parent using source identity/unit/tolerance rules. Missing parent means unknown and "
        "exclusion from detailed row denominators. Slot categories come from failed parent predicates, with "
        "the source fallback to all anchors when none fails. Recall is coverage of windows involving the field; "
        "an OR window can be recovered through a different field and still contribute coverage here. It does not "
        "establish that the field itself was correctly extracted. Categories overlap and are not summed for pooled metrics.",
    "source_matching": "Source calibration is preserved: blank numeric anchors inherit the parent; "
        "closest-parent consistency may accept other reported field differences; source name aliases, "
        "amount conversion, slot alignment, scale equivalence, and duplicate-anchor signatures are retained. "
        "Windows with explicit adjudication policies instead require reported numeric anchors and compatible "
        "amount units, use only documented cross-dimension conversions, and disable closest-parent drift "
        "and scale exemptions for the fixed parent loading. "
        "The chemically incorrect source H3BTB -> terephthalic-acid alias is corrected to "
        "1,3,5-tris(4-carboxyphenyl)benzene; the frozen original scorer is retained for historical regression.",
    "positive_assisted": "Only explicit --positive-csv enables positive rows to fill coverage slots; they never "
        "enter negative-row precision or paper detection. Assisted recall is not comparable to negative-only recall.",
    "coverage": "A CSV of emitted rows alone does not prove every paper was successfully processed. Missing "
        "rows are treated as no prediction for benchmark scoring; execution coverage is unverified. Explicit "
        "non-record/failed-status rows and rows without machine-readable recipe values are quarantined before scoring.",
}


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _harmonic(precision, recall):
    if precision is None or recall is None:
        return None
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalize_frame(frame):
    frame = frame.copy().fillna("")
    frame.columns = [str(c).strip() for c in frame.columns]
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Repeated column names are not allowed.")
    if "doi" in frame:
        frame["doi"] = frame["doi"].map(doi_key)
    return frame


def _validate_embedded_bundle(bundle):
    required = {"papers": list, "parent_context": list, "windows": dict, "linker_molecular_weights": dict}
    if not isinstance(bundle, dict) or not set(required).issubset(bundle):
        raise ValueError("Embedded negative metadata requires papers, parent_context, windows and linker_molecular_weights.")
    for key, expected in required.items():
        if not isinstance(bundle[key], expected):
            raise ValueError(f"Invalid embedded negative component: {key}.")
    for name, value in bundle["linker_molecular_weights"].items():
        if not isinstance(name, str) or not name.strip() or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Embedded linker molecular weights must map nonempty names to positive finite numbers.")


def embed_reference_rules(workbook, bundle):
    """Embed matching context in XLSX custom properties, without adding sheets."""
    _validate_embedded_bundle(bundle)
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded = base64.b64encode(gzip.compress(payload, mtime=0)).decode("ascii")
    chunks = [encoded[start:start + 255] for start in range(0, len(encoded), 255)]
    if not 1 <= len(chunks) <= 9999:
        raise ValueError("Embedded negative metadata exceeds the supported property count.")
    properties = workbook.custom_doc_props
    for name in list(properties.names):
        if name.startswith(REFERENCE_METADATA_PREFIX):
            del properties[name]
    metadata = {"Schema": REFERENCE_METADATA_SCHEMA, "Encoding": REFERENCE_METADATA_ENCODING,
                "ChunkCount": str(len(chunks)), "SHA256": hashlib.sha256(payload).hexdigest()}
    for name, value in metadata.items():
        properties.append(StringProperty(name=REFERENCE_METADATA_PREFIX + name, value=value))
    for index, chunk in enumerate(chunks, 1):
        properties.append(StringProperty(name=REFERENCE_METADATA_PREFIX + f"{index:04d}", value=chunk))
    return metadata


def read_embedded_reference_rules(workbook):
    """Read checksummed data only; never execute strings in a reference workbook."""
    properties = {prop.name.removeprefix(REFERENCE_METADATA_PREFIX): prop.value
                  for prop in workbook.custom_doc_props if prop.name.startswith(REFERENCE_METADATA_PREFIX)}
    if not properties:
        return None
    required = {"Schema", "Encoding", "ChunkCount", "SHA256"}
    if not required.issubset(properties):
        raise ValueError("Embedded negative metadata is incomplete.")
    if properties["Schema"] != REFERENCE_METADATA_SCHEMA or properties["Encoding"] != REFERENCE_METADATA_ENCODING:
        raise ValueError("Unsupported embedded negative metadata schema or encoding.")
    count = properties["ChunkCount"]
    if not isinstance(count, str) or not re.fullmatch(r"[1-9][0-9]{0,3}", count):
        raise ValueError("Invalid embedded negative metadata chunk count.")
    names = [f"{i:04d}" for i in range(1, int(count) + 1)]
    if set(properties) != required | set(names):
        raise ValueError("Embedded negative metadata chunks are missing or unexpected.")
    chunks = [properties[name] for name in names]
    if any(not isinstance(chunk, str) or not 1 <= len(chunk) <= 255 for chunk in chunks):
        raise ValueError("Invalid embedded negative metadata chunk.")
    try:
        payload = gzip.decompress(base64.b64decode("".join(chunks), validate=True))
    except (ValueError, binascii.Error, OSError, EOFError, zlib.error) as exc:
        raise ValueError("Embedded negative metadata is corrupt or truncated.") from exc
    if hashlib.sha256(payload).hexdigest() != properties["SHA256"]:
        raise ValueError("Embedded negative metadata checksum mismatch.")
    try:
        bundle = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Embedded negative metadata is not valid UTF-8 JSON.") from exc
    _validate_embedded_bundle(bundle)
    return bundle


def format_compact_rules(rules, logic="all_required", status="scored"):
    """Encode status and rule-combination logic in one readable executable cell."""
    if status not in ("scored", "optional"):
        raise ValueError("Rule status must be scored or optional.")
    if logic == "all_required":
        header = "ALL"
    elif logic == "single":
        header = "ANY"
    elif re.fullmatch(r"at_least_[1-9][0-9]*", str(logic)):
        header = f"AT_LEAST({str(logic).removeprefix('at_least_')})"
    else:
        raise ValueError(f"Unsupported rule logic {logic!r}.")
    return ("OPTIONAL " if status == "optional" else "") + header + ":\n" + str(rules).strip()


def parse_compact_rules(value, window_id):
    lines = str(value).replace("\r\n", "\n").split("\n")
    match = _COMPACT_RULE_HEADER.fullmatch(lines[0].strip())
    if not match or len(lines) < 2 or not "\n".join(lines[1:]).strip():
        raise ValueError(f"{window_id}: Negative condition needs ALL:, ANY: or AT_LEAST(K): followed by rules; OPTIONAL may prefix the header.")
    status = "optional" if match.group(1) else "scored"
    token = match.group(2)
    logic = "all changes" if token == "ALL" else "one change" if token == "ANY" else f"at least {match.group(3)} changes"
    return status, logic, "\n".join(lines[1:]).strip()


def _embedded_reference(path):
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return None
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        bundle = read_embedded_reference_rules(workbook)
        if bundle is None:
            return None
        visible = [sheet for sheet in workbook if sheet.sheet_state == "visible"]
        if len(visible) != 1:
            raise ValueError("An embedded negative reference must have exactly one visible worksheet.")
        raw = list(visible[0].iter_rows(values_only=True))
    finally:
        workbook.close()
    if not raw:
        raise ValueError("The visible negative reference sheet is empty.")
    columns = [str(value).strip() if value is not None else "" for value in raw[0]]
    if "Negative condition" in columns and "scoring_rules" in columns:
        raise ValueError("Use one condition column: Negative condition, or scoring_rules for the legacy format.")
    legacy = "scoring_rules" in columns
    display_columns = LEGACY_SINGLE_SHEET_COLUMNS if legacy else SINGLE_SHEET_COLUMNS
    condition_column = "scoring_rules" if legacy else "Negative condition"
    missing = set(display_columns) - set(columns)
    if missing:
        raise ValueError(f"Single-sheet negative reference lacks columns {sorted(missing)}.")
    sheet = _normalize_frame(pd.DataFrame(raw[1:], columns=columns))
    # Contribution flags and free comments are display metadata. Neither their
    # wording nor their values participate in any matching or score calculation.
    sheet = sheet[sheet[list(display_columns)].astype(str).apply(lambda col: col.str.strip()).ne("").any(axis=1)]
    manifest = {doi_key(row["doi"]): str(row["paper_id"]).strip() for row in bundle["papers"]}
    if len(manifest) != len(bundle["papers"]) or len(set(manifest.values())) != len(manifest):
        raise ValueError("Embedded paper manifest contains duplicate DOI or paper_id values.")
    if set(sheet["doi"]) != set(manifest):
        raise ValueError("Visible sheet and embedded paper manifest must cover the same publications.")
    rows = [{**dict.fromkeys(SHEET_COLUMNS, ""), "row_type": "PAPER", "doi": doi, "paper_id": paper_id}
            for doi, paper_id in manifest.items()]
    for context in bundle["parent_context"]:
        rows.append({**dict.fromkeys(SHEET_COLUMNS, ""), **context, "row_type": "POSITIVE"})
    seen, aliases = set(), {}
    for item in sheet.to_dict("records"):
        paper_id, doi = str(item["paper_id"]).strip(), item["doi"]
        if manifest.get(doi) != paper_id:
            raise ValueError(f"Visible DOI/paper_id mismatch for {doi}.")
        window_id = str(item["window_id"]).strip()
        if not window_id:
            if str(item[condition_column]).strip() != NO_NEGATIVE_EVIDENCE:
                raise ValueError(f"{paper_id}: a blank window_id requires '{NO_NEGATIVE_EVIDENCE}' in {condition_column}.")
            continue
        match = _VISIBLE_WINDOW_ID.fullmatch(window_id)
        if not match or match.group("paper") != paper_id or window_id in seen:
            raise ValueError(f"Invalid or repeated visible window_id: {window_id}.")
        seen.add(window_id)
        metadata = bundle["windows"].get(window_id)
        if not isinstance(metadata, dict):
            raise ValueError(f"{window_id}: missing embedded matching metadata.")
        index = int(match.group("parent"))
        if index != int(metadata["success_index"]):
            raise ValueError(f"{window_id}: encoded parent disagrees with embedded success_index.")
        status, logic, rules = parse_compact_rules(item[condition_column], window_id)
        more_allowed = metadata.get("more_allowed", False)
        if not isinstance(more_allowed, bool):
            raise ValueError(f"{window_id}: embedded more_allowed must be Boolean.")
        row = {**dict.fromkeys(SHEET_COLUMNS, ""), **item, "row_type": "NEGATIVE",
               "success_index": str(index), "scoring_status": status, "window_logic": logic,
               "scoring_rules": rules, "label": window_id,
               "legacy_window_id": metadata.get("legacy_window_id", ""),
               "link_group": metadata.get("link_group") or "",
               "rows_in_group": str(metadata.get("rows_in_group") or ""),
               "more_allowed": "yes" if more_allowed else "no"}
        rows.append(row)
        source_id = metadata.get("source_window_id")
        if source_id:
            if source_id in aliases:
                raise ValueError(f"Repeated source window alias: {source_id}.")
            aliases[str(source_id)] = window_id
    if seen != set(bundle["windows"]):
        raise ValueError("Visible windows and embedded window metadata must match exactly.")
    for item in sheet[sheet["window_id"].astype(str).str.strip().eq("")].to_dict("records"):
        if any(row["doi"] == item["doi"] and row["row_type"] == "NEGATIVE" for row in rows):
            raise ValueError(f"{item['paper_id']}: a no-evidence placeholder conflicts with negative windows.")
    frame = _normalize_frame(pd.DataFrame(rows))
    frame["sheet_row"] = range(2, 2 + len(frame))
    return {"frame": frame, "bundle": bundle, "window_id_aliases": aliases, "visible_sheet": sheet}


def _flat_reference(path):
    """Read the simplified three-table reference, retaining all parent context."""
    if path.suffix.lower() == ".csv":
        paths = {"ground_truth": path, **{name: path.with_name(name + ".csv")
                  for name in ("papers", "parent_context")}}
        tables = {name: _normalize_frame(pd.read_csv(p, dtype=str, keep_default_na=False,
                   encoding="utf-8-sig")) for name, p in paths.items()}
        companions = [p for p in paths.values() if p != path]
    else:
        with pd.ExcelFile(path) as book:
            if not {"ground_truth", "papers", "parent_context"}.issubset(book.sheet_names):
                return None, []
            tables = {name: _normalize_frame(pd.read_excel(book, sheet_name=name, dtype=str))
                      for name in ("ground_truth", "papers", "parent_context")}
        companions = []
    required = {
        "papers": ("paper_id", "doi"),
        "parent_context": ("doi", "success_index", "scoring_recipe"),
        "ground_truth": ("doi", "window_id", "success_index", "window_logic", "scoring_status",
                         "scoring_rules", "link_group", "more_allowed"),
    }
    rows = []
    for name, kind in (("papers", "PAPER"), ("parent_context", "POSITIVE"), ("ground_truth", "NEGATIVE")):
        missing = set(required[name]) - set(tables[name].columns)
        if missing:
            raise ValueError(f"{name}: missing columns {sorted(missing)}.")
        for row in tables[name].to_dict("records"):
            rows.append({**dict.fromkeys(SHEET_COLUMNS, ""), **row, "row_type": kind})
    frame = pd.DataFrame(rows)
    frame["sheet_row"] = range(2, 2 + len(frame))
    return frame, companions


def load_reference(path=DEFAULT_REFERENCE):
    """Load a simplified workbook/CSV bundle or the original SingleSlot GT workbook."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Missing negative reference: {path}")
    embedded = _embedded_reference(path)
    if embedded is not None:
        frame, companions = embedded["frame"], []
    else:
        frame, companions = _flat_reference(path)
    if frame is None:
        frame = _normalize_frame(read_sheet(path))
    for column in SHEET_COLUMNS:
        frame[column] = frame[column].astype(str).str.replace("\r\n", "\n")
    papers, tables = tables_from_sheet(frame)
    if embedded is not None:
        rule_frame = tables["window_rules"]
        rule_frame["required_unit"] = ""
        rule_frame["unit_conversions"] = [dict() for _ in range(len(rule_frame))]
        rule_frame["require_explicit_numeric_anchor"] = False
        rule_frame["strict_parent_consistency"] = False
        for window_id, metadata in embedded["bundle"]["windows"].items():
            units = metadata.get("rule_units", {})
            conversions = metadata.get("unit_conversions", {})
            explicit = metadata.get("require_explicit_numeric_anchors", False)
            strict = metadata.get("strict_parent_consistency", False)
            if not isinstance(units, dict) or not isinstance(conversions, dict) or not isinstance(explicit, bool) or not isinstance(strict, bool):
                raise ValueError(f"{window_id}: invalid strict matching policy metadata.")
            own = rule_frame["bucket_id"].eq(window_id)
            fields = set(rule_frame.loc[own, "field_name"])
            if set(units) - fields or set(conversions) - set(units):
                raise ValueError(f"{window_id}: unit policy must name explicit anchor fields with rule_units.")
            for field, unit in units.items():
                if not field.endswith("_amount_value") or parse_unit(unit) is None:
                    raise ValueError(f"{window_id}: explicit rule units require an amount-value anchor and a supported target unit.")
                bridges = conversions.get(field, {})
                if not isinstance(bridges, dict) or any(not isinstance(u, str) or not u.strip() or
                        not isinstance(factor, (int, float)) or not math.isfinite(factor) or factor <= 0
                        for u, factor in bridges.items()):
                    raise ValueError(f"{window_id}: unit conversion factors must be positive finite numbers.")
                for index in rule_frame.index[own & rule_frame["field_name"].eq(field)]:
                    rule_frame.at[index, "required_unit"] = unit
                    rule_frame.at[index, "unit_conversions"] = bridges
            rule_frame.loc[own, "require_explicit_numeric_anchor"] = explicit
            rule_frame.loc[own, "strict_parent_consistency"] = strict
    if not papers:
        raise ValueError("The paper manifest is empty.")
    if len(set(papers.values())) != len(papers):
        raise ValueError("paper_id values must be unique.")
    if any(not doi.startswith("10.") or "/" not in doi for doi in papers):
        raise ValueError("Every reference paper must have a DOI.")
    if set(tables["window_parents"]["doi"]) - set(papers):
        raise ValueError("Parent context contains papers outside the paper manifest.")
    windows, rules = tables["windows"], tables["window_rules"]
    if len(windows) == 0:
        raise ValueError("The reference has no negative constraints.")
    unknown_fields = set(rules["field_name"]) - set(PARENT_COLUMNS)
    if unknown_fields:
        raise ValueError(f"Rules name unsupported fields: {sorted(unknown_fields)}")
    for row in windows.itertuples():
        if row.more_allowed and not row.link_group:
            raise ValueError(f"{row.bucket_id}: an open window needs a link_group.")
        if row.bucket_logic.startswith("at_least_"):
            required = int(row.bucket_logic.removeprefix("at_least_"))
            anchor_count = len(rules[(rules["bucket_id"] == row.bucket_id) & rules["field_role"].eq("anchor")])
            if not 1 <= required <= anchor_count:
                raise ValueError(f"{row.bucket_id}: at least K changes requires 1 <= K <= {anchor_count} anchors.")
    # The inherited open-group algorithm uses the first member as representative.
    # Reject heterogeneous groups instead of silently scoring only one rule set.
    for (doi, group), members in windows[windows["link_group"].notna()].groupby(["doi", "link_group"]):
        if not members["more_allowed"].any():
            continue
        signatures = set()
        for row in members.to_dict("records"):
            own = rules[rules["bucket_id"] == row["bucket_id"]].drop(columns="bucket_id")
            signatures.add((row["based_on_success_index"], row["bucket_logic"], row["scoring_status"],
                            bool(row["more_allowed"]), own.fillna("").to_json(orient="values")))
        if len(signatures) > 1:
            raise ValueError(f"{doi} {group}: open-group members must have identical parents, rules and status.")
    return {"path": path, "papers": papers, "tables": tables, "sheet": frame,
            "companions": companions,
            "embedded_metadata": embedded["bundle"] if embedded is not None else None,
            "window_id_aliases": embedded["window_id_aliases"] if embedded is not None else {}}


def load_predictions(path, reference, *, positive=False):
    path = Path(path).expanduser().resolve()
    frame = _normalize_frame(read_rows(path))
    required = ("doi",) if positive else NEGATIVE_COLUMNS
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}.")
    if not any(field in frame for fields in DETAIL_GROUPS.values() for field in fields):
        raise ValueError(f"{path.name}: no synthesis recipe fields; input must be an expanded row CSV.")
    frame.insert(0, "csv_line", range(2, len(frame) + 2))
    frame.insert(0, "prediction_id", [f"{'P' if positive else 'N'}{i:06d}" for i in range(1, len(frame) + 1)])
    outside = ~frame["doi"].isin(reference["papers"])
    statuses = frame.get("status", pd.Series("", index=frame.index)).astype(str).str.strip().str.lower()
    statuses = statuses.str.replace(r"[\s-]+", "_", regex=True)
    non_record_statuses = {"no_negative", "no_negatives", "no_negative_records", "no_records", "no_results",
                          "empty", "failed", "failure", "error", "skipped", "pending", "in_progress",
                          "cancelled", "canceled", "timeout"}
    invalid_status = statuses.isin(non_record_statuses)
    recipe_fields = {field for fields in DETAIL_GROUPS.values() for field in fields}
    recipe_fields |= {field + "_abbr" for category, fields in DETAIL_GROUPS.items()
                      if category.endswith("_name") for field in fields}
    present_fields = sorted(recipe_fields & set(frame.columns))
    nonempty_recipe = frame[present_fields].apply(lambda col: col.map(lambda value: not _blank(value))).any(axis=1)
    empty_recipe = ~nonempty_recipe
    reason = pd.Series("", index=frame.index, dtype=str)
    reason.loc[empty_recipe] = "No machine-readable synthesis recipe values"
    reason.loc[invalid_status] = "Non-record or failed status: " + statuses[invalid_status]
    reason.loc[outside] = "DOI outside reference paper manifest"
    ignored_mask = reason.ne("")
    ignored = frame.loc[ignored_mask, ["prediction_id", "csv_line", "doi"]].copy()
    ignored["reason"] = reason[ignored_mask]
    for field in ("status", "error"):
        ignored[field] = frame.loc[ignored_mask, field] if field in frame else ""
    if "based_on_success_index" not in frame:
        frame["based_on_success_index"] = ""
    kept = frame[~ignored_mask].reset_index(drop=True)
    return kept, ignored, {"rows_read": len(frame), "rows_kept": len(kept),
                          "rows_outside_reference": int(outside.sum()),
                          "rows_ignored_non_record_status": int((invalid_status & ~outside).sum()),
                          "rows_ignored_empty_recipe": int((empty_recipe & ~outside & ~invalid_status).sum()),
                          "papers_with_rows": int(kept["doi"].nunique())}


def _paper_metrics(rows, scored, reference):
    buckets = reference["tables"]["windows"]
    gt_scored = set(buckets.loc[buckets["scoring_status"].eq("scored"), "doi"])
    gt_any = set(buckets["doi"])
    present = set(rows["doi"])
    records = []
    for doi, paper_id in reference["papers"].items():
        own = rows[rows["doi"] == doi]
        slots = scored[scored["doi"] == doi]
        expected, filled = int(slots["expected"].sum()), int(slots["filled"].sum())
        counted = own.loc[~own["dropped"].astype(bool)]
        unsupported = int((~counted["fits"].astype(bool)).sum())
        optional_only = doi in gt_any and doi not in gt_scored
        positive = doi in gt_scored
        predicted = doi in present
        label = "excluded_optional_only" if optional_only else (
            "TP" if positive and predicted else "FN" if positive else "FP" if predicted else "TN")
        records.append({"paper_id": paper_id, "doi": doi, "paper_label": label,
                        "reference_has_scored_negative": positive, "optional_only": optional_only,
                        "predicted_negative_presence": predicted, "submitted_negative_rows": len(own),
                        "counted_negative_rows": len(counted), "unsupported_negative_rows": unsupported,
                        "excluded_negative_rows": int(own["dropped"].sum()),
                        "supported_negative_rows": int(own["fits"].sum()),
                        "scored_slots": expected, "filled_slots": filled, "missed_slots": expected - filled,
                        "any_scored_window_fulfilled": filled > 0,
                        "per_paper_window_coverage": _ratio(filled, expected),
                        "contains_missed_protocols": filled < expected,
                        "complete_scored_coverage": expected > 0 and filled == expected,
                        "complete_coverage_no_unsupported_rows": expected > 0 and filled == expected and unsupported == 0})
    table = pd.DataFrame(records)
    counts = Counter(table["paper_label"])
    tp, tn, fp, fn = (counts[k] for k in ("TP", "TN", "FP", "FN"))
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    metrics = {"papers_analyzed": len(table), "classification_evaluable": tp + tn + fp + fn,
               "optional_only_excluded": counts["excluded_optional_only"],
               "reference_positive_papers": len(gt_scored), "reference_no_negative_papers": len(table) - len(gt_any),
               "TP": tp, "TN": tn, "FP": fp, "FN": fn,
               "accuracy": _ratio(tp + tn, tp + tn + fp + fn), "precision": precision,
               "recall": recall, "F1": _harmonic(precision, recall),
               "papers_containing_missed_protocols": int(table["contains_missed_protocols"].sum()),
               "papers_with_complete_scored_coverage": int(table["complete_scored_coverage"].sum()),
               "papers_with_complete_coverage_no_unsupported_rows": int(table["complete_coverage_no_unsupported_rows"].sum()),
               "papers_with_any_supported_negative": int(table["supported_negative_rows"].gt(0).sum()),
               "execution_coverage_verified": False}
    return table, metrics


def summarize_paper_recovery(paper_labels):
    """Content-supported recovery; also accepts historical saved paper_metrics tables.

    Only scored_slots and filled_slots are needed, so this additive summary can be
    computed from saved labels without rerunning the chemistry/window matcher.
    """
    expected = pd.to_numeric(paper_labels["scored_slots"], errors="raise")
    filled = pd.to_numeric(paper_labels["filled_slots"], errors="raise")
    if expected.isna().any() or filled.isna().any() or (expected < 0).any() or (filled < 0).any() or (filled > expected).any():
        raise ValueError("Paper coverage requires finite nonnegative counts with filled_slots <= scored_slots.")
    if not np.isfinite(expected).all() or not np.isfinite(filled).all():
        raise ValueError("Paper coverage requires finite counts.")
    eligible = expected > 0
    coverage = filled[eligible] / expected[eligible]
    recovered = int(filled[eligible].gt(0).sum())
    count = int(eligible.sum())
    return {"papers_analyzed": len(paper_labels), "papers_with_scored_windows": count,
            "papers_without_scored_windows_excluded": len(paper_labels) - count,
            "papers_with_at_least_one_scored_window_fulfilled": recovered,
            "papers_with_no_scored_window_fulfilled": count - recovered,
            "recovery_rate": _ratio(recovered, count),
            "mean_per_paper_window_coverage": float(coverage.mean()) if count else None,
            "median_per_paper_window_coverage": float(coverage.median()) if count else None,
            "papers_with_complete_scored_coverage": int((filled[eligible] == expected[eligible]).sum()),
            "definition": "At least one fulfilled scored window; equal paper weight for macro coverage; "
                          "separate from binary presence detection."}


def _parent_coverage_recipe_key(row):
    """Exact evaluated-recipe identity, independent of model/parent/source labels."""
    fields = {field for members in DETAIL_GROUPS.values() for field in members}
    fields |= {slot + "_amount_unit" for slot in SLOT_FIELDS}
    values = []
    for field in sorted(fields):
        value = norm_str(row.get(field))
        if value is None and field in SLOT_FIELDS + SOLVENT_FIELDS:
            value = norm_str(row.get(field + "_abbr"))
        if value is not None and (field.endswith(("_amount_value", "_ml")) or field in ("temperature_c", "time_h")):
            try:
                number = float(value)
                value = format(number, ".15g") if math.isfinite(number) else value
            except ValueError:
                pass
        values.append((field, value))
    payload = json.dumps([doi_key(row.get("doi")), values], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_parent_negative_coverage(reference, record_labels, predictions=None):
    """Summarize coverage of each positive parent's associated negative evidence.

    This uses only scored-window metadata and negative rows' ``fits_windows``
    labels, so historical saved evaluations need no matching rerun. It returns
    ``(summary, parent_labels, paper_labels)``. Primary coverage uses maximum
    parent-to-recipe matching. Supplying predictions (including prediction_id)
    collapses exact recipe duplicates before assignment. Without predictions,
    distinct row IDs are used and the missing deduplication is disclosed.
    """
    windows = reference["tables"]["windows"]
    scored = windows[windows["scoring_status"].eq("scored")]
    required = {}
    parent_of_window = {}
    known_windows = set(windows["bucket_id"])
    for row in scored.to_dict("records"):
        key = (row["doi"], _index_key(row["based_on_success_index"]))
        required.setdefault(key, set()).add(row["bucket_id"])
        parent_of_window[row["bucket_id"]] = key
    evidence = {key: set() for key in required}
    unambiguous = {key: set() for key in required}
    covered_windows = {key: set() for key in required}
    ambiguous_rows = []
    recipe_by_prediction = {}
    if predictions is not None:
        if "prediction_id" not in predictions:
            raise ValueError("Prediction recipes need prediction_id to join saved record labels.")
        if predictions["prediction_id"].duplicated().any():
            raise ValueError("Prediction recipe IDs must be unique.")
        recipe_by_prediction = {str(row["prediction_id"]): _parent_coverage_recipe_key(row)
                                for row in predictions.to_dict("records")}
    recipe_parents = {}
    recipe_rows = {}
    for index, row in enumerate(record_labels.to_dict("records"), 1):
        raw = row.get("fits_windows", "")
        hits = set() if _blank(raw) else {token.strip() for token in str(raw).split(";") if token.strip()}
        hits = {reference.get("window_id_aliases", {}).get(hit, hit) for hit in hits}
        unknown = hits - known_windows
        if unknown:
            raise ValueError(f"Prediction row {index}: unknown matched windows {sorted(unknown)}.")
        keys = {parent_of_window[hit] for hit in hits if hit in parent_of_window}
        doi = doi_key(row.get("doi", ""))
        if any(key[0] != doi for key in keys):
            raise ValueError(f"Prediction row {index}: matched window DOI differs from prediction DOI.")
        prediction_id = str(row.get("prediction_id") or f"row_{index}")
        if predictions is not None and prediction_id not in recipe_by_prediction:
            raise ValueError(f"Prediction {prediction_id} has no corresponding recipe row.")
        recipe_id = recipe_by_prediction.get(prediction_id, prediction_id)
        if keys:
            recipe_parents.setdefault(recipe_id, set()).update(keys)
            recipe_rows.setdefault(recipe_id, set()).add(prediction_id)
        if len(keys) > 1:
            ambiguous_rows.append({"prediction_id": prediction_id, "doi": doi,
                                   "compatible_parent_indices": sorted(key[1] for key in keys)})
        for key in keys:
            evidence[key].add(prediction_id)
            covered_windows[key].update(hits & required[key])
            if len(keys) == 1:
                unambiguous[key].add(prediction_id)
    # Abbreviations are identity fallbacks, not extra distinct-recipe evidence.
    # Recompute the unambiguous sensitivity after duplicate recipes are merged.
    unambiguous = {key: set() for key in required}
    for recipe_id, keys in recipe_parents.items():
        if len(keys) == 1:
            unambiguous[next(iter(keys))].update(recipe_rows[recipe_id])
    # Sorted adjacency lists make equally optimal assignments reproducible.
    compatibility = {key: sorted(recipe_id for recipe_id, keys in recipe_parents.items() if key in keys)
                     for key in sorted(required)}
    assignment = kuhns_max_matching(compatibility)
    context = {(row["doi"], _index_key(row["success_index"])): row
               for row in reference["tables"]["window_parents"].to_dict("records")}
    parent_rows = []
    for key, window_ids in required.items():
        doi, parent_index = key
        parent_rows.append({"paper_id": reference["papers"][doi], "doi": doi,
                            "success_index": parent_index, "mof_name": context.get(key, {}).get("mof_name", ""),
                            "scored_negative_windows": len(window_ids),
                            "scored_window_ids": ";".join(sorted(window_ids)),
                            "compatible_scored_window_ids": ";".join(sorted(covered_windows[key])),
                            "compatible_negative_rows": len(evidence[key]),
                            "compatible_prediction_ids": ";".join(sorted(evidence[key])),
                            "parent_negative_covered": key in assignment,
                            "parent_negative_covered_union": bool(evidence[key]),
                            "assigned_recipe_key": assignment.get(key, ""),
                            "assigned_prediction_id": min(recipe_rows[assignment[key]]) if key in assignment else "",
                            "assigned_recipe_duplicate_row_ids": ";".join(sorted(recipe_rows[assignment[key]])) if key in assignment else "",
                            "unambiguous_negative_rows": len(unambiguous[key]),
                            "parent_negative_covered_unambiguous": bool(unambiguous[key]),
                            "covered_only_by_ambiguous_rows": bool(evidence[key]) and not unambiguous[key]})
    parent_labels = pd.DataFrame(parent_rows, columns=[
        "paper_id", "doi", "success_index", "mof_name", "scored_negative_windows", "scored_window_ids",
        "compatible_scored_window_ids", "compatible_negative_rows", "compatible_prediction_ids",
        "parent_negative_covered", "parent_negative_covered_union", "assigned_recipe_key", "assigned_prediction_id",
        "assigned_recipe_duplicate_row_ids", "unambiguous_negative_rows", "parent_negative_covered_unambiguous",
        "covered_only_by_ambiguous_rows"])
    paper_rows = []
    for doi, paper_id in reference["papers"].items():
        own = parent_labels[parent_labels["doi"].eq(doi)]
        count = len(own)
        covered = int(own["parent_negative_covered"].sum())
        uniquely_covered = int(own["parent_negative_covered_unambiguous"].sum())
        union_covered = int(own["parent_negative_covered_union"].sum())
        status = ("excluded_no_scored_parent" if not count else "all" if covered == count else
                  "some" if covered else "none")
        paper_rows.append({"paper_id": paper_id, "doi": doi, "required_negative_parents": count,
                           "covered_negative_parents": covered, "negative_parent_coverage": _ratio(covered, count),
                           "negative_parent_recovery_status": status,
                           "all_negative_parents_covered": count > 0 and covered == count,
                           "covered_negative_parents_union": union_covered,
                           "all_negative_parents_covered_union": count > 0 and union_covered == count,
                           "covered_negative_parents_unambiguous": uniquely_covered,
                           "all_negative_parents_covered_unambiguous": count > 0 and uniquely_covered == count})
    paper_labels = pd.DataFrame(paper_rows)
    eligible = paper_labels[paper_labels["required_negative_parents"].gt(0)]
    statuses = Counter(eligible["negative_parent_recovery_status"])
    covered = int(parent_labels["parent_negative_covered"].sum())
    uniquely_covered = int(parent_labels["parent_negative_covered_unambiguous"].sum())
    complete_unambiguous = int(eligible["all_negative_parents_covered_unambiguous"].sum())
    union_covered = int(parent_labels["parent_negative_covered_union"].sum())
    union_complete = int(eligible["all_negative_parents_covered_union"].sum())
    summary = {"papers_analyzed": len(paper_labels), "papers_eligible": len(eligible),
               "papers_without_scored_negative_parent_excluded": len(paper_labels) - len(eligible),
               "parents_eligible": len(parent_labels), "parents_covered": covered,
               "parents_uncovered": len(parent_labels) - covered,
               "parent_coverage_rate": _ratio(covered, len(parent_labels)),
               "papers_all_parents_covered": statuses["all"], "papers_some_parents_covered": statuses["some"],
               "papers_no_parents_covered": statuses["none"],
               "paper_all_parent_coverage_rate": _ratio(statuses["all"], len(eligible)),
               "mean_per_paper_parent_coverage": float(eligible["negative_parent_coverage"].mean()) if len(eligible) else None,
               "median_per_paper_parent_coverage": float(eligible["negative_parent_coverage"].median()) if len(eligible) else None,
               "ambiguous_negative_rows": len(ambiguous_rows),
               "ambiguous_negative_row_details": ambiguous_rows,
               "parents_covered_with_unambiguous_evidence": uniquely_covered,
               "parents_covered_only_by_ambiguous_rows": union_covered - uniquely_covered,
               "papers_all_parents_covered_with_unambiguous_evidence": complete_unambiguous,
               "papers_relying_on_ambiguous_parent_associations": union_complete - complete_unambiguous,
               "union_parents_covered": union_covered, "union_papers_all_parents_covered": union_complete,
               "union_parent_coverage_rate": _ratio(union_covered, len(parent_labels)),
               "union_complete_parent_coverage_rate": _ratio(union_complete, len(eligible)),
               "exact_recipe_deduplication_applied": predictions is not None,
               "compatible_prediction_rows": sum(len(ids) for ids in recipe_rows.values()),
               "distinct_compatible_recipes": len(recipe_parents),
               "compatible_duplicate_rows_collapsed": sum(len(ids) - 1 for ids in recipe_rows.values()),
               "recipe_fingerprint": "DOI + normalized evaluated names (abbreviation fallback only for a missing name), numeric amounts and units, "
                                     "solvent volumes, temperature and time; excludes MOF label, parent index, "
                                     "source/provenance, varied classes, row IDs and free-text amounts.",
               "source": "negative prediction compatibility with scored reference windows only",
               "definition": DEFINITIONS["parent_negative_coverage"]}
    summary.update(eligible_papers=len(eligible), eligible_parents=len(parent_labels), fulfilled_parents=covered,
                   papers_all_parents_fulfilled=statuses["all"], papers_partial_parent_coverage=statuses["some"],
                   papers_no_parent_coverage=statuses["none"],
                   complete_parent_coverage_rate=_ratio(statuses["all"], len(eligible)),
                   macro_parent_coverage=summary["mean_per_paper_parent_coverage"])
    return summary, parent_labels, paper_labels


def summarize_paper_completion(reference, record_labels, parent_paper_labels):
    """Operational complete-recovery confusion, separate from raw output presence.

    Reference-positive papers need all eligible parents fulfilled. Papers without
    any negative reference window are FP/TN according to output presence. Papers
    with optional-only evidence remain explicitly unclassified until adjudicated.
    """
    all_evidence = set(reference["tables"]["windows"]["doi"])
    present = {doi_key(value) for value in record_labels["doi"]}
    coverage = {row["doi"]: row for row in parent_paper_labels.to_dict("records")}
    rows = []
    for doi, paper_id in reference["papers"].items():
        parent_row = coverage[doi]
        if parent_row["required_negative_parents"]:
            label = "TP" if parent_row["all_negative_parents_covered"] else "FN"
        elif doi in all_evidence:
            label = "excluded_optional_only"
        else:
            label = "FP" if doi in present else "TN"
        rows.append({"paper_id": paper_id, "doi": doi, "completion_label": label,
                     "has_negative_output": doi in present,
                     "required_negative_parents": parent_row["required_negative_parents"],
                     "covered_negative_parents": parent_row["covered_negative_parents"]})
    table = pd.DataFrame(rows)
    counts = Counter(table["completion_label"])
    tp, tn, fp, fn = (counts[key] for key in ("TP", "TN", "FP", "FN"))
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    summary = {"papers_analyzed": len(table), "classification_evaluable": tp + tn + fp + fn,
               "optional_only_excluded": counts["excluded_optional_only"],
               "TP": tp, "TN": tn, "FP": fp, "FN": fn,
               "accuracy": _ratio(tp + tn, tp + tn + fp + fn), "precision": precision,
               "recall": recall, "F1": _harmonic(precision, recall),
               "definition": "Operational complete-recovery labels: TP requires distinct compatible negatives "
                             "for every eligible parent; FN includes partial recovery. Among papers with no "
                             "negative reference windows, any negative output is FP and no output is TN. "
                             "Optional-only papers are excluded until adjudicated. Extra unsupported rows on "
                             "reference-positive papers remain protocol FP, without changing completion TP."}
    return summary, table


def _rename_field_metrics(frame):
    frame = frame.rename(columns={"TN_rows": "valid_rows_without_class", "F1": "coverage_F1"}).copy()
    frame["coverage_F1"] = [_harmonic(None if pd.isna(p) else float(p), None if pd.isna(r) else float(r))
                            for p, r in zip(frame["precision"], frame["recall"])]
    frame["accuracy"] = None
    return frame


def _detail_changes(candidate, parent, parents):
    """Observed changes versus the declared parent; missing numeric values are not changes."""
    aligned = align_slots(candidate, parent)
    changed = set()
    for category, fields in DETAIL_GROUPS.items():
        for field in fields:
            value, base = aligned.get(field), parent.get(field)
            numeric = field.endswith(("_amount_value", "_ml")) or field in ("temperature_c", "time_h")
            if numeric:
                if _blank(value):
                    continue
                if _blank(base) or field_differs_from_parent(aligned, parent, field, parents):
                    changed.add(category)
            elif not (_blank(value) and _blank(base)) and not same_component(
                    value, base, aligned.get(field + "_abbr"), parent.get(field + "_abbr")):
                changed.add(category)
    return changed


def _detail_tables(negatives, rows, scored, reference):
    parents = reference["tables"]["window_parents"]
    rules, buckets = reference["tables"]["window_rules"], reference["tables"]["windows"]
    parent_of = {(r["doi"], _index_key(r["success_index"])): r for r in parents.to_dict("records")}
    fields = sorted(set(parents.columns) | {"based_on_success_index"})
    row_labels = []
    for raw, outcome in zip(negatives.to_dict("records"), rows.to_dict("records")):
        candidate = _candidate(raw, fields)
        parent = parent_of.get((raw["doi"], _index_key(raw["based_on_success_index"])))
        changes = _detail_changes(candidate, parent, parents) if parent is not None else None
        for category in DETAIL_GROUPS:
            changed = category in changes if changes is not None else None
            label = ("excluded" if outcome["dropped"] else "unknown_parent" if changed is None else
                     "TP_row" if changed and outcome["fits"] else "FP_row" if changed else
                     "valid_row_without_class" if outcome["fits"] else "unattributed_invalid_row")
            row_labels.append({"prediction_id": raw["prediction_id"], "csv_line": raw["csv_line"],
                               "doi": raw["doi"], "field": category, "field_changed": changed,
                               "supported_row": outcome["fits"], "label": label})
    window_labels = []
    bucket_of = buckets.set_index("bucket_id")
    for window in scored.to_dict("records"):
        bid = window["window_id"]
        parent = resolve_bucket_parent(bucket_of.loc[bid], parents)
        anchors = rules[rules["bucket_id"] == bid]
        changed = {rule["field_name"] for rule in anchors.to_dict("records")
                   if not anchor_satisfied(parent, parent, rule)}
        if not changed:
            changed = set(anchors["field_name"])
        categories = {category for category, fields in DETAIL_GROUPS.items() if changed & set(fields)}
        for category in categories:
            window_labels.append({"window_id": bid, "doi": window["doi"], "field": category,
                                  "TP_slots": window["filled"], "FN_slots": window["expected"] - window["filled"]})
    summaries = []
    for category in DETAIL_GROUPS:
        counts = Counter(row["label"] for row in row_labels if row["field"] == category)
        tp_slots = sum(row["TP_slots"] for row in window_labels if row["field"] == category)
        fn_slots = sum(row["FN_slots"] for row in window_labels if row["field"] == category)
        precision = _ratio(counts["TP_row"], counts["TP_row"] + counts["FP_row"])
        recall = _ratio(tp_slots, tp_slots + fn_slots)
        summaries.append({"field": category, "TP_rows": counts["TP_row"], "FP_rows": counts["FP_row"],
                          "valid_rows_without_class": counts["valid_row_without_class"],
                          "unattributed_invalid_rows": counts["unattributed_invalid_row"],
                          "unknown_parent_rows": counts["unknown_parent"], "excluded_rows": counts["excluded"],
                          "TP_slots": tp_slots, "FN_slots": fn_slots, "precision": precision, "recall": recall,
                          "coverage_F1": _harmonic(precision, recall), "TN": None, "accuracy": None})
    return (pd.DataFrame(summaries),
            pd.DataFrame(row_labels, columns=["prediction_id", "csv_line", "doi", "field", "field_changed",
                                              "supported_row", "label"]),
            pd.DataFrame(window_labels, columns=["window_id", "doi", "field", "TP_slots", "FN_slots"]))


_CONTROL_ROLES = (SLOT_FIELDS[:3], SLOT_FIELDS[3:6], SLOT_FIELDS[6:], SOLVENT_FIELDS)


def _control_number_equal(candidate, reference, tolerance):
    if _blank(candidate) or _blank(reference):
        return False
    try:
        left, right = float(candidate), float(reference)
    except (ValueError, TypeError):
        return False
    return (math.isfinite(left) and math.isfinite(right) and
            abs(left - right) <= max(1e-9, tolerance * max(abs(left), abs(right))))


def _control_slot_active(row, slot):
    suffix = "_ml" if slot in SOLVENT_FIELDS else "_amount_value"
    return any(not _blank(row.get(slot + part)) for part in ("", "_abbr", suffix))


def _control_identity_keys(name, abbreviation, role):
    """Explicit aliases only; preserve substituents, counterions and hydrates."""
    from mofinder.evaluation.positive import canonical_name, clean
    if _blank(name):
        name = abbreviation
    if _blank(name):
        return set()
    values = [str(name)]
    suffix = re.search(r"\s*\(([^()]*)\)\s*$", str(name))
    if suffix and not _blank(abbreviation) and clean(suffix.group(1)) == clean(abbreviation):
        values.append(str(name)[:suffix.start()].strip())
    keys = {canonical_name(value) for value in values}
    if role.startswith("metal_"):
        # Do not use normalize_entry: its historical cleaning can remove
        # counterions/adducts. Only a completely parsed simple salt name may
        # become a formula; explicit dictionary mappings remain available.
        anions = "|".join(re.escape(key) for key in sorted(ANION, key=len, reverse=True))
        hydrates = "|".join(re.escape(key) for key in sorted(HYDRATE_WORD, key=len, reverse=True))
        salt = re.compile(rf"[A-Za-z]+\s*(?:\([IVXivx]+\))?\s+(?:{anions})(?:\s+(?:{hydrates}))?", re.I)
        for value in values:
            mapped = canon_metal(value)
            if salt.fullmatch(value.strip()):
                mapped = text_salt_to_formula(value) or mapped
            # Dot notation changes only water-of-crystallization punctuation.
            key = clean(mapped).replace("·", ".").replace("*", ".")
            key = re.sub(r"\.h2o$", ".1h2o", key)
            keys.add(key)
    return {key for key in keys if key}


def _control_identity_matches(candidate, control, candidate_slot, control_slot):
    from mofinder.evaluation.positive import clean
    cn, ca = candidate.get(candidate_slot), candidate.get(candidate_slot + "_abbr")
    rn, ra = control.get(control_slot), control.get(control_slot + "_abbr")
    if _blank(rn) and _blank(ra):
        return True
    if _control_identity_keys(cn, ca, control_slot) & _control_identity_keys(rn, ra, control_slot):
        return True
    # A name may be the other row's explicit abbreviation. Two different full
    # names cannot be equated merely because both use a generic H2L label.
    shorthand = lambda value: not _blank(value) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_'′-]{0,23}", str(value).strip()))
    return ((not _blank(cn) and shorthand(ra) and clean(cn) == clean(ra)) or
            (not _blank(rn) and shorthand(ca) and clean(rn) == clean(ca)))


def _control_slot_matches(candidate, control, candidate_slot, control_slot, tolerance):
    if not _control_identity_matches(candidate, control, candidate_slot, control_slot):
        return False
    solvent = control_slot in SOLVENT_FIELDS
    suffix = "_ml" if solvent else "_amount_value"
    expected, observed = control.get(control_slot + suffix), candidate.get(candidate_slot + suffix)
    if not _blank(expected):
        if _blank(observed):
            return False
        if not solvent:
            expected_unit = control.get(control_slot + "_amount_unit")
            observed_unit = candidate.get(candidate_slot + "_amount_unit")
            if _blank(expected_unit) or _blank(observed_unit):
                return False
            observed = convert_amount_named(observed, observed_unit, expected_unit,
                candidate.get(candidate_slot), control.get(control_slot), control_slot + "_amount_value")
            if observed is None:
                return False
        if not _control_number_equal(observed, expected, tolerance):
            return False
    return True


def _control_alignment(candidate, control, amount_tolerance=0.05):
    if doi_key(candidate.get("doi")) != doi_key(control.get("doi")):
        return None
    for field in ("temperature_c", "time_h"):
        if not _blank(control.get(field)) and not _control_number_equal(candidate.get(field), control[field], 1e-6):
            return None
    alignment = {}
    for slots in _CONTROL_ROLES:
        required = [slot for slot in slots if _control_slot_active(control, slot)]
        present = [slot for slot in slots if _control_slot_active(candidate, slot)]
        if len(required) != len(present):
            return None
        chosen = next((order for order in itertools.permutations(present)
                       if all(_control_slot_matches(candidate, control, a, b, amount_tolerance)
                              for a, b in zip(order, required))), None)
        if chosen is None:
            return None
        alignment.update(zip(required, chosen))
    return alignment


def successful_control_matches(candidate, control, amount_tolerance=0.05):
    """Match every known control field, without inheriting missing predictions.

    Unreported reference quantities remain unconstrained. This matches a recorded
    successful-control profile, not a claim of identical unreported experiments.
    Parent IDs, outcome labels, MOF labels and change classifications are ignored.
    """
    return _control_alignment(candidate, control, amount_tolerance) is not None


def _control_unknown_numeric_fields(control):
    fields = [slot + ("_ml" if slot in SOLVENT_FIELDS else "_amount_value")
              for slots in _CONTROL_ROLES for slot in slots if _control_slot_active(control, slot)]
    fields += ["temperature_c", "time_h"]
    return [field for field in fields if _blank(control.get(field))]


def _reference_case_metrics(tp, fn, fp, tn):
    tp, fn, fp, tn = (int(value) for value in (tp, fn, fp, tn))
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    total = tp + fn + fp + tn
    return {"TP": tp, "FN": fn, "FP": fp, "TN": tn, "total": total,
            "negative_cases": tp + fn, "successful_controls": fp + tn,
            "accuracy": _ratio(tp + tn, total), "precision": precision, "recall": recall,
            "F1": _ratio(2 * tp, 2 * tp + fp + fn)}


def summarize_reference_rows(reference, record_labels, window_labels, predictions, field_window_labels,
                             *, initialize_calibration=True):
    """Return fixed reference-case metrics and matched-control evidence.

    This helper also accepts the saved CSV DataFrames from a prior evaluation.
    Window coverage and field associations are reused exactly; control matching
    examines all substantive negative prediction recipes, including policy-excluded
    rows. Each associated parent ID is one control, without output-based filtering.
    """
    global LINKER_MW_DATA
    if initialize_calibration and reference.get("embedded_metadata") is not None:
        LINKER_MW_DATA = reference["embedded_metadata"]["linker_molecular_weights"]
        linker_molar_masses.cache_clear()
        molar_mass_of.cache_clear()
    windows = reference["tables"]["windows"]
    scored = windows[windows["scoring_status"].eq("scored")]
    parent_of_window = {row["bucket_id"]: (row["doi"], _index_key(row["based_on_success_index"]))
                        for row in scored.to_dict("records")}
    eligible = set(parent_of_window.values())
    controls = {(row["doi"], _index_key(row["success_index"])): row.copy()
                for row in reference["tables"]["window_parents"].to_dict("records")
                if (row["doi"], _index_key(row["success_index"])) in eligible}
    if set(controls) != eligible:
        raise ValueError("Every scored window needs an associated successful control profile.")
    aliases = reference.get("window_id_aliases", {})
    coverage = window_labels.copy()
    coverage["window_id"] = coverage["window_id"].map(lambda value: aliases.get(value, value))
    if coverage["window_id"].duplicated().any() or set(coverage["window_id"]) != set(parent_of_window):
        raise ValueError("Reference-row coverage needs exactly one label for every scored window.")
    for field in ("expected", "filled"):
        coverage[field] = pd.to_numeric(coverage[field], errors="raise")
    if not coverage["expected"].eq(1).all() or not coverage["filled"].isin([0, 1]).all():
        raise ValueError("Fixed reference-row accuracy requires binary, single-slot window labels.")
    fields = field_window_labels.copy()
    fields["window_id"] = fields["window_id"].map(lambda value: aliases.get(value, value))
    if set(fields["window_id"]) - set(parent_of_window) or set(fields["field"]) - set(DETAIL_GROUPS):
        raise ValueError("Field labels contain an unknown scored window or field category.")
    if predictions["prediction_id"].duplicated().any() or record_labels["prediction_id"].duplicated().any():
        raise ValueError("Prediction IDs must be unique when joining control evidence.")
    outcomes = {str(row["prediction_id"]): row for row in record_labels.to_dict("records")}
    if set(predictions["prediction_id"].astype(str)) != set(outcomes):
        raise ValueError("Control matching needs all substantive negative predictions and their record labels.")
    by_doi = {}
    for key, control in controls.items():
        control["control_id"] = f"{reference['papers'][key[0]]}-PR{int(float(key[1])):03d}"
        by_doi.setdefault(key[0], []).append(control)
    matches = []
    for raw in predictions.to_dict("records"):
        candidate = _candidate(raw, PARENT_COLUMNS)
        candidate["doi"] = doi_key(raw["doi"])
        for control in by_doi.get(candidate["doi"], []):
            alignment = _control_alignment(candidate, control)
            if alignment is None:
                continue
            unknown = _control_unknown_numeric_fields(control)
            supplied = []
            for field in unknown:
                candidate_field = field
                for slot, candidate_slot in alignment.items():
                    if field.startswith(slot + "_"):
                        candidate_field = candidate_slot + field[len(slot):]
                        break
                if not _blank(candidate.get(candidate_field)):
                    supplied.append({"reference_field": field, "candidate_field": candidate_field,
                                     "candidate_value": candidate[candidate_field],
                                     "candidate_unit": candidate.get(candidate_slot + "_amount_unit")
                                     if field.endswith("_amount_value") else "mL" if field.endswith("_ml") else
                                     "degC" if field == "temperature_c" else "h"})
            outcome = outcomes[str(raw["prediction_id"])]
            matches.append({"control_id": control["control_id"], "prediction_id": str(raw["prediction_id"]),
                "csv_line": raw.get("csv_line", ""), "doi": candidate["doi"],
                "source_policy_dropped": outcome.get("dropped", False),
                "also_fits_failure_windows": outcome.get("fits_windows", ""),
                "control_profile_complete": not unknown,
                "unknown_reference_numeric_fields": ";".join(unknown),
                "candidate_values_unconstrained_by_control": json.dumps(_jsonable(supplied), ensure_ascii=False),
                "incomplete_specificity": bool(supplied)})
    false_controls = {row["control_id"] for row in matches}
    control_rows = []
    field_controls = {field: set() for field in DETAIL_GROUPS}
    for field, names in DETAIL_GROUPS.items():
        parent_keys = {parent_of_window[wid] for wid in fields.loc[fields["field"].eq(field), "window_id"]}
        field_controls[field] = {controls[key]["control_id"] for key in parent_keys
                                 if any(not _blank(controls[key].get(name)) for name in names)}
    for key, control in controls.items():
        own = [row for row in matches if row["control_id"] == control["control_id"]]
        unknown = _control_unknown_numeric_fields(control)
        control_rows.append({"control_id": control["control_id"], "paper_id": reference["papers"][key[0]],
            "doi": key[0], "success_index": key[1], "mof_name": control.get("mof_name", ""),
            "label": "FP" if own else "TN", "matched_negative_rows": len(own),
            "matching_prediction_ids": ";".join(sorted(row["prediction_id"] for row in own)),
            "control_profile_complete": not unknown, "unknown_reference_numeric_fields": ";".join(unknown),
            "matched_with_incomplete_specificity": any(row["incomplete_specificity"] for row in own),
            "field_categories": ";".join(field for field in DETAIL_GROUPS if control["control_id"] in field_controls[field])})
    tp, total_negative = int(coverage["filled"].sum()), len(coverage)
    metrics = _reference_case_metrics(tp, total_negative - tp, len(false_controls), len(controls) - len(false_controls))
    metrics.update(control_profiles_complete=sum(row["control_profile_complete"] for row in control_rows),
                   control_profiles_partial=sum(not row["control_profile_complete"] for row in control_rows),
                   matched_negative_output_rows=len({row["prediction_id"] for row in matches}),
                   controls_matched_with_incomplete_specificity=sum(row["matched_with_incomplete_specificity"] for row in control_rows),
                   definition=DEFINITIONS["reference_row_metrics"])
    field_metrics = {}
    for field in DETAIL_GROUPS:
        own_ids = set(fields.loc[fields["field"].eq(field), "window_id"])
        field_tp = int(coverage.loc[coverage["window_id"].isin(own_ids), "filled"].sum())
        fp = len(field_controls[field] & false_controls)
        field_metrics[field] = _reference_case_metrics(field_tp, len(own_ids) - field_tp, fp, len(field_controls[field]) - fp)
    return {"reference_row_metrics": metrics, "reference_field_metrics": field_metrics,
            "control_labels": pd.DataFrame(control_rows, columns=["control_id", "paper_id", "doi", "success_index",
                "mof_name", "label", "matched_negative_rows", "matching_prediction_ids", "control_profile_complete",
                "unknown_reference_numeric_fields", "matched_with_incomplete_specificity", "field_categories"]),
            "control_matches": pd.DataFrame(matches, columns=["control_id", "prediction_id", "csv_line", "doi",
                "source_policy_dropped", "also_fits_failure_windows", "control_profile_complete",
                "unknown_reference_numeric_fields", "candidate_values_unconstrained_by_control", "incomplete_specificity"])}


def _calibration_path(reference, linker_molecular_weights=None):
    if linker_molecular_weights is None and reference.get("embedded_metadata") is not None:
        return None
    mass_path = Path(linker_molecular_weights or reference["path"].with_name("linker_molecular_weights.csv")).resolve()
    if not mass_path.is_file():
        raise FileNotFoundError(f"Missing linker molecular-weight calibration: {mass_path}")
    return mass_path


def analyze(csv_path=None, ground_truth=DEFAULT_REFERENCE, *, positive_csv=None,
            linker_molecular_weights=None, window_rule="open", model_label=None):
    """Return summary and auditable DataFrames without writing files or making API calls."""
    global LINKER_MW_DATA, LINKER_MW_FILE
    if csv_path is None:
        raise ValueError("Supply the model-specific negative output CSV.")
    if window_rule not in ("open", "strict"):
        raise ValueError("window_rule must be open or strict.")
    reference = load_reference(ground_truth)
    mass_path = _calibration_path(reference, linker_molecular_weights)
    LINKER_MW_DATA = (reference["embedded_metadata"]["linker_molecular_weights"] if mass_path is None else None)
    if mass_path is not None:
        LINKER_MW_FILE = mass_path
    linker_molar_masses.cache_clear()
    molar_mass_of.cache_clear()
    _POS_BY_DOI_CACHE.clear()
    negatives, ignored, coverage = load_predictions(csv_path, reference)
    positive_ignored = pd.DataFrame(columns=ignored.columns)
    positives = pd.DataFrame(columns=["doi", "based_on_success_index"])
    if positive_csv is not None:
        positives, positive_ignored, positive_coverage = load_predictions(positive_csv, reference, positive=True)
        coverage["positive_rows"] = positive_coverage
    matcher = window_matcher("singleslot", window_rule)
    rows, scored, checks = score_rows(matcher, reference["tables"], negatives, positives, reference["papers"])
    for column in ("fits", "dropped", "modulator_amount_only"):
        rows[column] = rows[column].astype(bool)
    for column in ("prediction_id", "csv_line"):
        rows[column] = negatives[column].values
    invalid = checks.loc[checks["check"].eq("scored windows that could not be scored"), "count"]
    if len(invalid) and int(invalid.iloc[0]):
        raise ValueError("At least one scored window cannot be scored; repair its parent/rules before evaluation.")
    field_metrics = _rename_field_metrics(field_table(rows, scored))
    paper_labels, paper_detection = _paper_metrics(rows, scored, reference)
    parent_coverage, parent_labels, parent_papers = summarize_parent_negative_coverage(reference, rows, negatives)
    paper_completion, completion_labels = summarize_paper_completion(reference, rows, parent_papers)
    paper_labels = paper_labels.merge(parent_papers, on=["paper_id", "doi"], validate="one_to_one")
    paper_labels = paper_labels.merge(completion_labels[["paper_id", "doi", "completion_label"]],
                                      on=["paper_id", "doi"], validate="one_to_one")
    counted = rows[~rows["dropped"]]
    tp_rows, fp_rows = int(counted["fits"].sum()), int((~counted["fits"]).sum())
    tp_slots, total_slots = int(scored["filled"].sum()), int(scored["expected"].sum())
    precision, recall = _ratio(tp_rows, tp_rows + fp_rows), _ratio(tp_slots, total_slots)
    protocol = {"submitted_records": len(rows), "records_counted": len(counted), "excluded_records": int(rows["dropped"].sum()),
                "TP_rows": tp_rows, "FP_rows": fp_rows, "TP_slots": tp_slots, "FN_slots": total_slots - tp_slots,
                "scored_slots": total_slots, "TN": None, "accuracy": None, "precision": precision,
                "recall": recall, "coverage_F1": _harmonic(precision, recall),
                "precision_without_exclusions": _ratio(int(rows["fits"].sum()), len(rows))}
    detail, detail_rows, detail_windows = _detail_tables(negatives, rows, scored, reference)
    reference_rows = summarize_reference_rows(reference, rows, scored, negatives, detail_windows,
                                               initialize_calibration=False)
    buckets = reference["tables"]["windows"]
    missing_optional = [b["bucket_id"] for b in buckets[buckets["scoring_status"].eq("optional")].to_dict("records")
                        if resolve_bucket_parent(b, reference["tables"]["window_parents"]) is None]
    suspicious = []
    for name, frame in (("predictions", negatives), ("parent_context", reference["tables"]["window_parents"])):
        for row in frame.to_dict("records"):
            if any(str(row.get(slot, "")).strip().lower() == "h3btb" for slot in ("linker_1", "linker_2", "linker_3")):
                suspicious.append({"source": name, "doi": row["doi"],
                                   "reason": "Legacy H3BTB alias corrected to 1,3,5-tris(4-carboxyphenyl)benzene"})
    summary = {"schema_version": SCHEMA_VERSION, "model_label": model_label or Path(csv_path).stem,
               "mode": "positive-assisted" if positive_csv is not None else "negative-only",
               "window_rule": window_rule, "paper_detection": paper_detection, "protocol_recovery": protocol,
               "paper_recovery": summarize_paper_recovery(paper_labels),
               "parent_negative_coverage": parent_coverage,
               "paper_completion": paper_completion,
               "reference_row_metrics": reference_rows["reference_row_metrics"],
               "reference_field_metrics": reference_rows["reference_field_metrics"],
               "input_coverage": coverage, "reference": {"papers": len(reference["papers"]), "windows": len(buckets),
               "scored_windows": int(buckets["scoring_status"].eq("scored").sum()),
               "optional_windows": int(buckets["scoring_status"].eq("optional").sum()),
               "parent_context_records": len(reference["tables"]["window_parents"]),
               "optional_windows_without_parent": missing_optional}, "definitions": DEFINITIONS,
               "audit_flags": suspicious}
    return {"summary": _jsonable(summary), "reference": reference, "mass_path": mass_path,
            "record_labels": row_table(rows).rename(columns={c: f"source_class_{c}" for c in FIELD_CLASSES}),
            "window_labels": window_table(scored), "paper_metrics": paper_labels,
            "parent_labels": parent_labels,
            "reference_field_metrics": pd.DataFrame([{"field": field, **values}
                for field, values in reference_rows["reference_field_metrics"].items()]),
            "control_labels": reference_rows["control_labels"],
            "control_matches": reference_rows["control_matches"],
            "paper_completion_labels": completion_labels,
            "field_metrics": field_metrics, "field_detail_metrics": detail, "field_labels": detail_rows,
            "field_window_labels": detail_windows, "checks": checks,
            "ignored_input_rows": ignored, "ignored_positive_rows": positive_ignored,
            "predictions_used": negatives, "positive_predictions_used": positives}


def evaluate(csv_path=None, ground_truth=DEFAULT_REFERENCE, *, output_dir=None,
             output_root=None, positive_csv=None, linker_molecular_weights=None,
             window_rule="open", model_label=None):
    """Analyze inputs, save labels/metrics/snapshots/hashes, and return (destination, summary)."""
    result = analyze(csv_path, ground_truth, positive_csv=positive_csv,
                     linker_molecular_weights=linker_molecular_weights,
                     window_rule=window_rule, model_label=model_label)
    if output_dir:
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=False)
    else:
        destination = create_run_directory(output_root or DEFAULT_OUTPUT_ROOT)
    for name, value in result.items():
        if isinstance(value, pd.DataFrame):
            _save_csv(value, destination / f"{name}.csv")
    reference = result["reference"]
    for name, value in reference["tables"].items():
        _save_csv(value, destination / f"reference_{name}_used.csv")
    _save_csv(pd.DataFrame([{"paper_id": pid, "doi": doi} for doi, pid in reference["papers"].items()]),
                destination / "paper_manifest_used.csv")
    paths = [Path(csv_path).expanduser().resolve(), reference["path"], *reference["companions"]]
    if result["mass_path"] is not None:
        paths.append(result["mass_path"])
    if positive_csv is not None:
        paths.append(Path(positive_csv).expanduser().resolve())
    snapshot_dir = destination / "input_snapshots"
    snapshot_dir.mkdir()
    inputs = []
    for i, path in enumerate(paths):
        snapshot = snapshot_dir / f"{i:02d}_{path.name}"
        shutil.copyfile(path, snapshot)
        inputs.append({"path": str(path), "sha256": _digest(path), "snapshot": str(snapshot.relative_to(destination)),
                       "snapshot_sha256": _digest(snapshot)})
    manifest = {"schema_version": SCHEMA_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
                "completed": True, "inputs": inputs, "implementation_sha256": _digest(__file__),
                "settings": {"window_rule": window_rule, "mode": result["summary"]["mode"],
                             "model_label": result["summary"]["model_label"]},
                "definitions": DEFINITIONS}
    from mofinder.evaluation import positive as positive_evaluator
    manifest["matching_dependency_sha256"] = {"positive.py": _digest(positive_evaluator.__file__)}
    for name, value in (("summary", result["summary"]), ("run_manifest", manifest)):
        (destination / f"{name}.json").write_text(json.dumps(_jsonable(value), indent=2, ensure_ascii=False,
                                                            allow_nan=False), encoding="utf-8")
    return destination, result["summary"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path,
                        help="Expanded negative-row CSV for one model/run.")
    parser.add_argument("--ground-truth", "--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output-dir", type=Path, help="New destination; existing folders are refused.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--positive-csv", type=Path, help="Explicit positive-assisted coverage; omitted by default.")
    parser.add_argument("--linker-molecular-weights", type=Path)
    parser.add_argument("--window-rule", choices=("open", "strict"), default="open")
    parser.add_argument("--model-label")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.validate_only:
        reference = load_reference(args.ground_truth)
        _calibration_path(reference, args.linker_molecular_weights)
        coverage = {}
        if args.csv is not None:
            _, _, coverage = load_predictions(args.csv, reference)
        if args.positive_csv is not None:
            _, _, coverage["positive_rows"] = load_predictions(args.positive_csv, reference, positive=True)
        print(json.dumps({"reference_papers": len(reference["papers"]),
                          "reference_windows": len(reference["tables"]["windows"]), **coverage}, indent=2))
        return 0
    if args.csv is None:
        parser.error("a model-specific CSV is required unless --validate-only is used")
    destination, summary = evaluate(args.csv, args.ground_truth, output_dir=args.output_dir,
        output_root=args.output_root, positive_csv=args.positive_csv,
        linker_molecular_weights=args.linker_molecular_weights,
        window_rule=args.window_rule, model_label=args.model_label)
    protocol = summary["protocol_recovery"]
    completion = summary["paper_completion"]
    print(f"Saved evaluation: {display_path(destination)}")
    print(f"Paper completion: TP={completion['TP']}; TN={completion['TN']}; "
          f"FP={completion['FP']}; FN={completion['FN']}; "
          f"evaluable={completion['classification_evaluable']}/{completion['papers_analyzed']}.")
    panel = summary["reference_row_metrics"]
    percent = lambda value: f"{value:.2%}" if value is not None else "n/a"
    print(f"Supported records={protocol['TP_rows']}; unsupported records={protocol['FP_rows']}; "
          f"recovered conditions={protocol['TP_slots']}; missed conditions={protocol['FN_slots']}; "
          f"retained successful controls={panel['TN']}/{panel['successful_controls']}.")
    print(f"Pooled output precision={percent(protocol['precision'])}; "
          f"pooled condition recall={percent(protocol['recall'])}; "
          f"coverage F1={percent(protocol['coverage_F1'])}.")
    print(f"Separate fixed-reference accuracy={percent(panel['accuracy'])} "
          f"({panel['total']} reference cases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
