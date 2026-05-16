"""
Step 3.3 — Negative-data mining (failed MOF synthesis conditions)
=================================================================
What it does
    Reads ``mof_extraction.csv`` (from Step 3.2) and the 3-column Excel
    workbook (from Step 3.1).  For every DOI where
    ``article_trial_or_failure == "yes"``, it calls GPT-5 with reasoning
    effort "medium" to build a *modification plan*: a structured list of
    alternative conditions (metal, linker, modulator, solvent, temperature,
    time) that the article implies are non-working.

    A second task ("enumerate") expands each plan into one CSV row per
    enumerated (combinatorial) failed condition, referencing the original
    success synthesis JSON from Step 3.2.

    Both tasks are resume-safe: successfully processed DOIs are skipped.

Input (mine task)
    ``<data>/SELECTED 7000 SI - Copy - simple.xlsx``  (output of Step 3.1)
    ``<data>/mof_extraction.csv``                     (output of Step 3.2)
    ``<data>/mof_json_store/``                        (output of Step 3.2)

Output (mine task)
    ``<data>/mof_extraction_failplans.csv``  — one row per (doi, base).
    ``<data>/mof_negative_plan_store/``      — JSON payloads per DOI.
    ``<data>/mof_trials_yes_7.csv``          — 7-column summary of YES DOIs.

Input (enumerate task)
    ``<data>/mof_extraction_failplans.csv``   (output of mine task)
    ``<data>/mof_json_store/``               (output of Step 3.2)

Output (enumerate task)
    ``<data>/mof_extraction_failures_enum.csv`` — one row per enumerated
                                                   failed condition.
    ``<data>/mof_negative_enum_store/``         — per-combo JSON files.

File layout (numbered sections below)
    1. Pydantic schemas          5. Worker & concurrent runner
    2. Prompts                   6. Failure enumeration
    3. JSON I/O helpers          7. CLI
    4. CSV helpers

Usage
-----
  python 3_3_mine_negative.py [options]

Examples:
  # Run both tasks sequentially (default)
  python 3_3_mine_negative.py

  # Only mine negative plans
  python 3_3_mine_negative.py --task mine

  # Only enumerate (plan CSV must already exist)
  python 3_3_mine_negative.py --task enumerate

  # Test run: only process first 5 DOIs
  python 3_3_mine_negative.py --task mine --quick-n 5

  # Dry-run: see which DOIs would be processed
  python 3_3_mine_negative.py --task mine --dry-run

Requirements
------------
  pip install openai pydantic pandas openpyxl pypdf
  set OPENAI_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import logging
import os
import re
import time
import threading
import unicodedata
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import pandas as pd
from pandas.errors import DtypeWarning
from pydantic import BaseModel, ConfigDict, Field
from openai import OpenAI

warnings.filterwarnings("ignore", category=DtypeWarning)

try:
    from pypdf.errors import PdfReadWarning
except Exception:
    class PdfReadWarning(Warning): ...  # type: ignore[no-redef]

logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=PdfReadWarning)

from utils.text_io import read_any_text, safe_truncate
from utils.csv_io import (sanitize_for_path, ensure_dir,
                          to_oneline, read_csv_header, append_rows)


# ===========================================================================
# Script paths / defaults
# ===========================================================================
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _SCRIPT_DIR.parent
_DATA_DIR   = _REPO_ROOT / "data"

DEFAULT_EXCEL_PATH    = str(_DATA_DIR / "SELECTED 7000 SI - Copy - simple.xlsx")
DEFAULT_POSITIVE_CSV  = str(_DATA_DIR / "mof_extraction.csv")
DEFAULT_FAILPLAN_CSV  = str(_DATA_DIR / "mof_extraction_failplans.csv")
DEFAULT_NEG_JSON_DIR  = str(_DATA_DIR / "mof_negative_plan_store")
DEFAULT_SUCCESS_DIR   = str(_DATA_DIR / "mof_json_store")
DEFAULT_ENUM_JSON_DIR = str(_DATA_DIR / "mof_negative_enum_store")
DEFAULT_ENUM_CSV      = str(_DATA_DIR / "mof_extraction_failures_enum.csv")


# ===========================================================================
# 1. Pydantic schemas — negative plan (do not modify)
# ===========================================================================

class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metal1Option(StrictBase):
    name_full: str = Field(..., description="e.g., 'ZrCl4', 'Zn(NO3)2·6H2O', 'CuCl2·2H2O'")
    abbreviation: Optional[str] = Field(None, description="if given, else empty")
    amount_value: Optional[float] = Field(None, description="numeric if possible")
    amount_unit: Optional[str] = Field(None, description="mmol, mol, mg, g")


class Linker1Option(StrictBase):
    name_full: str = Field(..., description="e.g., 'terephthalic acid', 'H2BDC-NH2'")
    abbreviation: Optional[str] = Field(None)
    amount_value: Optional[float] = Field(None)
    amount_unit: Optional[str] = Field(None, description="mmol, mol, mg, g")


class Modulator1Option(StrictBase):
    name_full: str = Field(..., description="e.g., acetic acid, formic acid, HNO3, TEA")
    abbreviation: Optional[str] = Field(None)
    amount_value: Optional[float] = Field(None)
    amount_unit: Optional[str] = Field(None, description="mmol, mol, mL, eq (write the numeric value and unit text exactly as article practice if used)")


class SolventMainOption(StrictBase):
    name_full: str = Field(..., description="e.g., DMF, DEF, DMAc, H2O, EtOH")
    abbreviation: Optional[str] = Field(None)
    amount_value_ml: Optional[float] = Field(None, description="volume in mL if derivable")


class VariationSet(StrictBase):
    metal_1: List[Metal1Option] = Field(default_factory=list)
    linker_1: List[Linker1Option] = Field(default_factory=list)
    modulator_1: List[Modulator1Option] = Field(default_factory=list)
    solvent_main: List[SolventMainOption] = Field(default_factory=list)
    temperature_c: List[float] = Field(default_factory=list)
    time_h: List[float] = Field(default_factory=list)


class BaseModificationPlan(StrictBase):
    based_on_success_index: int = Field(..., description="1-based index referencing the provided success JSON list")
    mof_name: Optional[str] = Field(None, description="carry from success if available")
    modification_notes: str = Field(..., description="overall summary for this base: what is varied")
    variations: VariationSet = Field(..., description="lists of options per class")


class PaperModificationPlan(StrictBase):
    rationale_overall: str = Field(..., description="Up to 50 words. Paper-level reasoning. Include the attempted MOF/compound names.")
    plans: List[BaseModificationPlan] = Field(..., description="One item per success JSON you varied. If none, return empty list.")


# ===========================================================================
# 2. Prompts (do not modify)
# ===========================================================================

ALLOWED_CHANGED_SECTIONS = ["metal_1", "linker_1", "modulator_1", "solvent_main", "conditions.temperature", "conditions.time"]

NEG_SYSTEM_PROMPT = f"""
You are a professional MOF chemist. Build a NEGATIVE-CONDITION PLAN for solvothermal MOF synthesis.

