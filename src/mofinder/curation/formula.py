"""Element counts and molar masses for normalized precursor formulas."""
import re

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
    if s is None or str(s).strip().lower() in {"", "nan", "none"}: return s
    t = str(s)
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
        # A leading coefficient applies to the complete dot-separated fragment.
        # For example, 6H2O contributes H12O6, not H12O.
        coefficient, position = _read_num(p, 0)
        if coefficient is None:
            coefficient, position = 1.0, 0
        seg_counts = _parse_segment(p[position:], coefficient)
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

