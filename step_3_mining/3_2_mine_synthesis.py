"""
Step 3.2 — Concurrent MOF synthesis extraction (GPT-5 Structured Outputs)
==========================================================================
What it does
    Reads the 3-column ``(DOI, Main File, SI File)`` workbook produced by
    Step 3.1, then calls the OpenAI Responses API concurrently for every
    row.  Each call sends the full article text and optional SI text and
    asks the model to extract every primary MOF synthesis into a structured
    JSON object matching the ``ArticleExtraction`` Pydantic schema.

    Large JSON payloads are saved to disk first; the CSV output stores only
    file paths to them.  The runner is resume-safe: successfully processed
    DOIs (present in the CSV with status="ok") are skipped.

    A ``--backfill`` mode can reconstruct the CSV from previously saved JSON
    payloads without making any API calls.

Input
    ``<data>/SELECTED 7000 SI - Copy - simple.xlsx``
    (output of Step 3.1, override with ``--excel``).

Output
    ``<data>/mof_extraction.csv``    — one row per synthesis record.
    ``<data>/mof_json_store/``       — per-DOI JSON subdirectories.

    Columns in the CSV:
        doi, main_pdf, si_pdf, raw_output, parsed_json,
        article_trial_or_failure, article_trial_or_failure_notes,
        mof_name, crystal_code,
        metal_1..3 (name, abbr, amount_text, amount_value, amount_unit),
        linker_1..3 (same), modulator_1..2 (same),
        solvent_main / solvent_secondary (name, abbr, amount_text, ml),
        temperature_c, temperature_c_text, time_h, time_text,
        vessel_type, stirring,
        washing_solvent, washing_cycles, activation_text,
        activation_temp_c, activation_time_h,
        crystal_morphology, yield_percent, crystal_size,
        topology_code, metal_cluster_connectivity, unit_cell_short,
        pore_diameter_A, BET_surface_area_m2g,
        air_stable, water_stable, tga_decomposition_temp_c, applications,
        reference, status, error.

File layout (numbered sections below)
    1. Pydantic schemas          5. Row flattener
    2. File / text helpers       6. CSV I/O utilities
    3. Prompts                   7. Concurrent runner
    4. JSON persistence          8. Backfill from saved JSON
                                 9. CLI

Usage
-----
  python 3_2_mine_synthesis.py [options]

Examples:
  # Default run — gpt-5, concurrency 5
  python 3_2_mine_synthesis.py

  # Higher concurrency for large batches
  python 3_2_mine_synthesis.py --concurrency 50 --flush-every 50

  # Rebuild CSV from saved JSON (no API calls)
  python 3_2_mine_synthesis.py --backfill

Requirements
------------
  pip install openai pydantic pandas openpyxl pypdf
  set OPENAI_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
import threading
import unicodedata
import warnings
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from openai import OpenAI

try:
    from pypdf.errors import PdfReadWarning
except Exception:
    class PdfReadWarning(Warning): ...  # type: ignore[no-redef]

logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=PdfReadWarning)

from utils.text_io import read_any_text, safe_truncate
from utils.csv_io import sanitize_for_path, ensure_dir, to_oneline, read_csv_header, append_rows


# ===========================================================================
# Script paths / defaults
# ===========================================================================
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _SCRIPT_DIR.parent
_DATA_DIR   = _REPO_ROOT / "data"

DEFAULT_EXCEL_PATH = str(_DATA_DIR / "SELECTED 7000 SI - Copy - simple.xlsx")
DEFAULT_CSV_OUT    = str(_DATA_DIR / "mof_extraction.csv")
DEFAULT_JSON_DIR   = str(_DATA_DIR / "mof_json_store")


# ===========================================================================
# 1. Pydantic schemas (Structured Outputs schema — do not modify)
# ===========================================================================
NumOrText = Union[float, int, str, None]


class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reagent(StrictBase):
    """Generic reagent line with original units preserved in amount."""
    name_full: Optional[str] = Field(..., description="Full chemical name as written in the paper, e.g., 'zinc nitrate hexahydrate'.")
    abbreviation: Optional[str] = Field(..., description="Defined in the paper or widely standard, e.g., DMF, EtOH, BDC, BTC. Otherwise leave empty.")
    amount_text: Optional[str] = Field(..., description="Verbatim, original amount or concentration text exactly as reported e.g., '2.0 mmol', '0.25 M, 8 mL'")
    amount_value: Optional[float] = Field(..., description="Numeric if a single mass or mol amount is extractable. If stock solution, convert to mol/mmol or g/mg unit.")
    amount_unit: Optional[str] = Field(..., description="mmol, mg, mol, g etc.")


class Solvent(StrictBase):
    name_full: Optional[str] = Field(..., description="Solvent name, e.g., 'N,N-dimethylformamide', 'water'.")
    abbreviation: Optional[str] = Field(..., description="e.g., DMF, H2O, EtOH, MeOH, DEF, DMAc. Leave empty if not standard.")
    amount_text: Optional[str] = Field(..., description="Original text for volume or ratio, e.g., '10 mL', 'DMF/H2O 9:1 v/v'.")
    amount_value_ml: Optional[float] = Field(..., description="Volume in mL if derivable for single solvent and can be convert to ml")
    role: Literal["main", "secondary", "tertiary", "other"] = Field(...)


class Conditions(StrictBase):
    temperature_c_text: Optional[str] = Field(..., description="Verbtaim phrase or oirginal text or value with unit if explicit. If textual only (e.g., 'reflux', 'RT'), put that string.")
    temperature_c: Optional[float] = Field(..., description="Celsius if numeric")
    time_text: Optional[str] = Field(..., description="Verbtaim phrase or oirginal text for time. Hours/minutes/days if explicit. If textual only (e.g., 'overnight'), put that string.")
    time_h: Optional[float] = Field(..., description="Hours if numeric or converted")
    vessel_type: Optional[str] = Field(..., description="e.g., 'Teflon-lined autoclave', 'glass vial', 'microwave vial', 'mortar and pestle'.")
    stirring: Optional[str] = Field(..., description="e.g., 'stirred', 'static'")


class PostProcessing(StrictBase):
    washing_solvent: Optional[str] = Field(..., description="Short; comma-separated if multiple; e.g., 'DMF, MeOH'.")
    washing_cycles: Optional[str] = Field(..., description="e.g., '3×', 'three times', 'until clear'")
    activation_text: Optional[str] = Field(..., description="Verbatim text, include temperature and time if given, e.g., '120 °C under vacuum for 12 h'.")
    activation_temp_c: Optional[float] = Field(..., description="If numeric converted in degree C")
    activation_time_h: Optional[float] = Field(..., description="If numeric converted in hour")


class StructureProps(StrictBase):
    topology_code: Optional[str] = Field(..., description="RCSR 3-letter code if reported, e.g., 'pcu', 'dia'. Else leave empty.")
    metal_cluster_connectivity: Optional[str] = Field(..., description="Short phrase, e.g., 'Zr6O4(OH)4 12-connected SBU', 'oxo-bridged rod'.")
    unit_cell_short: Optional[str] = Field(..., description="Keep as one short string, e.g., 'a=25.123(3), b=..., c=..., α=..., β=..., γ=..., Pnma'.")
    pore_diameter_A: Optional[float] = Field(..., description="Pore diameter in Å or aperture if reported. Keep units if textual.")
    BET_surface_area_m2g: Optional[float] = Field(..., description="BET area if reported. Keep numeric in unit of m2/g.")
    air_stable: Optional[Literal["yes", "no", "not_reported"]] = Field(..., description="controlled vocab")
    water_stable: Optional[Literal["yes", "no", "not_reported"]] = Field(..., description="controlled vocab")
    tga_decomposition_temp_c: Optional[float] = Field(..., description="decomposition onset in deg C and numeric if given")
    applications: List[str] = Field(..., description="Short tags (three words max): water_harvesting, CO2_capture, C-H oxidation catalysis, luminescence, sensing, I2 delivery, hydrogen storage, acetylene separation")


class SynthesisRecord(StrictBase):
    # One primary MOF synthesis per item. Exclude postsynthetic modification and composites.
    mof_name: Optional[str] = Field(..., description="Common name, e.g., 'UiO-66', 'MOF-5', 'IRMOF-1'. Leave empty if not given.")
    crystal_code: Optional[str] = Field(..., description="Six-letter/number CCDC code if present ")
    metals: List[Reagent] = Field(..., description="List of metal sources. Include salts, oxides, clusters. Preserve hydration and counterions.")
    linkers: List[Reagent] = Field(..., description="List of organic linkers. Use full name and abbreviation if provided.")
    modulators: List[Reagent] = Field(..., description="Monocarboxylic acids, bases, amines, etc. If a liquid could be both solvent and modulator, treat as modulator here.")
    solvents: List[Solvent] = Field(..., description="Reaction solvents only. Label one as 'main' when obvious from text or majority fraction.")
    conditions: Conditions = Field(..., description="Reaction conditions.")
    post_processing: PostProcessing = Field(..., description="Washing and activation.")
    crystal_morphology: Optional[str] = Field(..., description="color and shape, e.g., 'blue' 'red' 'octahedra', 'rods', 'blocks'.")
    yield_percent: Optional[Union[float, str]] = Field(..., description="Percent if numeric. Else exact wording, e.g., 'quantitative'.")
    crystal_size: Optional[str] = Field(..., description="As reported, e.g., '0.20 × 0.10 × 0.05 mm', '5-10 μm'.")
    structure_properties: StructureProps = Field(..., description="Topological and property lines reported by the authors.")
    reference: str = Field(..., description="DOI string for this synthesis record, e.g., '10.1021/jacs.9b12345'.")


class ArticleExtraction(StrictBase):
    syntheses: List[SynthesisRecord] = Field(..., description="One item per primary MOF synthesis found in the article. Exclude postsynthetic modifications and non-MOF procedures.")
    trial_or_failure_reported: Literal["yes", "no"] = Field(..., description="Did the article describe trying multiple conditions in MOF synthesis that failed, or attempts that did not yield the target? This only apply to pristine MOF synthesis. Y/N.")
    trial_or_failure_notes: Optional[str] = Field(None, description="Short evidence phrase, e.g., 'screened temperatures 60-140 °C with no crystals', 'BDC gave amorphous solid'.")


# ===========================================================================
# 2. File / text helpers (local; utils.text_io imported above)
# ===========================================================================

def _empty_row(doi: str, main_pdf: str, si_pdf: str, status: str, error: str) -> Dict[str, Any]:
    return {
        "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
        "raw_output": "", "parsed_json": "",
        "article_trial_or_failure": "", "article_trial_or_failure_notes": "",
        "mof_name": "", "crystal_code": "",
        "metal_1": "", "metal_1_abbr": "", "metal_1_amount_text": "", "metal_1_amount_value": "", "metal_1_amount_unit": "",
        "metal_2": "", "metal_2_abbr": "", "metal_2_amount_text": "", "metal_2_amount_value": "", "metal_2_amount_unit": "",
        "metal_3": "", "metal_3_abbr": "", "metal_3_amount_text": "", "metal_3_amount_value": "", "metal_3_amount_unit": "",
        "linker_1": "", "linker_1_abbr": "", "linker_1_amount_text": "", "linker_1_amount_value": "", "linker_1_amount_unit": "",
        "linker_2": "", "linker_2_abbr": "", "linker_2_amount_text": "", "linker_2_amount_value": "", "linker_2_amount_unit": "",
        "linker_3": "", "linker_3_abbr": "", "linker_3_amount_text": "", "linker_3_amount_value": "", "linker_3_amount_unit": "",
        "modulator_1": "", "modulator_1_abbr": "", "modulator_1_amount_text": "", "modulator_1_amount_value": "", "modulator_1_amount_unit": "",
        "modulator_2": "", "modulator_2_abbr": "", "modulator_2_amount_text": "", "modulator_2_amount_value": "", "modulator_2_amount_unit": "",
        "solvent_main": "", "solvent_main_abbr": "", "solvent_main_amount_text": "", "solvent_main_ml": "",
        "solvent_secondary": "", "solvent_secondary_abbr": "", "solvent_secondary_amount_text": "", "solvent_secondary_ml": "",
        "temperature_c": "", "temperature_c_text": "", "time_h": "", "time_text": "", "vessel_type": "", "stirring": "",
        "washing_solvent": "", "washing_cycles": "", "activation_text": "", "activation_temp_c": "", "activation_time_h": "",
        "crystal_morphology": "", "yield_percent": "", "crystal_size": "",
        "topology_code": "", "metal_cluster_connectivity": "", "unit_cell_short": "",
        "pore_diameter_A": "", "BET_surface_area_m2g": "", "air_stable": "", "water_stable": "", "tga_decomposition_temp_c": "",
        "applications": "", "reference": doi, "status": status, "error": error,
    }


# ===========================================================================
# 3. Prompts (do not modify)
# ===========================================================================

SYSTEM_PROMPT = """You extract structured MOF synthesis data from scientific papers.