Return JSON that exactly matches the PaperModificationPlan schema.

Use ALL provided successful syntheses as bases. For each BaseModificationPlan:
- Pick one success by index (1-based). Conceptually copy it, then propose options in these classes only: metal_1, linker_1, modulator_1, solvent_main, temperature_c, time_h.
- Put options in LISTS inside the Variations object. If a class should not change, leave its list empty.
- Fill amounts and units exactly as the article uses when possible. If a failed alternative lacks explicit amounts, copy the success stoichiometry or volumes for that swap. If this cannot be done credibly, leave numeric fields empty rather than guessing.

Evidence and inclusion rules (ranked):
1) Direct failures stated in main text, tables, figures, or SI. Always include these as options.
2) Bounded statements such as "only 100–120 °C worked", "shorter times gave no crystals", "only DMF works as solvent". Include a few concrete options that fall outside the allowed window and are clearly implied to fail. Choose boundary points and at most one midpoint per side.
3) High-throughput or grid screens where outcomes are reported. Include failed settings that appear in the grid or that the authors say "all others failed". If a grid is not exhaustive, do not invent unlisted categories.
4) Minimal inference allowed only when the article explicitly frames a closed set or rule. Example: "only linker A works under protocol P" allows listing the other linkers from the paper under the same protocol P as failed. Do not introduce metals, linkers, solvents, or modulators that are never named in the article or SI.

Inclusion and coverage:
- Include every explicitly tested failed condition from the main text, tables, figures, SI, and any high throughput or grid screening.
- If a grid or screening scans metals vs linkers or other factors under a shared base protocol or similar conditions, treat unreported or omitted combinations as likely non-working under that same base protocol. Create rows for those missing combinations by swapping the relevant component(s) while keeping other fields identical. If the paper is ambiguous, skip.
- If formation requires a combination (example: solvent X + modulator Y + temperature Z), generate failures where exactly one of those factors is changed and the rest match the success. But be consistent with the choice of each parameter the author reports. For example, do not invent a new temperature if not mentioned in paper even for other compounds.
- Do not add new reagents or solvents that never appear in the article or SI. Modulators must be those named by the authors. If the text says "acid additive" without naming which, use only acids that are actually used elsewhere in this same paper.
- When authors define a narrow viable window (example: only pH 5-7 works), create multiple outside-window failures by changing realistic modulators and their loadings that alter acidity or basicity. Use choices consistent with MOF practice and the paper's context. Prefer modulators mentioned by the authors or used in similar syntheses in the same article.
- When authors mention alternative linkers or modulators that did not work, infer specific identities and amounts from the text and closely related context in the paper.

Amounts, units, and ratios:
- Always fill amount_value/unit when possible. Use the article's units exactly (mmol, mol, mg, g, mL, M). No parentheses or inline notes.
- If the article gives a range or several options fail, output multiple concrete options rather than a range.
- When changing temperature, produce several realistic failing points guided by the paper (for example: below the stated threshold, above the stated maximum, and one intermediate).
- For solvent composition, vary specific ratios and volumes as the authors discuss or imply. If only one ratio works, create several non-working ratios.
- For stoichiometry, vary metal:linker and metal:modulator ratios in realistic steps around the successful ratio (for example: halve, double, and one intermediate). Reflect these changes by adjusting the underlying amounts and solvent volumes as reported.

How to vary each class:
- temperature_c: pick boundary failures and one midpoint on each side of the reported working window. Example: if 100–120 °C works and text says lower gives no crystals, include 80 and 60 °C. If higher fails, include a higher point. You can also get choice based on other conditions the author tried for other compounds.
- time_h: include clearly implied shorter or longer times that failed. If not discussed, leave empty.  You can also get choice based on other conditions the author tried for other compounds.
- solvent_main: include non-working solvents or ratios that the article shows or implies. Keep volumes and roles consistent with the success protocol.  You can also get choice based on other solvents the author tried for other compounds.
- modulator_1: include modulators used or discussed in this paper. If the author only says "acid" or "base" to change pH, you can use common acid or base modulator in MOF synthesis. Adjust loadings using the article's units, prefer mol or gram or mL, dont use eq. and if the author indicate pH changed by modulator is important (e.g. outside a range does not form), you can infer what acid or base the author may have tried if author does not explictly say, you can include up to 2 modulator the author may use to change the pH like strong acid or base. But if the author stated specific name of modulator even in other protocols, you can inlcude them and do not have limit. If possible, include the amount and unit based on literature evidence.
- linker_1 and metal_1: include alternatives the article shows or strongly implies are non-working under the same protocol. Keep amounts in the article's units, if not, prefer use mmol or mg, copying the success stoichiometry when swapping.

Focus:
- Prioritize true failures such as amorphous solid or no product. De-emphasize mixed or wrong phase unless the article frames them as non crystallinity.
- Do not invent unsupported failures. Be relevant to what the authors discussed, but if their description implies many concrete failing variants, output as many distinct rows as are well supported. There is no limit in how many failures you can produce, as long as it is based on evidence on the paper.

Rationale and notes:
- rationale_overall: up to 50 words. Summarize the failure landscape and include the attempted MOF or compound names. Treat any prior trial_or_failure notes as hints only; rely on the full article and SI.
- modification_notes for each BaseModificationPlan must state the basis for inclusion and reference short evidence phrases such as "text: 'lower temperatures gave amorphous solids' Fig. S3".

Constraints:
- Allowed edit classes are limited to {ALLOWED_CHANGED_SECTIONS}. Do not invent new labels.
- If details cannot be reconstructed credibly, leave that class empty.
- Output only JSON that matches the schema. No extra commentary.
"""

NEG_USER_PROMPT_TEMPLATE = """Context for negative-data mining

DOI: {doi}

Reference notes from prior pass (context only; do not follow blindly):
<<<TRIAL_NOTES_START
{reference_notes}
TRIAL_NOTES_END>>>

All known successful syntheses from this paper (indexed; use as bases):
<<<SUCCESS_JSONS_START
{success_blob}
SUCCESS_JSONS_END>>>

Full article text:
<<<ARTICLE_START
{article_text}
ARTICLE_END>>>

