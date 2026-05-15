from __future__ import annotations

from typing import Optional


def build_prompt(
    title: str,
    source: str,
    author_keywords: Optional[str],
    keywords_plus: Optional[str],
    abstract: str,
) -> str:
    """Build the classification prompt from paper metadata fields."""
    title           = title or ""
    source          = source or ""
    author_keywords = author_keywords or ""
    keywords_plus   = keywords_plus or ""
    abstract        = abstract or ""
    return f"""
You are a domain expert in metal–organic frameworks (MOFs).
Given the paper info (title, keywords, abstract), output a SINGLE uppercase letter:

Y = The abstract indicates (explicitly OR implicitly) an experimental synthesis of a MOF via a TRADITIONAL **solution-phase** route (solvothermal, hydrothermal, **ambient/room-temperature**, slow diffusion/layering) in common solvents (water/alcohols/DMF/DEF/DMAc; mixed solvents; acids/bases as modulators). Explicit numeric conditions are **not required** in the abstract if synthesis is clearly stated or strongly implied.

Treat the following as **strong positive cues** (any one suffices unless an explicit exclusion appears):
  • **Named MOF + synthesis verb** (e.g., "synthesized/prepared/obtained MOF-5/MOF-74/MOF-177/MOF-199/IRMOF-0; UiO/MIL/ZIF/HKUST/PCN/NU/DUT").
  • **Announcement of new MOF(s)** (e.g., "we report the synthesis of MOF-519 and MOF-520").
  • **Structure/porosity readouts on a new MOF** (SCXRD/PXRD of the framework; BET/adsorption measurements), which imply executed synthesis and usually reported conditions.
  • **Direct solution-phase cues**: solvothermal/hydrothermal/diffusion/room-temperature solution, common solvents, modulators, crystal growth/yield.

Weaker positive cues (two or more suffice if no strong cue): mention of **both** a metal source/cluster and a multidentate linker; solvent/modulator/time/temperature words without explicit "synthesized"; references to optimization of synthetic variables.

N = Otherwise, or if any **explicit** exclusion is present:
  mechanochemical/ball-milling/LAG, microwave, sonochemical, electrochemical, vapor-phase CVD/ALD, **ionothermal as primary medium**, microfluidic/flow, plasma, aerosol/spray; film-only growth; computational/review; MOF-derived materials; PSM-only; non-porous 1D/2D coordination polymers; non-MOFs (MOC/MOP/COF/HOF/SOF/PAF/PPN/POF).

Decision protocol (internal, do not output):
  1) If explicit exclusion → N.
  2) If any **strong positive** → Y.
  3) Else if ≥2 weaker positives → Y.
  4) Else → N.

Return ONLY 'Y' or 'N' (one character). No punctuation, words, or explanation.

TITLE: {title}
SOURCE: {source}
AUTHOR KEYWORDS: {author_keywords}
KEYWORDS PLUS: {keywords_plus}
ABSTRACT: {abstract}
""".strip()