Output format:
- Return JSON that exactly matches the ArticleExtraction schema provided via text_format.
- One SynthesisRecord **per unique set of synthesis conditions**. If the same MOF is prepared under different temperatures, times, solvent ratios, reagent ratios, modulators, or methods, create one SynthesisRecord for each condition, even if reagents are otherwise identical.
- Exclude postsynthetic modification, ion exchange, ligand exchange, composites, films, pyrolysis or derived-carbons, polymer-MOF composites, shaping or pelletization steps, and any non-MOF syntheses. For non-MOF definition, see below.
- Do not include dye-loaded, encapsulated, doped, supported, coated, film, membrane, or core-shell materials, and any formulation written as "X@MOF". These are not primary MOF syntheses. Do not return them in `syntheses`.
- Set trial_or_failure_reported = "yes" if the text mentions trials that failed during MOF synthesis and screening. Non-crystalline products, amorphous solids, no product, or a screening of linkers/solvent/temperature that did not work as intended. Otherwise set "no". For other failures like failed post-synthetic modification please do not consider and say no. If "yes", put a short evidence phrase in trial_or_failure_notes. Keep it brief.


Key definitions:
- MOF is a crystalline material composed of metal ions or clusters coordinated to organic linkers through strong bonds, forming an extended periodic network that is stable and often porous. Please do not include the case of non-MOF where coordination Polymers with weak supramolecular interactions
- Metal source: metal-containing starting reagent (salts, oxides, clusters). Keep hydration and counterions, e.g., 'ZrCl4', 'Zn(NO3)2·6H2O'.
- Linker: organic bridging ligand(s). Use full name and abbreviation if present. Accept common safe abbreviations: BDC (terephthalate), BTC (benzene-1,3,5-tricarboxylate), bipy (4,4′-bipyridine), H2L/H3L labels when used by authors.
  - If the article reports *alternatives* across a series (e.g., "BDC or BDC-NH2 or BDC-SO3Na"), output **separate SynthesisRecord items**, each with **only one** of those linkers.
  - Only include multiple linkers in a single record when the framework is  described as mixed-linker in that one synthesis.