Supporting Information:
<<<SI_START
{si_text}
SI_END>>>
"""


# ===========================================================================
# 3. JSON I/O helpers
# ===========================================================================

def _load_all_success_jsons(
    doi: str,
    json_store_dir: str = DEFAULT_SUCCESS_DIR,
    positive_csv: Optional[str] = None,
) -> List[str]:
    out: List[str] = []
    base = Path(json_store_dir) / sanitize_for_path(doi)
    if base.exists():
        for p in sorted(base.glob("synthesis_*.json")):
            try:
                out.append(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        if not out:
            art = base / "article_extraction.json"
            if art.exists():
                try:
                    data = json.loads(art.read_text(encoding="utf-8"))
                    syns = (data or {}).get("syntheses", [])
                    for s in syns:
                        out.append(json.dumps(s, ensure_ascii=False))
                except Exception:
                    pass
    if not out and positive_csv and os.path.exists(positive_csv):
        try:
            df = pd.read_csv(positive_csv, encoding="utf-8-sig")
            sub = df[df["doi"].astype(str) == str(doi)]
            for x in sub.get("parsed_json", []):
                if isinstance(x, str) and x.strip() and os.path.exists(x.strip()):
                    try:
                        out.append(Path(x.strip()).read_text(encoding="utf-8"))
                    except Exception:
                        pass
        except Exception:
            pass
    # Deduplicate
    seen: Set[str] = set()
    uniq: List[str] = []
    for s in out:
        k = s.strip()
        if k and k not in seen:
            uniq.append(k)
            seen.add(k)
    return uniq


def _build_success_blob(success_json_list: List[str]) -> str:
    parts = []
    for i, s in enumerate(success_json_list, start=1):
        parts.append(f"-- SUCCESS {i} --\n{s.strip()}")
    return safe_truncate("\n\n".join(parts), max_chars=300_000)


def _yes_note_for_doi(doi: str, positive_csv: str) -> str:
    try:
        df = pd.read_csv(positive_csv, encoding="utf-8-sig")
        sub = df[df["doi"].astype(str) == str(doi)]
        for x in sub.get("article_trial_or_failure_notes", []):
            if isinstance(x, str) and x.strip():
                return x.strip()
    except Exception:
        pass
    return ""


def save_plan_payloads(
    doi: str,
    raw_output: str,
    parsed_obj: PaperModificationPlan,
    out_dir: str,
) -> Dict[str, Any]:
    base = Path(out_dir) / sanitize_for_path(doi)
    ensure_dir(base)

    raw_json_path = base / "raw_plan_output.json"
    raw_txt_path  = base / "raw_plan_output.txt"
    try:
        candidate = json.loads(raw_output)
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(candidate, f, ensure_ascii=False, indent=2)
        raw_path = raw_json_path
    except Exception:
        with open(raw_txt_path, "w", encoding="utf-8") as f:
            f.write(raw_output if isinstance(raw_output, str) else str(raw_output))
        raw_path = raw_txt_path

    paper_plan_path = base / "paper_plan.json"
    with open(paper_plan_path, "w", encoding="utf-8") as f:
        json.dump(parsed_obj.model_dump(), f, ensure_ascii=False, indent=2)

    plan_paths: List[Path] = []
    for i, plan in enumerate(parsed_obj.plans or [], start=1):
        p = base / f"plan_{i:03d}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)
        plan_paths.append(p)

    return {
        "raw_path": str(raw_path),
        "paper_plan_path": str(paper_plan_path),
        "plan_paths": [str(p) for p in plan_paths],
    }


def _plan_json_exists_for_doi(doi: str, json_out_dir: str) -> bool:
    base = Path(json_out_dir) / sanitize_for_path(doi)
    if (base / "paper_plan.json").exists():
        return True
    for _ in base.glob("plan_*.json"):
        return True
    return False


# ===========================================================================
# 4. CSV helpers (specific to negative mining)
# ===========================================================================

def _variations_nonempty(v: VariationSet) -> bool:
    return any([
        bool(v.metal_1), bool(v.linker_1), bool(v.modulator_1),
        bool(v.solvent_main), bool(v.temperature_c), bool(v.time_h),
    ])


def _empty_plan_row(doi: str, main_file: str, si_file: str,
                    raw_output_path: str, status: str, error: str) -> Dict[str, Any]:
    return {
        "doi": doi, "main_pdf": main_file, "si_pdf": si_file,
        "raw_output": raw_output_path, "parsed_json": "",
        "article_trial_or_failure": "", "article_trial_or_failure_notes": "",
        "mof_name": "", "modification_notes": "", "rationale": "",
        "based_on_success_index": "",
        "metal_1_options": "[]", "linker_1_options": "[]",
        "modulator_1_options": "[]", "solvent_main_options": "[]",
        "temperature_c_options": "[]", "time_h_options": "[]",
        "status": status, "error": error,
    }


def flatten_plan_rows(
    doi: str,
    main_file: str,
    si_file: str,
    raw_output_path: str,
    parsed_obj: PaperModificationPlan,
    plan_json_paths: List[str],
    article_trial_note: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rationale = parsed_obj.rationale_overall or ""

    for i, plan in enumerate(parsed_obj.plans or [], start=1):
        if not plan or not plan.variations or not _variations_nonempty(plan.variations):
            continue

        def je(x): return json.dumps(x, ensure_ascii=False)

        rows.append({
            "doi": doi, "main_pdf": main_file, "si_pdf": si_file,
            "raw_output": raw_output_path,
            "parsed_json": plan_json_paths[i - 1] if i - 1 < len(plan_json_paths) else "",
            "article_trial_or_failure": "yes" if article_trial_note else "",
            "article_trial_or_failure_notes": article_trial_note,
            "mof_name": plan.mof_name or "",
            "modification_notes": plan.modification_notes or "",
            "rationale": rationale,
            "based_on_success_index": plan.based_on_success_index,
            "metal_1_options":     je([m.model_dump() for m in plan.variations.metal_1]),
            "linker_1_options":    je([l.model_dump() for l in plan.variations.linker_1]),
            "modulator_1_options": je([m.model_dump() for m in plan.variations.modulator_1]),
            "solvent_main_options":je([s.model_dump() for s in plan.variations.solvent_main]),
            "temperature_c_options": je(list(plan.variations.temperature_c or [])),
            "time_h_options":        je(list(plan.variations.time_h or [])),
            "status": "ok", "error": "",
        })

    if not rows:
        rows.append(_empty_plan_row(doi, main_file, si_file, raw_output_path, "ok", ""))
    return rows


def _load_done_dois_from_csv(csv_path: str) -> Set[str]:
    if not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        if "doi" not in df.columns or "status" not in df.columns:
            return set()
        ok = df["status"].astype(str).str.strip().str.lower() == "ok"
        return set(df.loc[ok, "doi"].astype(str))
    except Exception:
        return set()


def _clean_excel_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"", "nan", "none"} else s


def _valid_file_path(path_str: str, allowed_exts: Optional[Set[str]] = None) -> bool:
    if not path_str:
        return False
    try:
        path = Path(path_str)
        if allowed_exts is not None and path.suffix.lower() not in allowed_exts:
            return False
        return path.is_file()
    except (OSError, ValueError):
        return False


def drop_rows_for_dois(csv_path: str, dois_to_drop: Set[str]) -> int:
    if not os.path.exists(csv_path) or not dois_to_drop:
        return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    before = len(df)
    df = df[~df["doi"].astype(str).isin({str(x) for x in dois_to_drop})]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return before - len(df)


def summarize_trials_yes(
    in_csv: str = DEFAULT_POSITIVE_CSV,
    out_csv_yes_7: str = str(_DATA_DIR / "mof_trials_yes_7.csv"),
) -> Tuple[pd.DataFrame, int, int, float]:
    if not os.path.exists(in_csv):
        print(f"[INFO] Input CSV not found: {in_csv}")
        return pd.DataFrame(), 0, 0, 0.0

    df = pd.read_csv(in_csv, encoding="utf-8-sig")
    key_cols = ["doi", "main_pdf", "si_pdf", "raw_output", "parsed_json",
                "article_trial_or_failure", "article_trial_or_failure_notes"]
    for k in key_cols:
        if k not in df.columns:
            raise ValueError(f"Missing column in input CSV: {k}")

    m = df[key_cols].copy()
    m["article_trial_or_failure"] = m["article_trial_or_failure"].fillna("").str.strip().str.lower()
    yes = m[m["article_trial_or_failure"] == "yes"].copy()
    yes_merged = yes.drop_duplicates(subset=["doi", "article_trial_or_failure_notes"]).reset_index(drop=True)
    yes_merged.to_csv(out_csv_yes_7, index=False, encoding="utf-8-sig")

    total_unique = df["doi"].astype(str).nunique()
    yes_unique   = yes["doi"].astype(str).nunique()
    pct          = 100.0 * yes_unique / total_unique if total_unique else 0.0
    print(f"Unique DOIs with 'yes': {yes_unique} of {total_unique} ({pct:.1f}%)")
    print(f"Wrote 7-column deduped list to: {out_csv_yes_7}")
    return yes_merged, yes_unique, total_unique, pct


# ===========================================================================
# 5. Worker & concurrent runner (run_negative)
# ===========================================================================

def _neg_build_plan(
    client: OpenAI,
    doi: str,
    main_file: str,
    si_file: str,
    success_json_list: List[str],
    reference_notes: str,
    model_name: str = "gpt-5",
) -> Tuple[str, PaperModificationPlan]:
    main_text    = read_any_text(main_file)
    si_text      = read_any_text(si_file) if si_file else ""
    success_blob = _build_success_blob(success_json_list) if success_json_list else "-- SUCCESS 1 --\n{}"
    user_msg = NEG_USER_PROMPT_TEMPLATE.format(
        doi=doi,
        reference_notes=reference_notes or "(empty)",
        success_blob=success_blob,
        article_text=safe_truncate(main_text),
        si_text=safe_truncate(si_text),
    )
    resp = client.responses.parse(
        model=model_name,
        reasoning={"effort": "medium"},
        input=[
            {"role": "system", "content": NEG_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        text_format=PaperModificationPlan,
    )
    raw_output = resp.output_text or json.dumps(resp.model_dump(), ensure_ascii=False)
    parsed: PaperModificationPlan = resp.output_parsed
    return raw_output, parsed


def _neg_build_plan_with_retry(client: OpenAI, *args, **kwargs):
    try:
        return _neg_build_plan(client, *args, **kwargs)
    except Exception:
        time.sleep(0.7)
        return _neg_build_plan(client, *args, **kwargs)


def _load_yes_dois(positive_csv: str) -> Set[str]:
    yes: Set[str] = set()
    if not os.path.exists(positive_csv):
        print(f"[WARN] positive_csv not found: {positive_csv}. No DOIs will run.")
        return yes
    try:
        df = pd.read_csv(positive_csv, encoding="utf-8-sig",
                         usecols=["doi", "article_trial_or_failure"])
        m  = df["article_trial_or_failure"].fillna("").str.strip().str.lower() == "yes"
        yes = set(df.loc[m, "doi"].astype(str))
    except Exception as e:
        print(f"[WARN] could not parse positive_csv: {e}. No DOIs will run.")
    return yes


def process_negative_item_yes(
    item: Dict[str, str],
    model: str,
    out_dir: str,
    positive_csv: str,
    yes_dois: Set[str],
    success_dir: str = DEFAULT_SUCCESS_DIR,
) -> Dict[str, Any]:
    doi, main_file, si_file = item["doi"], item["main_pdf"], item["si_pdf"]

    if doi not in yes_dois:
        return {"doi": doi, "rows": [], "status": "skipped_no_yes", "error": "", "elapsed": 0.0}

    t0 = time.perf_counter()
    print(f"NEG-PLAN START [{doi}]")
    client = OpenAI()
    try:
        success_list = _load_all_success_jsons(doi, json_store_dir=success_dir,
                                               positive_csv=positive_csv)
        if not success_list:
            success_list = ["{}"]

        ref_notes = _yes_note_for_doi(doi, positive_csv)
        raw, parsed = _neg_build_plan_with_retry(
            client, doi=doi, main_file=main_file, si_file=si_file,
            success_json_list=success_list, reference_notes=ref_notes, model_name=model,
        )
        paths = save_plan_payloads(doi, raw, parsed, out_dir)
        rows  = flatten_plan_rows(
            doi=doi, main_file=main_file, si_file=si_file,
            raw_output_path=paths["raw_path"],
            parsed_obj=parsed, plan_json_paths=paths["plan_paths"],
            article_trial_note=ref_notes,
        )
        dt = time.perf_counter() - t0
        print(f"NEG-PLAN DONE  [{doi}] in {dt:.2f}s")
        return {"doi": doi, "rows": rows, "status": "ok", "error": "", "elapsed": dt}
    except Exception as e:
        dt = time.perf_counter() - t0
        print(f"[NEG-PLAN ERROR] {doi}: {e}")
        return {
            "doi": doi,
            "rows": [_empty_plan_row(doi, main_file, si_file, "", "failed", str(e))],
            "status": "failed", "error": str(e), "elapsed": dt,
        }


def run_negative(
    excel_path: str = DEFAULT_EXCEL_PATH,
    positive_csv: str = DEFAULT_POSITIVE_CSV,
    csv_out: str = DEFAULT_FAILPLAN_CSV,
    start_row: int = 0,
    model: str = "gpt-5",
    concurrency: int = 5,
    only_dois_with_yes: bool = True,
    json_out_dir: str = DEFAULT_NEG_JSON_DIR,
    success_dir: str = DEFAULT_SUCCESS_DIR,
    resume_mode: str = "csv",
    force_rerun: bool = False,
    update_in_place: bool = True,
    quick_run_n: Optional[int] = None,
    summarize_trials_first: bool = False,
    skip_if_plan_csv_exists: bool = True,
    skip_if_plan_json_exists: bool = True,
    dry_run: bool = False,
    verbose_skip: bool = True,
    verbose_list: bool = True,
) -> None:
    """
    Mine negative synthesis conditions for every 'yes' DOI in positive_csv.

    Writes one row per (doi, based_on_success_index) to csv_out.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    ensure_dir(Path(json_out_dir))

    if summarize_trials_first and os.path.exists(positive_csv):
        try:
            summarize_trials_yes(
                in_csv=positive_csv,
                out_csv_yes_7=str(Path(csv_out).parent / "mof_trials_yes_7.csv"),
            )
        except Exception as e:
            print(f"[WARN] summarize_trials_yes failed: {e}")

    df = pd.read_excel(excel_path)
    for col in ["DOI", "Main File", "SI File"]:
        if col not in df.columns:
            raise ValueError(f"Missing column in Excel: {col}")

    yes_dois = _load_yes_dois(positive_csv)
    if not yes_dois:
        print("[INFO] No DOIs marked 'yes' in positive_csv. Nothing to do.")
        return

    candidates = []
    skipped_invalid_source = 0
    seen: Set[str] = set()
    for _, row in df.iloc[start_row:].iterrows():
        doi = _clean_excel_cell(row["DOI"])
        if not doi or doi in seen:
            continue
        seen.add(doi)
        if doi not in yes_dois:
            if verbose_skip:
                print(f"[SKIP NO/EMPTY] {doi} not marked 'yes'")
            continue
        main_file = _clean_excel_cell(row["Main File"])
        si_file   = _clean_excel_cell(row["SI File"])
        if not _valid_file_path(main_file, {".pdf"}):
            skipped_invalid_source += 1
            if verbose_skip:
                print(f"[SKIP NO MAIN] {doi} missing usable Main File")
            continue
        if si_file and not _valid_file_path(si_file, {".pdf", ".docx", ".doc"}):
            si_file = ""
        candidates.append({"doi": doi, "main_pdf": main_file, "si_pdf": si_file})
    if skipped_invalid_source:
        print(f"[INFO] Skipped {skipped_invalid_source} DOI(s) with missing usable Main File.")

    done_csv = _load_done_dois_from_csv(csv_out) if (resume_mode == "csv" and skip_if_plan_csv_exists) else set()
    items = []
    for it in candidates:
        doi = it["doi"]
        reasons = []
        if skip_if_plan_csv_exists and doi in done_csv:
            reasons.append("plan_csv")
        if skip_if_plan_json_exists and _plan_json_exists_for_doi(doi, json_out_dir):
            reasons.append("plan_json")
        if reasons and not force_rerun:
            if verbose_skip:
                print(f"[SKIP] {doi} due to {', '.join(reasons)}")
            continue
        items.append(it)

    if quick_run_n is not None and quick_run_n > 0:
        items = items[:quick_run_n]

    total = len(items)
    if total == 0:
        print("Nothing to process for negative plan.")
        return

    for i, it in enumerate(items, start=1):
        it["__rank"]  = i
        it["__total"] = total

    print(f"Total DOIs to mine negative plan: {total}")
    if verbose_list:
        print("Selected DOIs:")
        for it in items:
            print(" ", f"[{it['__rank']}/{total}]", it["doi"])

    if dry_run:
        print("Dry run complete.")
        return

    if force_rerun and update_in_place and resume_mode == "csv":
        dois_to_update = {it["doi"] for it in items if it["doi"] in done_csv}
        if dois_to_update:
            removed = drop_rows_for_dois(csv_out, dois_to_update)
            print(f"[UPDATE] Removed {removed} old row(s) for {len(dois_to_update)} DOI(s)")

    buffer = []
    processed = 0

    def _proc(it: Dict[str, Any]) -> Dict[str, Any]:
        doi  = it["doi"]
        rank = it.get("__rank", "?")
        tot  = it.get("__total", "?")
        print(f"NEG-PLAN START [{rank}/{tot}] [{doi}]")
        return process_negative_item_yes(
            {"doi": doi, "main_pdf": it["main_pdf"], "si_pdf": it["si_pdf"]},
            model, json_out_dir, positive_csv, yes_dois, success_dir,
        )

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(_proc, it) for it in items]
        for fut in as_completed(futs):
            res = fut.result()
            if res["rows"]:
                buffer.extend(res["rows"])
            processed += 1
            if len(buffer) >= 25:
                written, skipped = append_rows(csv_out, buffer)
                buffer = []
                print(f"[FLUSH] wrote {written} rows to {csv_out}, skipped {skipped}")

    if buffer:
        written, skipped = append_rows(csv_out, buffer)
        print(f"[FINAL FLUSH] wrote {written} rows to {csv_out}, skipped {skipped}")

    print(f"Finished. Processed {processed}/{total} DOIs.")


