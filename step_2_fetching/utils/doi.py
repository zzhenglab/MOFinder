"""
DOI helpers shared by Step 2.1 / 2.2.

These functions answer four questions:
  - "Is the publisher one we have a download flow for?"        publisher_key()
  - "What URL should we navigate to for this DOI?"             doi_to_link()
  - "What filename / file stem should the saved file have?"    doi_to_filename(),
                                                                doi_to_base(),
                                                                doi_stem()
  - "Which journal does this DOI belong to (5-char prefix)?"   doi_journal_key()
                                                                — used to fast-skip
                                                                rows after N journal-
                                                                wide failures.
"""
from __future__ import annotations

import re
from typing import Optional


# ===========================================================================
# Publisher names we have hand-written download flows for.
# Order matters in startswith() fallback path of publisher_key().
# ===========================================================================
SUPPORTED_PREFIXES = [
    "WILEY",
    "AMER CHEMICAL SOC",
    "ROYAL SOC CHEMISTRY",
    "SPRINGER",
    "ELSEVIER",
]

# Canonical key -> regex patterns. Used by publisher_key() to map free-form
# Publisher strings ("Springer Nature", "John Wiley", "ACS", ...) to one of
# the SUPPORTED_PREFIXES.
PUBLISHER_ALIASES = {
    "SPRINGER": [
        r"\bSPRINGER\b",
        r"\bSPRINGER NATURE\b",
        r"\bNATURE\b",
        r"\bNATURE RESEARCH\b",
        r"\bNATURE PUBLISHING GROUP\b",
    ],
    "WILEY": [
        r"\bWILEY\b",
        r"\bJOHN WILEY\b",
        r"\bWILEY-VCH\b",
    ],
    "AMER CHEMICAL SOC": [
        r"\bAMERICAN CHEMICAL SOCIETY\b",
        r"\bAMER CHEMICAL SOC\b",
        r"\bACS\b",
    ],
    "ROYAL SOC CHEMISTRY": [
        r"\bROYAL SOC(?:IETY)? CHEM(?:ISTRY)?\b",
        r"\bRSC\b",
    ],
    "ELSEVIER": [
        r"\bELSEVIER\b",
        r"\bCELL PRESS\b",
        r"\bTHE LANCET\b",
        r"\bSCIENTIA\b",
    ],
}


# ===========================================================================
# Publisher detection
# ===========================================================================
def normalize_pub(pub_value: str) -> str:
    """Uppercase, strip, fold smart quotes, and collapse runs of whitespace."""
    if not isinstance(pub_value, str):
        return ""
    s = pub_value.strip().replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def publisher_key(pub_value: str, use_aliases: bool = True) -> Optional[str]:
    """
    Map a free-form Publisher cell to one of SUPPORTED_PREFIXES, or None.

    With ``use_aliases=True`` (the default) the PUBLISHER_ALIASES
    regex table runs first; falls back to ``key in normalized_value``.
    With ``use_aliases=False`` only the strict ``startswith`` check is used.
    """
    p = normalize_pub(pub_value)
    if not p:
        return None

    if use_aliases:
        for key, patterns in PUBLISHER_ALIASES.items():
            for pat in patterns:
                if re.search(pat, p):
                    return key
        for key in SUPPORTED_PREFIXES:
            if key in p:
                return key
        return None

    for key in SUPPORTED_PREFIXES:
        if p.startswith(key):
            return key
    return None


# ===========================================================================
# DOI <-> URL / filename
# ===========================================================================
def doi_to_link(doi: str) -> str:
    """DOI string -> https URL to navigate to. Empty if DOI is blank."""
    doi = str(doi).strip()
    if not doi or doi.lower() == "nan":
        return ""
    if doi.lower().startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def doi_to_filename(doi: str) -> str:
    """
    DOI -> filename for Step 2.1 (main article PDF).
    Replaces ``/`` with ``_``, scrubs other path-invalid chars, appends ``.pdf``.
    """
    base = str(doi).strip().replace("/", "_")
    base = re.sub(r'[<>:"\\|?*\n\r\t]', "_", base)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def doi_to_base(doi: str) -> str:
    """DOI -> sanitized filename stem (no extension). Used by Step 2.2."""
    base = str(doi).strip().replace("/", "_")
    base = re.sub(r'[<>:"\\|?*\n\r\t]', "_", base)
    return base


def doi_stem(doi: str) -> str:
    """DOI -> ``<base>_SI`` stem used for Step 2.2 saved files."""
    return doi_to_base(doi) + "_SI"


def doi_journal_key(doi: str) -> str:
    """
    Reduce a DOI to a coarse 'journal key' for the journal-fast-skip rule.

    Format: ``<everything before '/'> + '/' + first 5 chars after '/'`` (lowercase).
    Example: ``10.1016/j.ica.2018.05.024`` -> ``10.1016/j.ica``.
    Empty string if the DOI has no ``/``.
    """
    if not doi or "/" not in doi:
        return ""
    pfx, sfx = doi.split("/", 1)
    sfx5 = sfx[:5] if len(sfx) >= 5 else sfx
    return f"{pfx}/{sfx5}".lower()