- Modulator: additives used to tune nucleation, defect density, or crystal size (e.g., acetic acid, formic acid, HCl, triethylamine). If a liquid could be both solvent and modulator, treat it as a modulator and do not list it as a solvent.
- Solvent: reaction medium. Mark one as 'main' when clear (largest fraction or named primary solvent). Others are 'secondary' or 'tertiary'. Keep original ratios or volumes.
- Amount fields: preserve the exact original units and wording in the 'amount' string (examples: '2.0 mmol', '10 mL', '0.25 M, 8 mL in DMF'). For stock solutions, record both concentration and added volume in amount, e.g., '0.10 M, 5 mL'.
- Temperature and time: if numeric, you may use numbers; if only textual terms are given, keep the phrase in the *_text fields and you may also use the textual form in temperature_c or time_h. Examples: 'reflux', 'RT', 'overnight', '3 days'.
- Vessel type: 'Teflon-lined autoclave', 'glass vial', 'microwave vial', 'planetary mill', etc.
- Washing and activation: list washing solvent(s) and cycles; activation is the final drying or solvent exchange step, keep temperature and time as written in one short phrase.
- Structure properties: only include what the authors state. Topology as a 3-letter code if given (e.g., pcu, dia). Keep unit cell as one short string. Property notes like BET m2/g, pore diameters, stability flags, and applications go here.
- Crystal code: CCDC refcode. the 6-letter/number CCDC refcode (or deposition number) **if reported**.