# ===========================================================================
# 6. Failure enumeration — expand plans → one row per combo
# ===========================================================================

def _json_or_empty_list(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    if isinstance(x, (list, dict)):
        return x
    try:
        return json.loads(str(x))
    except Exception:
        return []


def _read_success_syn(doi: str, idx_1based: int, success_dir: str) -> Optional[Dict[str, Any]]:
    base = Path(success_dir) / sanitize_for_path(doi)
    synp = base / f"synthesis_{idx_1based:03d}.json"
    if synp.exists():
        try:
            return json.loads(synp.read_text(encoding="utf-8"))
        except Exception:
            pass
    art = base / "article_extraction.json"
    if art.exists():
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
            syns = (data or {}).get("syntheses", [])
            if 1 <= idx_1based <= len(syns):
                return syns[idx_1based - 1]
        except Exception:
            pass
    return None


def _mk_amount_text(val, unit, kind="mol") -> str:
    if val is None or unit is None or str(val) == "":
        return ""
    return f"{val} mL" if kind == "mL" else f"{val} {unit}"


def _keep_first_half(seq):
    if not seq:
        return []
    if isinstance(seq, dict):
        return [seq]
    if not isinstance(seq, list):
        try:
            seq = list(seq)
        except Exception:
            return []
    k = (len(seq) + 1) // 2
    return seq[:k]


def _pick_reagents_dict(lst, n: int):
    lst = lst or []
    out = list(lst[:n])
    while len(out) < n:
        out.append(None)
    return out


def _pick_solvent_by_role_dict(lst, role: str):
    for s in lst or []:
        if (s or {}).get("role") == role:
            return s
    return None


def _rg_tuple_dict(r):
    if not r:
        return ("", "", "", "", "")
    return (
        r.get("name_full", "") or "",
        r.get("abbreviation", "") or "",
        r.get("amount_text", "") or "",
        r.get("amount_value", "") if r.get("amount_value") is not None else "",
        r.get("amount_unit", "") or "",
    )


def _sv_tuple_dict(s):
    if not s:
        return ("", "", "", "")
    return (
        s.get("name_full", "") or "",
        s.get("abbreviation", "") or "",
        s.get("amount_text", "") or "",
        s.get("amount_value_ml", "") if s.get("amount_value_ml") is not None else "",
    )


def _all_options_empty(metal, linker, mod, solv, t, h) -> bool:
    def _empty(lst):
        return not lst or all(x is None for x in lst)
    return all([_empty(metal), _empty(linker), _empty(mod), _empty(solv), _empty(t), _empty(h)])


def _load_done_pairs_from_csv(enum_csv: str) -> Set[Tuple[str, int]]:
    done: Set[Tuple[str, int]] = set()
    if not os.path.exists(enum_csv):
        return done
    try:
        df = pd.read_csv(enum_csv, encoding="utf-8-sig",
                         usecols=["doi", "based_on_success_index"])
        for _, r in df.iterrows():
            doi = str(r["doi"]).strip()
            try:
                idx = int(r["based_on_success_index"])
            except Exception:
                continue
            done.add((doi, idx))
    except Exception:
        pass
    return done


def _enum_exists_for_pair(doi: str, base_idx: int, enum_dir: str) -> bool:
    b = Path(enum_dir) / sanitize_for_path(doi) / f"base_{base_idx:03d}"
    if not b.exists():
        return False
    for _ in b.glob("combo_*.json"):
        return True
    return False


def _write_enum_json(doi: str, base_idx: int, combo_idx: int,
                     payload: Dict[str, Any], enum_dir: str) -> str:
    root = Path(enum_dir) / sanitize_for_path(doi) / f"base_{base_idx:03d}"
    ensure_dir(root)
    p = root / f"combo_{combo_idx:04d}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def enumerate_failures(
    failplan_csv: str = DEFAULT_FAILPLAN_CSV,
    out_csv: str = DEFAULT_ENUM_CSV,
    success_dir: str = DEFAULT_SUCCESS_DIR,
    enum_json_dir: str = DEFAULT_ENUM_JSON_DIR,
    yes_only: bool = True,
    skip_if_enum_csv_exists: bool = True,
    skip_if_enum_json_exists: bool = False,
    skip_empty_options: bool = True,
    verbose_skip: bool = True,
    dry_run: bool = False,
    flush_every: int = 500,
) -> None:
    """
    Enumerate failure combinations from failplan rows + base success JSONs.

    Reads
        failplan_csv       — output of run_negative()
        success_dir        — mof_json_store/ from Step 3.2
    Writes
        out_csv            — one row per enumerated failed condition
        enum_json_dir      — per-combo JSON files for traceability
    """
    if not os.path.exists(failplan_csv):
        raise FileNotFoundError(f"Missing failplan CSV: {failplan_csv}")

    ensure_dir(Path(enum_json_dir))
    df = pd.read_csv(failplan_csv, encoding="utf-8-sig")

    required_cols = [
        "doi", "main_pdf", "si_pdf", "raw_output", "parsed_json",
        "article_trial_or_failure", "article_trial_or_failure_notes",
        "mof_name", "modification_notes", "rationale",
        "based_on_success_index",
        "metal_1_options", "linker_1_options", "modulator_1_options",
        "solvent_main_options", "temperature_c_options", "time_h_options",
    ]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"Missing column in failplan CSV: {c}")

    if yes_only:
        df = df[df["article_trial_or_failure"].fillna("").str.strip().str.lower() == "yes"].copy()

    # Drop DOI with missing synthesis info
    DROP_DOIS_MISSING_SYN = {"10.1021/acsmaterialslett.0c00456"}
    before = len(df)
    df = df[~df["doi"].astype(str).str.strip().isin(DROP_DOIS_MISSING_SYN)].copy()
    if verbose_skip and len(df) < before:
        print("[DROP] 10.1021/acsmaterialslett.0c00456 skipped (missing synthesis info)")

    df["based_on_success_index"] = pd.to_numeric(
        df["based_on_success_index"], errors="coerce"
    ).astype("Int64")
    df = df.dropna(subset=["based_on_success_index"])
    df["based_on_success_index"] = df["based_on_success_index"].astype(int)
    df_pairs = df.drop_duplicates(subset=["doi", "based_on_success_index"]).reset_index(drop=True)

    done_pairs_csv = load_done_pairs_from_csv(out_csv) if skip_if_enum_csv_exists else set()

    to_process = []
    for _, r in df_pairs.iterrows():
        doi      = str(r["doi"]).strip()
        base_idx = int(r["based_on_success_index"])
        # Special drop: 10.1002/chem.201802189 base 2
        if doi == "10.1002/chem.201802189" and base_idx == 2:
            if verbose_skip:
                pass  # silent per notebook
            continue
        reasons = []
        if skip_if_enum_csv_exists and (doi, base_idx) in done_pairs_csv:
            reasons.append("enum_csv")
        if skip_if_enum_json_exists and _enum_exists_for_pair(doi, base_idx, enum_json_dir):
            reasons.append("enum_json")
        if reasons:
            if verbose_skip:
                print(f"[SKIP] {doi} base {base_idx} due to {', '.join(reasons)}")
            continue
        to_process.append(r)

    if dry_run:
        print("Dry run. Would enumerate these pairs:")
        for r in to_process:
            print(" ", str(r["doi"]).strip(), int(r["based_on_success_index"]))
        return

    if not to_process:
        print("Nothing to enumerate. All pairs appear to be done.")
        return

    per_doi_counts: Dict[str, int] = {}
    buffer = []
    total_written = 0

    for row in to_process:
        doi      = str(row["doi"]).strip()
        base_idx = int(row["based_on_success_index"])

        # Secondary check (belt-and-suspenders)
        if doi == "10.1021/acsmaterialslett.0c00456":
            if verbose_skip:
                print(f"[DROP] {doi} base {base_idx} (missing synthesis info)")
            continue

        syn = _read_success_syn(doi, base_idx, success_dir)
        if syn is None:
            print(f"[WARN] Missing base synthesis for DOI {doi} index {base_idx}")
            continue

        main_pdf   = str(row.get("main_pdf", "") or "")
        si_pdf     = str(row.get("si_pdf", "") or "")
        raw_plan   = str(row.get("raw_output", "") or "")
        trial_note = str(row.get("article_trial_or_failure_notes", "") or "")
        mof_name   = str(row.get("mof_name", "") or "")
        mod_notes  = str(row.get("modification_notes", "") or "")
        rationale  = str(row.get("rationale", "") or "")

        metal_opts = _json_or_empty_list(row.get("metal_1_options"))
        linkr_opts = _json_or_empty_list(row.get("linker_1_options"))
        mod_opts   = _json_or_empty_list(row.get("modulator_1_options"))
        solv_opts  = _json_or_empty_list(row.get("solvent_main_options"))
        t_opts     = _json_or_empty_list(row.get("temperature_c_options"))
        h_opts     = _json_or_empty_list(row.get("time_h_options"))

        # -------- Special-case overrides (preserved verbatim from notebook) --------
        if doi == "10.1039/b713705b" and base_idx in (1, 2):
            t_opts = [100]

        if doi == "10.1002/chem.201802189":
            metal_opts = _keep_first_half(metal_opts)
            linkr_opts = _keep_first_half(linkr_opts)
            if base_idx == 1:
                t_opts = [80, 140]
                h_opts = [12]
        # ---------------------------------------------------------------------------

        if skip_empty_options and _all_options_empty(metal_opts, linkr_opts, mod_opts, solv_opts, t_opts, h_opts):
            if verbose_skip:
                print(f"[SKIP EMPTY] {doi} base {base_idx} has no options in any class")
            continue

        metal_opts = metal_opts if metal_opts else [None]
        linkr_opts = linkr_opts if linkr_opts else [None]
        mod_opts   = mod_opts   if mod_opts   else [None]
        solv_opts  = solv_opts  if solv_opts  else [None]
        t_opts     = t_opts     if t_opts     else [None]
        h_opts     = h_opts     if h_opts     else [None]

        combo_idx = 0
        for opt_m, opt_l, opt_md, opt_s, opt_t, opt_h in itertools.product(
            metal_opts, linkr_opts, mod_opts, solv_opts, t_opts, h_opts
        ):
            combo_idx += 1
            varied: List[str] = []
            syn_mod = copy.deepcopy(syn)
            for key in ["metals", "linkers", "modulators", "solvents", "conditions", "post_processing", "structure_properties"]:
                syn_mod.setdefault(key, {} if key in ("conditions", "post_processing", "structure_properties") else [])

            if opt_m is not None:
                varied.append("metal_1")
                r = {
                    "name_full": opt_m.get("name_full", ""),
                    "abbreviation": opt_m.get("abbreviation", "") or "",
                    "amount_text": _mk_amount_text(opt_m.get("amount_value"), opt_m.get("amount_unit"), kind="mol"),
                    "amount_value": opt_m.get("amount_value", None),
                    "amount_unit": opt_m.get("amount_unit", "") or "",
                }
                if syn_mod["metals"]:
                    syn_mod["metals"][0] = r
                else:
                    syn_mod["metals"].append(r)

            if opt_l is not None:
                varied.append("linker_1")
                r = {
                    "name_full": opt_l.get("name_full", ""),
                    "abbreviation": opt_l.get("abbreviation", "") or "",
                    "amount_text": _mk_amount_text(opt_l.get("amount_value"), opt_l.get("amount_unit"), kind="mol"),
                    "amount_value": opt_l.get("amount_value", None),
                    "amount_unit": opt_l.get("amount_unit", "") or "",
                }
                if syn_mod["linkers"]:
                    syn_mod["linkers"][0] = r
                else:
                    syn_mod["linkers"].append(r)

            if opt_md is not None:
                varied.append("modulator_1")
                r = {
                    "name_full": opt_md.get("name_full", ""),
                    "abbreviation": opt_md.get("abbreviation", "") or "",
                    "amount_text": _mk_amount_text(opt_md.get("amount_value"), opt_md.get("amount_unit"), kind="mol"),
                    "amount_value": opt_md.get("amount_value", None),
                    "amount_unit": opt_md.get("amount_unit", "") or "",
                }
                if syn_mod["modulators"]:
                    syn_mod["modulators"][0] = r
                else:
                    syn_mod["modulators"].append(r)

            if opt_s is not None:
                varied.append("solvent_main")
                main_s = None
                for i_s, s0 in enumerate(syn_mod["solvents"]):
                    if s0.get("role") == "main":
                        main_s = i_s
                        break
                sobj = {
                    "name_full": opt_s.get("name_full", ""),
                    "abbreviation": opt_s.get("abbreviation", "") or "",
                    "amount_text": _mk_amount_text(opt_s.get("amount_value_ml"), "mL", kind="mL"),
                    "amount_value_ml": opt_s.get("amount_value_ml", None),
                    "role": "main",
                }
                if main_s is not None:
                    syn_mod["solvents"][main_s] = sobj
                else:
                    syn_mod["solvents"].append(sobj)

            if opt_t is not None:
                varied.append("temperature_c")
                syn_mod["conditions"]["temperature_c"]      = opt_t
                syn_mod["conditions"]["temperature_c_text"] = f"{opt_t} °C"

            if opt_h is not None:
                varied.append("time_h")
                syn_mod["conditions"]["time_h"]   = opt_h
                syn_mod["conditions"]["time_text"] = f"{opt_h} h"

            enum_payload = {
                "based_on_success_index": int(base_idx),
                "varied_classes": varied,
                "reference": syn_mod.get("reference", doi),
                "mof_name": mof_name or syn_mod.get("mof_name", ""),
                "synthesis": syn_mod,
            }
            enum_json_path = _write_enum_json(doi, base_idx, combo_idx, enum_payload, enum_json_dir)

            # Flatten to CSV row
            m1, m2, m3 = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn_mod.get("metals"), 3)]
            l1, l2, l3 = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn_mod.get("linkers"), 3)]
            md1, md2   = [_rg_tuple_dict(x) for x in _pick_reagents_dict(syn_mod.get("modulators"), 2)]
            sm = _sv_tuple_dict(_pick_solvent_by_role_dict(syn_mod.get("solvents"), "main"))
            ss = _sv_tuple_dict(_pick_solvent_by_role_dict(syn_mod.get("solvents"), "secondary"))
            cond = syn_mod.get("conditions", {}) or {}
            pp   = syn_mod.get("post_processing", {}) or {}
            sp   = syn_mod.get("structure_properties", {}) or {}

            row_out = {
                "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
                "raw_output": raw_plan, "parsed_json": enum_json_path,
                "article_trial_or_failure": "yes" if trial_note else "",
                "article_trial_or_failure_notes": trial_note,
                "mof_name": mof_name or syn_mod.get("mof_name", ""),
                "modification_notes": mod_notes, "rationale": rationale,
                "based_on_success_index": base_idx,
                "varied_classes": ";".join(varied),

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
                "temperature_c": cond.get("temperature_c", ""), "temperature_c_text": cond.get("temperature_c_text", "") or "",
                "time_h": cond.get("time_h", ""), "time_text": cond.get("time_text", "") or "",
                "vessel_type": cond.get("vessel_type", "") or "", "stirring": cond.get("stirring", "") or "",
                "washing_solvent": pp.get("washing_solvent", "") or "", "washing_cycles": pp.get("washing_cycles", "") or "",
                "activation_text": pp.get("activation_text", "") or "",
                "activation_temp_c": pp.get("activation_temp_c", "") if pp.get("activation_temp_c") is not None else "",
                "activation_time_h": pp.get("activation_time_h", "") if pp.get("activation_time_h") is not None else "",
                "crystal_morphology": syn_mod.get("crystal_morphology", "") or "",
                "yield_percent": syn_mod.get("yield_percent", "") if syn_mod.get("yield_percent") is not None else "",
                "crystal_size": syn_mod.get("crystal_size", "") or "",
                "topology_code": sp.get("topology_code", "") or "",
                "metal_cluster_connectivity": sp.get("metal_cluster_connectivity", "") or "",
                "unit_cell_short": sp.get("unit_cell_short", "") or "",
                "pore_diameter_A": sp.get("pore_diameter_A", "") if sp.get("pore_diameter_A") is not None else "",
                "BET_surface_area_m2g": sp.get("BET_surface_area_m2g", "") if sp.get("BET_surface_area_m2g") is not None else "",
                "air_stable": sp.get("air_stable", "") or "", "water_stable": sp.get("water_stable", "") or "",
                "tga_decomposition_temp_c": sp.get("tga_decomposition_temp_c", "") if sp.get("tga_decomposition_temp_c") is not None else "",
                "applications": ";".join(sp.get("applications", []) or []),
                "reference": syn_mod.get("reference", doi),
                "status": "ok", "error": "",
            }
            buffer.append(row_out)
            per_doi_counts[doi] = per_doi_counts.get(doi, 0) + 1

            if len(buffer) >= flush_every:
                written, _ = append_rows(out_csv, buffer)
                total_written += written
                buffer = []
                print(f"[FLUSH] wrote {written} rows to {out_csv}. Total so far: {total_written}")

    if buffer:
        written, _ = append_rows(out_csv, buffer)
        total_written += written
        print(f"[FINAL FLUSH] wrote {written} rows to {out_csv}. Total: {total_written}")

    print("\nPer-DOI enumerated failures:")
    for d, n in sorted(per_doi_counts.items()):
        print(f"  {d}: {n}")
    print(f"\nTotal enumerated failure conditions: {total_written}")