Ambiguity handling:
- When a chemical could be both solvent and modulator, classify as modulator.
- Keep original names. Use common solvent and linker abbreviations only if standard (DMF, DEF, DMAc, MeOH, EtOH, H2O, BDC, BTC, bipy). Otherwise leave abbreviation empty.
- If multiple distinct syntheses for the same MOF appear, create multiple SynthesisRecord items.
- If no primary MOF synthesis is present, return an empty list in 'syntheses'.
- Do not include incomplete synthesis if the metal source, linker, or solvent is missing or only referenced to prior work or ref work.
- If procedures appear in both the main text and Supporting Information, use the more detailed version.
- Always include 'reference' with the DOI string in each SynthesisRecord.
- If the author mentions the detailed procedure is given in ref xxx or previous work without showing synthesis paramters, do not include.
- Exclude composites, dye-loaded, encapsulated, doped, supported, coated, film, membrane, or core-shell materials, and any formulation written as "X@MOF". These are not primary MOF syntheses. Do not return them in `syntheses`.


Conciseness:
- Keep metal cluster connectivity, topology description, and unit cell each to a short phrase. Do not write long prose.

Follow the schema exactly. Do not include explanations outside the JSON.

"""

USER_PROMPT_TEMPLATE = """Context:
You are a professional MOF chemist and will receive the full text of an article. If Supporting Information exists, you will receive that text afterwards. Extract primary MOF syntheses only.

Metadata:
DOI: {doi}

Full article text:
<<<ARTICLE_START
{article_text}
ARTICLE_END>>>

Supporting Information (may be empty):
<<<SI_START
{si_text}
SI_END>>>
"""


# ===========================================================================
# 4. JSON persistence — save large payloads to disk
# ===========================================================================

def save_json_payloads(
    doi: str,
    raw_output: str,
    parsed_obj: ArticleExtraction,
    out_dir: str,
) -> Dict[str, Any]:
    """
    Persist raw model output and parsed extraction to disk.

    Returns a dict with keys: raw_path, article_parsed_path, syn_paths.
    """
    base = Path(out_dir) / sanitize_for_path(doi)
    ensure_dir(base)

    raw_json_path = base / "raw_output.json"
    raw_txt_path  = base / "raw_output.txt"
    try:
        candidate = json.loads(raw_output)
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(candidate, f, ensure_ascii=False, indent=2)
        raw_path = raw_json_path
    except Exception:
        with open(raw_txt_path, "w", encoding="utf-8") as f:
            f.write(raw_output if isinstance(raw_output, str) else str(raw_output))
        raw_path = raw_txt_path

    article_parsed_path = base / "article_extraction.json"
    with open(article_parsed_path, "w", encoding="utf-8") as f:
        json.dump(parsed_obj.model_dump(), f, ensure_ascii=False, indent=2)

    syn_paths: List[Path] = []
    for i, syn in enumerate(parsed_obj.syntheses or [], start=1):
        spath = base / f"synthesis_{i:03d}.json"
        with open(spath, "w", encoding="utf-8") as f:
            json.dump(syn.model_dump(), f, ensure_ascii=False, indent=2)
        syn_paths.append(spath)

    return {
        "raw_path": str(raw_path),
        "article_parsed_path": str(article_parsed_path),
        "syn_paths": [str(p) for p in syn_paths],
    }


# ===========================================================================
# 5. Row flattener — ArticleExtraction → list of CSV-row dicts
# ===========================================================================

def _pick_reagents(rgs: List[Any], n: int) -> List[Any]:
    rgs = rgs or []
    return list(rgs[:n]) + [None] * max(0, n - len(rgs))


def _pick_solvent_by_role(svs: List[Any], role: str):
    for s in svs or []:
        if getattr(s, "role", None) == role:
            return s
    return None


def flatten_row(
    doi: str,
    main_pdf: str,
    si_pdf: str,
    raw_output_path: str,
    parsed_obj: ArticleExtraction,
    syn_json_paths: List[str],
    article_parsed_path: str,
) -> List[Dict[str, Any]]:
    trial_flag  = getattr(parsed_obj, "trial_or_failure_reported", "")
    trial_notes = getattr(parsed_obj, "trial_or_failure_notes", "")

    def rg_tuple(r):
        if not r:
            return ("", "", "", "", "")
        return (
            r.name_full or "",
            r.abbreviation or "",
            r.amount_text or "",
            r.amount_value if r.amount_value is not None else "",
            r.amount_unit or "",
        )

    def sv_tuple(s):
        if not s:
            return ("", "", "", "")
        return (
            s.name_full or "",
            s.abbreviation or "",
            s.amount_text or "",
            s.amount_value_ml if s.amount_value_ml is not None else "",
        )

    rows: List[Dict[str, Any]] = []
    for idx, syn in enumerate(parsed_obj.syntheses or [], start=1):
        m1, m2, m3 = [rg_tuple(x) for x in _pick_reagents(getattr(syn, "metals", []), 3)]
        l1, l2, l3 = [rg_tuple(x) for x in _pick_reagents(getattr(syn, "linkers", []), 3)]
        md1, md2   = [rg_tuple(x) for x in _pick_reagents(getattr(syn, "modulators", []), 2)]

        sm = sv_tuple(_pick_solvent_by_role(getattr(syn, "solvents", []), "main"))
        ss = sv_tuple(_pick_solvent_by_role(getattr(syn, "solvents", []), "secondary"))

        cond = getattr(syn, "conditions", None)
        pp   = getattr(syn, "post_processing", None)
        sp   = getattr(syn, "structure_properties", None)

        rows.append({
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": raw_output_path,
            "parsed_json": syn_json_paths[idx - 1] if idx - 1 < len(syn_json_paths) else "",
            "article_trial_or_failure": trial_flag,
            "article_trial_or_failure_notes": trial_notes,
            "mof_name": syn.mof_name or "",
            "crystal_code": syn.crystal_code or "",

            "metal_1": m1[0], "metal_1_abbr": m1[1], "metal_1_amount_text": m1[2], "metal_1_amount_value": m1[3], "metal_1_amount_unit": m1[4],
            "metal_2": m2[0], "metal_2_abbr": m2[1], "metal_2_amount_text": m2[2], "metal_2_amount_value": m2[3], "metal_2_amount_unit": m2[4],
            "metal_3": m3[0], "metal_3_abbr": m3[1], "metal_3_amount_text": m3[2], "metal_3_amount_value": m3[3], "metal_3_amount_unit": m3[4],

            "linker_1": l1[0], "linker_1_abbr": l1[1], "linker_1_amount_text": l1[2], "linker_1_amount_value": l1[3], "linker_1_amount_unit": l1[4],
            "linker_2": l2[0], "linker_2_abbr": l2[1], "linker_2_amount_text": l2[2], "linker_2_amount_value": l2[3], "linker_2_amount_unit": l2[4],
            "linker_3": l3[0], "linker_3_abbr": l3[1], "linker_3_amount_text": l3[2], "linker_3_amount_value": l3[3], "linker_3_amount_unit": l3[4],

            "modulator_1": md1[0], "modulator_1_abbr": md1[1], "modulator_1_amount_text": md1[2], "modulator_1_amount_value": md1[3], "modulator_1_amount_unit": md1[4],
            "modulator_2": md2[0], "modulator_2_abbr": md2[1], "modulator_2_amount_text": md2[2], "modulator_2_amount_value": md2[3], "modulator_2_amount_unit": md2[4],

            "solvent_main": sm[0], "solvent_main_abbr": sm[1], "solvent_main_amount_text": sm[2], "solvent_main_ml": sm[3],
            "solvent_secondary": ss[0], "solvent_secondary_abbr": ss[1], "solvent_secondary_amount_text": ss[2], "solvent_secondary_ml": ss[3],

            "temperature_c": cond.temperature_c if cond else "",
            "temperature_c_text": (cond.temperature_c_text if cond else "") or "",
            "time_h": cond.time_h if cond else "",
            "time_text": (cond.time_text if cond else "") or "",
            "vessel_type": (cond.vessel_type if cond else "") or "",
            "stirring": (cond.stirring if cond else "") or "",

            "washing_solvent": (pp.washing_solvent if pp else "") or "",
            "washing_cycles": (pp.washing_cycles if pp else "") or "",
            "activation_text": (pp.activation_text if pp else "") or "",
            "activation_temp_c": (pp.activation_temp_c if pp and pp.activation_temp_c is not None else ""),
            "activation_time_h": (pp.activation_time_h if pp and pp.activation_time_h is not None else ""),

            "crystal_morphology": syn.crystal_morphology or "",
            "yield_percent": syn.yield_percent if syn.yield_percent is not None else "",
            "crystal_size": syn.crystal_size or "",

            "topology_code": (sp.topology_code if sp and sp.topology_code else ""),
            "metal_cluster_connectivity": (sp.metal_cluster_connectivity if sp and sp.metal_cluster_connectivity else ""),
            "unit_cell_short": (sp.unit_cell_short if sp and sp.unit_cell_short else ""),
            "pore_diameter_A": (sp.pore_diameter_A if sp and sp.pore_diameter_A is not None else ""),
            "BET_surface_area_m2g": (sp.BET_surface_area_m2g if sp and sp.BET_surface_area_m2g is not None else ""),
            "air_stable": (sp.air_stable if sp and sp.air_stable else ""),
            "water_stable": (sp.water_stable if sp and sp.water_stable else ""),
            "tga_decomposition_temp_c": (sp.tga_decomposition_temp_c if sp and sp.tga_decomposition_temp_c is not None else ""),
            "applications": ";".join(sp.applications) if sp and sp.applications else "",

            "reference": syn.reference,
            "status": "ok",
            "error": "",
        })

    if not rows:
        rows.append(_empty_row(doi, main_pdf, si_pdf, "ok", ""))
        rows[-1]["parsed_json"] = article_parsed_path
    return rows


# ===========================================================================
# 6. CSV I/O utilities
# ===========================================================================

def already_done_dois(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        if "status" not in df.columns:
            return set()
        ok = df["status"].astype(str).str.strip().str.lower() == "ok"
        return set(df.loc[ok, "doi"].astype(str).tolist())
    except Exception:
        return set()


def _clean_excel_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"", "nan", "none"} else s


def _valid_file_path(path_str: str, allowed_exts: Optional[set[str]] = None) -> bool:
    if not path_str:
        return False
    try:
        path = Path(path_str)
        if allowed_exts is not None and path.suffix.lower() not in allowed_exts:
            return False
        return path.is_file()
    except (OSError, ValueError):
        return False


# ===========================================================================
# 7. Concurrent runner
# ===========================================================================

def _extract_one(client: OpenAI, doi: str, main_pdf: str, si_pdf: str, model_name: str = "gpt-5"):
    main_text = read_any_text(main_pdf)
    si_text   = read_any_text(si_pdf) if si_pdf else ""
    user_msg  = USER_PROMPT_TEMPLATE.format(
        doi=doi,
        article_text=safe_truncate(main_text),
        si_text=safe_truncate(si_text),
    )
    resp = client.responses.parse(
        model=model_name,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        text_format=ArticleExtraction,
    )
    raw_output = resp.output_text or json.dumps(resp.model_dump(), ensure_ascii=False)
    parsed: ArticleExtraction = resp.output_parsed
    return raw_output, parsed


def _extract_with_retry(client: OpenAI, doi: str, main_pdf: str, si_pdf: str, model_name: str):
    try:
        return _extract_one(client, doi, main_pdf, si_pdf, model_name)
    except Exception:
        time.sleep(0.5)
        return _extract_one(client, doi, main_pdf, si_pdf, model_name)


def _process_item(item: Dict[str, str], model: str, json_out_dir: str) -> Dict[str, Any]:
    """Worker that handles one DOI; creates its own OpenAI client for thread safety."""
    doi      = item["doi"]
    main_pdf = item["main_pdf"]
    si_pdf   = item["si_pdf"]
    t0 = time.perf_counter()
    print(f"START [{doi}] on {threading.current_thread().name}")
    client = OpenAI()
    try:
        raw, parsed = _extract_with_retry(client, doi, main_pdf, si_pdf, model)
        paths = save_json_payloads(doi, raw, parsed, json_out_dir)
        synth_count = len(parsed.syntheses or [])
        rows = flatten_row(
            doi=doi,
            main_pdf=main_pdf,
            si_pdf=si_pdf,
            raw_output_path=paths["raw_path"],
            parsed_obj=parsed,
            syn_json_paths=paths["syn_paths"],
            article_parsed_path=paths["article_parsed_path"],
        )
        dt = time.perf_counter() - t0
        print(f"DONE  [{doi}] in {dt:.2f}s, syntheses parsed: {synth_count}")
        return {"doi": doi, "rows": rows, "synth_count": synth_count,
                "status": "ok", "error": "", "elapsed": dt}
    except Exception as e:
        dt = time.perf_counter() - t0
        print(f"[ERROR] {doi}: {e}")
        return {"doi": doi, "rows": [_empty_row(doi, main_pdf, si_pdf, "failed", str(e))],
                "synth_count": 0, "status": "failed", "error": str(e), "elapsed": dt}


def run(
    excel_path: str,
    csv_out: str = DEFAULT_CSV_OUT,
    start_row: int = 0,
    model: str = "gpt-5",
    concurrency: int = 5,
    flush_every: int = 5,
    json_out_dir: str = DEFAULT_JSON_DIR,
) -> None:
    """
    Concurrent runner — reads Excel, skips done DOIs, processes remainder.

    Parameters
    ----------
    excel_path  : path to Excel with columns DOI, Main File, SI File.
    csv_out     : output CSV file.
    start_row   : zero-based start row in the Excel.
    model       : OpenAI model name (default gpt-5).
    concurrency : parallel OpenAI calls (default 5).
    flush_every : write CSV every N completed DOIs.
    json_out_dir: folder for raw + parsed JSON payloads.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    ensure_dir(Path(json_out_dir))
    df = pd.read_excel(excel_path)
    for col in ["DOI", "Main File", "SI File"]:
        if col not in df.columns:
            raise ValueError(f"Missing column in Excel: {col}")

    done  = already_done_dois(csv_out)
    items: List[Dict[str, str]] = []
    skipped_invalid = 0
    for _, row in df.iloc[start_row:].iterrows():
        doi = _clean_excel_cell(row["DOI"])
        if doi in done:
            continue
        main_pdf = _clean_excel_cell(row["Main File"])
        si_pdf   = _clean_excel_cell(row["SI File"])
        if not doi or not _valid_file_path(main_pdf, {".pdf"}):
            skipped_invalid += 1
            continue
        if si_pdf and not _valid_file_path(si_pdf, {".pdf", ".docx", ".doc"}):
            si_pdf = ""
        items.append({"doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf})

    n_total = len(items)
    if skipped_invalid:
        print(f"Skipped {skipped_invalid} row(s) with blank DOI or missing Main File.")
    print(f"Total to process: {n_total}")
    if n_total == 0:
        print("Nothing to do.")
        return

    t0 = time.perf_counter()
    processed = 0
    buffer: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_process_item, item, model, json_out_dir) for item in items]

        for fut in as_completed(futures):
            result = fut.result()
            buffer.extend(result["rows"])
            processed += 1
            avg_dt    = (time.perf_counter() - t0) / processed
            remaining = n_total - processed
            eta_sec   = max(0.0, remaining * avg_dt)
            print(f"[{processed}/{n_total}] {result['doi']} in {result['elapsed']:.2f}s, "
                  f"syntheses: {result['synth_count']}, ETA {eta_sec/60:.1f} min")

            if len(buffer) >= flush_every:
                written, skipped = append_rows(csv_out, buffer)
                print(f"Flushed {written} row(s) to {csv_out} (skipped {skipped})")
                buffer = []

    if buffer:
        written, skipped = append_rows(csv_out, buffer)
        print(f"Final flush wrote {written} row(s) to {csv_out} (skipped {skipped})")

    total_dt = time.perf_counter() - t0
    avg_per  = (total_dt / processed) if processed else 0.0
    print(f"All done. {processed}/{n_total} in {total_dt/60:.1f} min (avg {avg_per:.2f}s/row)")
    print(f"JSON payloads stored under: {json_out_dir}/<sanitized DOI>/")