# Alias used in _load_done_pairs_from_csv (kept for clarity)
def load_done_pairs_from_csv(enum_csv: str) -> Set[Tuple[str, int]]:
    return _load_done_pairs_from_csv(enum_csv)


# ===========================================================================
# 7. CLI
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Step 3.3 — Negative-data mining (failed MOF synthesis conditions)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task", choices=["mine", "enumerate", "all"], default="all",
        help="Task to run: 'mine' runs run_negative(), 'enumerate' runs enumerate_failures(), "
             "'all' runs both in sequence (default: all)",
    )

    # ---- mine task args ----
    mg = parser.add_argument_group("mine task")
    mg.add_argument("--excel", default=DEFAULT_EXCEL_PATH,
                    help=f"Input Excel (DOI, Main File, SI File) (default: {DEFAULT_EXCEL_PATH})")
    mg.add_argument("--positive-csv", default=DEFAULT_POSITIVE_CSV,
                    help=f"Positive extraction CSV from Step 3.2 (default: {DEFAULT_POSITIVE_CSV})")
    mg.add_argument("--failplan-csv", default=DEFAULT_FAILPLAN_CSV,
                    help=f"Output failplan CSV (default: {DEFAULT_FAILPLAN_CSV})")
    mg.add_argument("--model", default="gpt-5",
                    help="OpenAI model (default: gpt-5)")
    mg.add_argument("--concurrency", type=int, default=5,
                    help="Parallel API calls (default: 5)")
    mg.add_argument("--neg-json-dir", default=DEFAULT_NEG_JSON_DIR,
                    help=f"JSON output dir for negative plans (default: {DEFAULT_NEG_JSON_DIR})")
    mg.add_argument("--success-dir", default=DEFAULT_SUCCESS_DIR,
                    help=f"mof_json_store directory from Step 3.2 (default: {DEFAULT_SUCCESS_DIR})")
    mg.add_argument("--quick-n", type=int, default=None,
                    help="Limit to first N DOIs (test mode)")
    mg.add_argument("--dry-run", action="store_true",
                    help="Preview which DOIs would be processed without running")
    mg.add_argument("--force-rerun", action="store_true",
                    help="Rerun even if output already exists")

    # ---- enumerate task args ----
    eg = parser.add_argument_group("enumerate task")
    eg.add_argument("--enum-csv", default=DEFAULT_ENUM_CSV,
                    help=f"Output enum CSV (default: {DEFAULT_ENUM_CSV})")
    eg.add_argument("--enum-json-dir", default=DEFAULT_ENUM_JSON_DIR,
                    help=f"JSON dir for enumerated combos (default: {DEFAULT_ENUM_JSON_DIR})")

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.task in ("mine", "all"):
        run_negative(
            excel_path=args.excel,
            positive_csv=args.positive_csv,
            csv_out=args.failplan_csv,
            model=args.model,
            concurrency=args.concurrency,
            json_out_dir=args.neg_json_dir,
            success_dir=args.success_dir,
            quick_run_n=args.quick_n,
            dry_run=args.dry_run,
            force_rerun=args.force_rerun,
            only_dois_with_yes=True,
            skip_if_plan_csv_exists=not args.force_rerun,
            skip_if_plan_json_exists=not args.force_rerun,
            summarize_trials_first=True,
            verbose_skip=True,
            verbose_list=True,
        )

    if args.task in ("enumerate", "all"):
        enumerate_failures(
            failplan_csv=args.failplan_csv,
            out_csv=args.enum_csv,
            success_dir=args.success_dir,
            enum_json_dir=args.enum_json_dir,
            yes_only=True,
            skip_if_enum_csv_exists=True,
            skip_if_enum_json_exists=False,
            skip_empty_options=True,
            verbose_skip=True,
            dry_run=args.dry_run,
            flush_every=500,
        )