# ===========================================================================
# 8. Backfill from saved JSON — reconstruct CSV without API calls
# ===========================================================================

def _pick_reagents_dict(lst: Optional[List[Dict[str, Any]]], n: int) -> List[Optional[Dict[str, Any]]]:
    lst = lst or []
    out = list(lst[:n])
    while len(out) < n:
        out.append(None)
    return out


def _pick_solvent_by_role_dict(lst: Optional[List[Dict[str, Any]]], role: str) -> Optional[Dict[str, Any]]:
    for s in lst or []:
        if (s or {}).get("role") == role:
            return s
    return None


def _rg_tuple_dict(r: Optional[Dict[str, Any]]):
    if not r:
        return ("", "", "", "", "")
    return (
        r.get("name_full") or "",
        r.get("abbreviation") or "",
        r.get("amount_text") or "",
        r.get("amount_value") if r.get("amount_value") is not None else "",
        r.get("amount_unit") or "",
    )


def _sv_tuple_dict(s: Optional[Dict[str, Any]]):
    if not s:
        return ("", "", "", "")
    return (
        s.get("name_full") or "",
        s.get("abbreviation") or "",
        s.get("amount_text") or "",
        s.get("amount_value_ml") if s.get("amount_value_ml") is not None else "",
    )


def _flatten_rows_from_dir(doi: str, main_pdf: str, si_pdf: str, art_dir: Path) -> List[Dict[str, Any]]:
    raw_json = art_dir / "raw_output.json"
    raw_txt  = art_dir / "raw_output.txt"
    raw_path = raw_json if raw_json.exists() else (raw_txt if raw_txt.exists() else None)

    article_parsed_path = art_dir / "article_extraction.json"
    syn_paths = sorted(art_dir.glob("synthesis_*.json"))

    trial_flag  = ""
    trial_notes = ""
    syntheses: List[Dict[str, Any]] = []

    if article_parsed_path.exists():
        try:
            article_data = json.loads(article_parsed_path.read_text(encoding="utf-8"))
            trial_flag   = article_data.get("trial_or_failure_reported", "") or ""
            trial_notes  = article_data.get("trial_or_failure_notes", "") or ""
            syntheses    = article_data.get("syntheses") or []
            if not syntheses and syn_paths:
                syntheses = []
                for sp in syn_paths:
                    try:
                        syntheses.append(json.loads(sp.read_text(encoding="utf-8")))
                    except Exception:
                        continue
        except Exception:
            if syn_paths:
                syntheses = []
                for sp in syn_paths:
                    try:
                        syntheses.append(json.loads(sp.read_text(encoding="utf-8")))
                    except Exception:
                        continue

    rows: List[Dict[str, Any]] = []
    for idx, syn in enumerate(syntheses or [], start=1):
        m1, m2, m3 = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn.get("metals") or [], 3)]
        l1, l2, l3 = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn.get("linkers") or [], 3)]
        md1, md2   = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn.get("modulators") or [], 2)]
        sm  = _sv_tuple_dict(_pick_solvent_by_role_dict(syn.get("solvents") or [], "main"))
        ss  = _sv_tuple_dict(_pick_solvent_by_role_dict(syn.get("solvents") or [], "secondary"))
        cond = syn.get("conditions") or {}
        pp   = syn.get("post_processing") or {}
        sp   = syn.get("structure_properties") or {}

        row = {
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": str(raw_path) if raw_path else "",
            "parsed_json": (
                str(syn_paths[idx - 1]) if idx - 1 < len(syn_paths)
                else str(article_parsed_path) if article_parsed_path.exists() else ""
            ),
            "article_trial_or_failure": trial_flag,
            "article_trial_or_failure_notes": trial_notes,
            "mof_name": syn.get("mof_name") or "",
            "crystal_code": syn.get("crystal_code") or "",

            "metal_1": m1[0], "metal_1_abbr": m1[1], "metal_1_amount_text": m1[2], "metal_1_amount_value": m1[3], "metal_1_amount_unit": m1[4],
            "metal_2": m2[0], "metal_2_abbr": m2[1], "metal_2_amount_text": m2[2], "metal_2_amount_value": m2[3], "metal_2_amount_unit": m2[4],
            "metal_3": m3[0], "metal_3_abbr": m3[1], "metal_3_amount_text": m3[2], "metal_3_amount_value": m3[3], "metal_3_amount_unit": m3[4],

            "linker_1": l1[0], "linker_1_abbr": l1[1], "linker_1_amount_text": l1[2], "linker_1_amount_value": l1[3], "linker_1_amount_unit": l1[4],
            "linker_2": l2[0], "linker_2_abbr": l2[1], "linker_2_amount_text": l2[2], "linker_2_amount_value": l2[3], "linker_2_amount_unit": l2[4],
            "linker_3": l3[0], "linker_3_abbr": l3[1], "linker_3_amount_text": l3[2], "linker_3_amount_value": l3[3], "linker_3_amount_unit": l3[4],

            "modulator_1": md1[0], "modulator_1_abbr": md1[1], "modulator_1_amount_text": md1[2], "modulator_1_amount_value": md1[3], "modulator_1_amount_unit": md1[4],
            "modulator_2": md2[0], "modulator_2_abbr": md2[1], "modulator_2_amount_text": md2[2], "modulator_2_amount_value": md2[3], "modulator_2_amount_unit": md2[4],

            "solvent_main": sm[0], "solvent_main_abbr": sm[1], "solvent_main_amount_text": sm[2], "solvent_main_ml": sm[3],
            "solvent_secondary": ss[0], "solvent_secondary_abbr": ss[1], "solvent_secondary_amount_text": ss[2], "solvent_secondary_ml": ss[3],

            "temperature_c": cond.get("temperature_c", "") if cond.get("temperature_c") is not None else "",
            "temperature_c_text": cond.get("temperature_c_text") or "",
            "time_h": cond.get("time_h", "") if cond.get("time_h") is not None else "",
            "time_text": cond.get("time_text") or "",
            "vessel_type": cond.get("vessel_type") or "",
            "stirring": cond.get("stirring") or "",

            "washing_solvent": pp.get("washing_solvent") or "",
            "washing_cycles": pp.get("washing_cycles") or "",
            "activation_text": pp.get("activation_text") or "",
            "activation_temp_c": pp.get("activation_temp_c") if pp.get("activation_temp_c") is not None else "",
            "activation_time_h": pp.get("activation_time_h") if pp.get("activation_time_h") is not None else "",

            "crystal_morphology": syn.get("crystal_morphology") or "",
            "yield_percent": syn.get("yield_percent") if syn.get("yield_percent") is not None else "",
            "crystal_size": syn.get("crystal_size") or "",

            "topology_code": sp.get("topology_code") or "",
            "metal_cluster_connectivity": sp.get("metal_cluster_connectivity") or "",
            "unit_cell_short": sp.get("unit_cell_short") or "",
            "pore_diameter_A": sp.get("pore_diameter_A") if sp.get("pore_diameter_A") is not None else "",
            "BET_surface_area_m2g": sp.get("BET_surface_area_m2g") if sp.get("BET_surface_area_m2g") is not None else "",
            "air_stable": sp.get("air_stable") or "",
            "water_stable": sp.get("water_stable") or "",
            "tga_decomposition_temp_c": sp.get("tga_decomposition_temp_c") if sp.get("tga_decomposition_temp_c") is not None else "",
            "applications": (";".join(sp.get("applications") or [])
                             if isinstance(sp.get("applications"), list)
                             else (sp.get("applications") or "")),

            "reference": syn.get("reference") or doi,
            "status": "ok", "error": "",
        }
        rows.append(row)

    if not rows:
        r = _empty_row(doi, main_pdf, si_pdf, "ok", "")
        r["raw_output"] = str(raw_path) if raw_path else ""
        r["parsed_json"] = str(article_parsed_path) if article_parsed_path.exists() else ""
        rows.append(r)

    return rows


def backfill_from_json(
    excel_path: str,
    json_out_dir: str = DEFAULT_JSON_DIR,
    csv_out: str = DEFAULT_CSV_OUT,
    flush_every: int = 50,
) -> None:
    """
    Reconstruct ``csv_out`` from saved JSON payloads without making API calls.

    Useful for recovery after a crash or to rebuild from an existing
    ``mof_json_store/`` directory.
    """
    df = pd.read_excel(excel_path)
    for col in ["DOI", "Main File", "SI File"]:
        if col not in df.columns:
            raise ValueError(f"Missing column in Excel: {col}")

    done = already_done_dois(csv_out)
    base = Path(json_out_dir)

    total = 0
    written_total = 0
    skipped_total = 0
    missing_json  = 0
    missing_list: List[str] = []
    buffer: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        doi = str(row["DOI"]).strip()
        if not doi or doi in done:
            continue
        main_pdf = str(row["Main File"]).strip()
        si_pdf   = str(row["SI File"]).strip() if pd.notna(row["SI File"]) else ""

        art_dir = base / sanitize_for_path(doi)
        if not art_dir.exists():
            missing_json += 1
            missing_list.append(doi)
            continue

        try:
            rows = _flatten_rows_from_dir(doi, main_pdf, si_pdf, art_dir)
            buffer.extend(rows)
            total += 1
            if len(buffer) >= flush_every:
                w, s = append_rows(csv_out, buffer)
                written_total += w
                skipped_total += s
                buffer = []
                print(f"[FLUSH] wrote={w} skipped={s} total_written={written_total} processed={total}")
        except Exception as e:
            r = _empty_row(doi, main_pdf, si_pdf, "failed", str(e))
            buffer.append(r)

    if buffer:
        w, s = append_rows(csv_out, buffer)
        written_total += w
        skipped_total += s
        print(f"[FINAL FLUSH] wrote={w} skipped={s}")

    print(f"Backfill complete. processed={total} written={written_total} "
          f"skipped={skipped_total} json_missing={missing_json} → {csv_out}")

    if missing_list:
        miss_path = Path(csv_out).parent / "missing_json_dois.txt"
        miss_path.write_text("\n".join(missing_list), encoding="utf-8")
        print(f"Missing JSON DOIs written to: {miss_path}")


# ===========================================================================
# 9. CLI
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Step 3.2 — Concurrent MOF synthesis extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--excel", default=DEFAULT_EXCEL_PATH,
                        help=f"Input Excel (DOI, Main File, SI File) (default: {DEFAULT_EXCEL_PATH})")
    parser.add_argument("--csv-out", default=DEFAULT_CSV_OUT,
                        help=f"Output CSV path (default: {DEFAULT_CSV_OUT})")
    parser.add_argument("--model", default="gpt-5",
                        help="OpenAI model name (default: gpt-5)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Parallel API calls (default: 5)")
    parser.add_argument("--flush-every", type=int, default=5,
                        help="Write CSV after every N completed DOIs (default: 5)")
    parser.add_argument("--json-dir", default=DEFAULT_JSON_DIR,
                        help=f"Directory for JSON payload files (default: {DEFAULT_JSON_DIR})")
    parser.add_argument("--start-row", type=int, default=0,
                        help="Zero-based start row in the Excel (default: 0)")
    parser.add_argument("--backfill", action="store_true",
                        help="Reconstruct CSV from saved JSON payloads (no API calls)")
    parser.add_argument("--backfill-flush", type=int, default=50,
                        help="Flush interval for backfill mode (default: 50)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.backfill:
        backfill_from_json(
            excel_path=args.excel,
            json_out_dir=args.json_dir,
            csv_out=args.csv_out,
            flush_every=args.backfill_flush,
        )
    else:
        run(
            excel_path=args.excel,
            csv_out=args.csv_out,
            start_row=args.start_row,
            model=args.model,
            concurrency=args.concurrency,
            flush_every=args.flush_every,
            json_out_dir=args.json_dir,
        )
