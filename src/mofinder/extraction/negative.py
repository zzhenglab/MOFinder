"""Evidence-guided negative-condition plans from articles and successful syntheses.

The miner selects papers marked YES for trial-and-error evidence and records
option lists for each successful synthesis. Six editable condition classes
are defined in ALLOWED_CHANGED_SECTIONS. Cartesian expansion is a separate stage.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "negative_extraction.json"
NEG_SYSTEM_PROMPT = (PROJECT_ROOT / "prompts" / "negative_system.txt").read_text(encoding="utf-8")
NEG_USER_PROMPT_TEMPLATE = (PROJECT_ROOT / "prompts" / "negative_user.txt").read_text(encoding="utf-8")
ALLOWED_CHANGED_SECTIONS = ["metal_1", "linker_1", "modulator_1", "solvent_main", "conditions.temperature", "conditions.time"]
_HARD_BREAKS = re.compile(r'[\r\n\u0085\u2028\u2029]')
_CTRL = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
_ZERO_WIDTH = re.compile(r'[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]')


def _make_client():
    from openai import OpenAI
    return OpenAI()


def read_excel_checked(excel_path: str) -> pd.DataFrame:
    """Read the document manifest; accept the original XLSX or a CSV export."""
    path = Path(excel_path)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        frame = pd.read_excel(path, dtype=str, keep_default_na=False)
    for column in ("DOI", "Main File", "SI File"):
        if column not in frame.columns:
            raise ValueError(f"Missing column in document manifest: {column}")
    return frame

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def sanitize_for_path(name: str) -> str:
    if not name:
        return "unknown"
    s = name.strip()
    s = s.replace("/", "_").replace("\\", "_").replace(":", "_")
    s = re.sub(r"[^A-Za-z0-9._\\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_.")
    return s[:160] or "item"


def read_pdf_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        chunks = []
        for p in reader.pages:
            try:
                chunks.append(p.extract_text() or "")
            except Exception:
                continue
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def read_docx_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join([p.text for p in doc.paragraphs]).strip()
    except Exception:
        return ""


def read_doc_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        import textract
        b = textract.process(path)
        return b.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def read_any_text(path: str) -> str:
    if not path:
        return ""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return read_pdf_text(path)
    if ext == ".docx":
        return read_docx_text(path)
    if ext == ".doc":
        return read_doc_text(path)
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def safe_truncate(txt: str, max_chars: int = 400000) -> str:
    return txt[:max_chars] if txt and len(txt) > max_chars else (txt or "")


def to_oneline(val) -> str:
    if val is None:
        return ""
    s = val if isinstance(val, str) else str(val)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\x00b7", "·").replace("\\u0000b7", "·")
    s = _HARD_BREAKS.sub("\n", s)
    s = _CTRL.sub(" ", s)
    s = _ZERO_WIDTH.sub("", s)
    s = s.replace("\u00A0", " ").replace("\t", " ")
    s = re.sub(r"[ ]{2,}", " ", s)
    s = re.sub(r"\n+", "\n", s).replace("\n", "\\n")
    return s


def read_csv_header(csv_path: str) -> Optional[List[str]]:
    if not os.path.exists(csv_path):
        return None
    try:
        if os.path.getsize(csv_path) == 0:
            return None
    except Exception:
        try:
            if os.stat(csv_path).st_size == 0:
                return None
        except Exception:
            return None
    try:
        hdr_df = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=0)
        return list(hdr_df.columns)
    except Exception:
        return None


def append_rows(csv_path: str, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    if not rows:
        return (0, 0)
    existing_header = read_csv_header(csv_path)
    if existing_header is None:
        expected_header = list(rows[0].keys())
        header_needed = True
    else:
        expected_header = existing_header
        header_needed = False

    cleaned, skipped = [], 0
    expected_set = set(expected_header)
    for r in rows:
        keys = set(r.keys())
        if keys != expected_set:
            print(
                f"[ROW SKIPPED] DOI {r.get('doi','?')} invalid column set. "
                f"expected={len(expected_set)} got={len(keys)} "
                f"extra={sorted(keys - expected_set)} missing={sorted(expected_set - keys)}"
            )
            skipped += 1
            continue
        cleaned.append({k: r.get(k, "") for k in expected_header})

    if not cleaned:
        return (0, skipped)

    df = pd.DataFrame(cleaned).fillna("")
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].map(to_oneline)

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        try:
            df.to_csv(
                f, index=False, header=header_needed, sep=",",
                quoting=csv.QUOTE_ALL, doublequote=True, line_terminator="\n",
            )
        except:
            df.to_csv(
                f, index=False, header=header_needed, sep=",",
                quoting=csv.QUOTE_ALL, doublequote=True, lineterminator="\n",
            )
    return (len(df), skipped)


def drop_rows_for_dois(csv_path: str, dois_to_drop: Set[str]) -> int:
    if not os.path.exists(csv_path) or not dois_to_drop:
        return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    before = len(df)
    df = df[~df["doi"].astype(str).isin({str(x) for x in dois_to_drop})]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return before - len(df)


def processed_dois_from_csv(csv_path: str) -> Set[str]:
    if not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["doi"])
        return set(df["doi"].astype(str).tolist())
    except Exception:
        return set()


def summarize_trials_yes(
    in_csv: str = "mof_extraction.csv",
    out_csv_yes_7: str = "mof_trials_yes_7.csv"
) -> Tuple[pd.DataFrame, int, int, float]:
    if not os.path.exists(in_csv):
        print(f"[INFO] Input CSV not found: {in_csv}")
        return pd.DataFrame(), 0, 0, 0.0

    df = pd.read_csv(in_csv, encoding="utf-8-sig")
    key_cols = ["doi","main_pdf","si_pdf","raw_output","parsed_json",
                "article_trial_or_failure","article_trial_or_failure_notes"]
    for k in key_cols:
        if k not in df.columns:
            raise ValueError(f"Missing column in input CSV: {k}")

    m = df[key_cols].copy()
    m["article_trial_or_failure"] = m["article_trial_or_failure"].fillna("").str.strip().str.lower()
    yes = m[m["article_trial_or_failure"] == "yes"].copy()

    yes_merged = yes.drop_duplicates(subset=["doi","article_trial_or_failure_notes"]).reset_index(drop=True)
    yes_merged.to_csv(out_csv_yes_7, index=False, encoding="utf-8-sig")

    total_unique = df["doi"].astype(str).nunique()
    yes_unique = yes["doi"].astype(str).nunique()
    pct = 100.0 * yes_unique / total_unique if total_unique else 0.0

    print(f"Unique DOIs with 'yes': {yes_unique} of {total_unique} ({pct:.1f}%)")
    print(f"Wrote 7-column deduped list to: {out_csv_yes_7}")
    return yes_merged, yes_unique, total_unique, pct


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
    # If nothing to vary, keep the list empty
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


def _load_all_success_jsons(doi: str, json_store_dir: str = "mof_json_store", positive_csv: Optional[str] = None) -> List[str]:
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
    seen, uniq = set(), []
    for s in out:
        k = s.strip()
        if k and k not in seen:
            uniq.append(k); seen.add(k)
    return uniq


def _build_success_blob(success_json_list: List[str]) -> str:
    parts = []
    for i, s in enumerate(success_json_list, start=1):
        parts.append(f"-- SUCCESS {i} --\n{s.strip()}")
    return safe_truncate("\n\n".join(parts), max_chars=300000)


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


def _neg_build_plan(
    client: Any,
    doi: str,
    main_file: str,
    si_file: str,
    success_json_list: List[str],
    reference_notes: str,
    model_name: str = "gpt-5",
    reasoning_effort: str = "medium",
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
) -> Tuple[str, PaperModificationPlan]:
    main_text = read_any_text(main_file)
    si_text = read_any_text(si_file) if si_file else ""
    success_blob = _build_success_blob(success_json_list) if success_json_list else "-- SUCCESS 1 --\n{}"
    user_msg = (user_prompt_template or NEG_USER_PROMPT_TEMPLATE).format(
        doi=doi,
        reference_notes=reference_notes or "(empty)",
        success_blob=success_blob,
        article_text=safe_truncate(main_text),
        si_text=safe_truncate(si_text),
    )
    resp = client.responses.parse(
        model=model_name,
        reasoning={"effort": reasoning_effort},
        input=[{"role": "system", "content": system_prompt or NEG_SYSTEM_PROMPT},
               {"role": "user", "content": user_msg}],
        text_format=PaperModificationPlan
    )
    raw_output = resp.output_text or json.dumps(resp.model_dump(), ensure_ascii=False)
    parsed: PaperModificationPlan = resp.output_parsed
    return raw_output, parsed


def _neg_build_plan_with_retry(client: Any, *args, **kwargs):
    try:
        return _neg_build_plan(client, *args, **kwargs)
    except Exception:
        time.sleep(0.7)
        return _neg_build_plan(client, *args, **kwargs)


def save_plan_payloads(doi: str, raw_output: str, parsed_obj: PaperModificationPlan, out_dir: str, success_json_list: List[str] | None = None) -> Dict[str, Any]:
    base = Path(out_dir) / sanitize_for_path(doi)
    ensure_dir(base)

    # Preserve the exact base order supplied to the model. Deduplication can
    # otherwise make a displayed success index differ from the source filename.
    if success_json_list is not None:
        snapshot = {
            "record_type": "success_bases_for_negative_plan",
            "doi": doi,
            "index_origin": 1,
            "syntheses": [json.loads(value) for value in success_json_list],
        }
        snapshot_path = base / "success_bases.json"
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        import hashlib
        provenance = {
            "record_type": "evidence_guided_negative_plan",
            "doi": doi,
            "success_snapshot": "success_bases.json",
            "success_snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        }
        (base / "plan_provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # raw output
    raw_json_path = base / "raw_plan_output.json"
    raw_txt_path = base / "raw_plan_output.txt"
    try:
        candidate = json.loads(raw_output)
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(candidate, f, ensure_ascii=False, indent=2)
        raw_path = raw_json_path
    except Exception:
        with open(raw_txt_path, "w", encoding="utf-8") as f:
            f.write(raw_output if isinstance(raw_output, str) else str(raw_output))
        raw_path = raw_txt_path

    # full paper plan
    paper_plan_path = base / "paper_plan.json"
    with open(paper_plan_path, "w", encoding="utf-8") as f:
        json.dump(parsed_obj.model_dump(), f, ensure_ascii=False, indent=2)

    # per-base plans
    plan_paths: List[Path] = []
    for i, plan in enumerate(parsed_obj.plans or [], start=1):
        p = base / f"plan_{i:03d}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)
        plan_paths.append(p)

    return {"raw_path": str(raw_path), "paper_plan_path": str(paper_plan_path), "plan_paths": [str(p) for p in plan_paths]}


def _variations_nonempty(v: VariationSet) -> bool:
    return any([
        bool(v.metal_1), bool(v.linker_1), bool(v.modulator_1),
        bool(v.solvent_main), bool(v.temperature_c), bool(v.time_h)
    ])


def flatten_plan_rows(
    doi: str,
    main_file: str,
    si_file: str,
    raw_output_path: str,
    parsed_obj: PaperModificationPlan,
    plan_json_paths: List[str],
    article_trial_note: str
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rationale = parsed_obj.rationale_overall or ""
    plans = parsed_obj.plans or []

    for i, plan in enumerate(plans, start=1):
        if not plan or not plan.variations or not _variations_nonempty(plan.variations):
            continue  # skip bases with no actual options

        # JSON-encode lists so one row can carry many options
        def je(x): return json.dumps(x, ensure_ascii=False)

        metal_list = [m.model_dump() for m in plan.variations.metal_1]
        linker_list = [l.model_dump() for l in plan.variations.linker_1]
        mod_list   = [m.model_dump() for m in plan.variations.modulator_1]
        solv_list  = [s.model_dump() for s in plan.variations.solvent_main]
        t_list     = list(plan.variations.temperature_c or [])
        h_list     = list(plan.variations.time_h or [])

        rows.append({
            # Source files and paper-level notes.
            "doi": doi,
            "main_pdf": main_file,
            "si_pdf": si_file,
            "raw_output": raw_output_path,
            "parsed_json": plan_json_paths[i-1] if i-1 < len(plan_json_paths) else "",
            "article_trial_or_failure": "yes" if article_trial_note else "",
            "article_trial_or_failure_notes": article_trial_note,
            "mof_name": plan.mof_name or "",
            "modification_notes": plan.modification_notes or "",
            "rationale": rationale,

            # ---- identifiers and option lists ----
            "based_on_success_index": plan.based_on_success_index,
            "metal_1_options": je(metal_list),
            "linker_1_options": je(linker_list),
            "modulator_1_options": je(mod_list),
            "solvent_main_options": je(solv_list),
            "temperature_c_options": je(t_list),
            "time_h_options": je(h_list),

            "status": "ok",
            "error": ""
        })

    # If nothing added, still log the DOI with one empty row (so resume works)
    if not rows:
        rows.append({
            "doi": doi, "main_pdf": main_file, "si_pdf": si_file,
            "raw_output": raw_output_path, "parsed_json": "",
            "article_trial_or_failure": "", "article_trial_or_failure_notes": "",
            "mof_name": "", "modification_notes": "", "rationale": "",
            "based_on_success_index": "",
            "metal_1_options": "[]",
            "linker_1_options": "[]",
            "modulator_1_options": "[]",
            "solvent_main_options": "[]",
            "temperature_c_options": "[]",
            "time_h_options": "[]",
            "status": "ok", "error": ""
        })
    return rows


def _plan_json_exists_for_doi(doi: str, json_out_dir: str = "mof_negative_plan_store") -> bool:
    base = Path(json_out_dir) / sanitize_for_path(doi)
    if (base / "paper_plan.json").exists():
        return True
    for _ in base.glob("plan_*.json"):
        return True
    return False


def _load_done_dois_from_csv(csv_path: str) -> Set[str]:
    if not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["doi"])
        return set(df["doi"].astype(str))
    except Exception:
        return set()


def _load_yes_dois(positive_csv: str) -> Set[str]:
    """
    Return only DOIs where article_trial_or_failure == 'yes' (case-insensitive).
    If the file is missing or malformed, return empty set to avoid accidental runs.
    """
    yes = set()
    if not os.path.exists(positive_csv):
        print(f"[WARN] positive_csv not found: {positive_csv}. No DOIs will run.")
        return yes
    try:
        df = pd.read_csv(positive_csv, encoding="utf-8-sig",
                         usecols=["doi","article_trial_or_failure"])
        m = df["article_trial_or_failure"].fillna("").str.strip().str.lower() == "yes"
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
    success_json_dir: str = "mof_json_store",
    reasoning_effort: str = "medium",
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
) -> Dict[str, Any]:
    """
    Process a negative plan only for a DOI in yes_dois.
    Other DOIs return a skipped result with no rows and no model call.
    """
    doi, main_file, si_file = item["doi"], item["main_pdf"], item["si_pdf"]

    if doi not in yes_dois:
        return {"doi": doi, "rows": [], "status": "skipped_no_yes", "error": "", "elapsed": 0.0}

    t0 = time.perf_counter()
    print(f"NEG-PLAN START [{doi}]")
    try:
        client = _make_client()
        success_list = _load_all_success_jsons(doi, json_store_dir=success_json_dir, positive_csv=positive_csv)
        supplied_successes = list(success_list)
        if not success_list:
            success_list = ["{}"]  # Allow plans based on article text when saved successes are absent.

        # Retain notes from the positive extraction without adding a fallback.
        ref_notes = _yes_note_for_doi(doi, positive_csv)  # may be empty

        raw, parsed = _neg_build_plan_with_retry(
            client, doi=doi, main_file=main_file, si_file=si_file,
            success_json_list=success_list, reference_notes=ref_notes, model_name=model,
            reasoning_effort=reasoning_effort, system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
        )

        if supplied_successes and any(
            plan.based_on_success_index < 1 or plan.based_on_success_index > len(supplied_successes)
            for plan in parsed.plans
        ):
            raise ValueError("A negative plan references a success index outside the supplied list")
        paths = save_plan_payloads(doi, raw, parsed, out_dir, supplied_successes)

        # Set the 'yes' flag only when a source note is present.
        rows = flatten_plan_rows(
            doi=doi,
            main_file=main_file,
            si_file=si_file,
            raw_output_path=paths["raw_path"],
            parsed_obj=parsed,
            plan_json_paths=paths["plan_paths"],
            article_trial_note=ref_notes  # empty -> article_trial_or_failure stays empty
        )
        dt = time.perf_counter() - t0
        print(f"NEG-PLAN DONE  [{doi}] in {dt:.2f}s")
        return {"doi": doi, "rows": rows, "status": "ok", "error": "", "elapsed": dt}
    except Exception as e:
        dt = time.perf_counter() - t0
        print(f"[NEG-PLAN ERROR] {doi}: {e}")
        rows = [{
            "doi": doi, "main_pdf": main_file, "si_pdf": si_file,
            "raw_output": "", "parsed_json": "",
            "article_trial_or_failure": "", "article_trial_or_failure_notes": "",
            "mof_name": "", "modification_notes": "", "rationale": "",
            "based_on_success_index": "",
            "metal_1_options": "[]", "linker_1_options": "[]", "modulator_1_options": "[]",
            "solvent_main_options": "[]", "temperature_c_options": "[]", "time_h_options": "[]",
            "status":"failed", "error": str(e)
        }]
        return {"doi": doi, "rows": rows, "status": "failed", "error": str(e), "elapsed": dt}


def run_negative(
    excel_path: str,
    positive_csv: str = "mof_extraction.csv",
    csv_out: str = "mof_extraction_failplans.csv",
    start_row: int = 0,
    model: str = "gpt-5",
    concurrency: int = 5,
    only_dois_with_yes: bool = True,      # YES-only selection is always enforced.
    json_out_dir: str = "mof_negative_plan_store",
    resume_mode: str = "csv",
    force_rerun: bool = False,
    update_in_place: bool = True,
    quick_run_n: int | None = None,
    summarize_trials_first: bool = False,
    skip_if_plan_csv_exists: bool = True,
    skip_if_plan_json_exists: bool = True,
    dry_run: bool = False,
    verbose_skip: bool = True,
    verbose_list: bool = True,            # Print the selected DOI list.
    success_json_dir: str = "mof_json_store",
    reasoning_effort: str = "medium",
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    trial_summary_csv: str | None = None,
):
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    df = read_excel_checked(excel_path)

    # Strict YES-only
    yes_dois = _load_yes_dois(positive_csv)
    if not yes_dois:
        print("[INFO] No DOIs marked 'yes' in positive_csv. Nothing to do.")
        return

    # Build candidates with de-dup by DOI
    candidates = []
    seen = set()
    for _, row in df.iloc[start_row:].iterrows():
        doi = str(row["DOI"]).strip()
        if not doi or doi in seen:
            continue
        seen.add(doi)
        if doi not in yes_dois:
            if verbose_skip:
                print(f"[SKIP NO/EMPTY] {doi} not marked 'yes'")
            continue
        main_file = str(row["Main File"]).strip()
        si_file   = str(row["SI File"]).strip() if pd.notna(row["SI File"]) else ""
        candidates.append({"doi": doi, "main_pdf": main_file, "si_pdf": si_file})

    # Skip by plan artifacts (CSV, JSON)
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

    # quick run clamp
    if quick_run_n is not None and quick_run_n > 0:
        items = items[:quick_run_n]

    # Count the DOIs remaining after all filters.
    total = len(items)
    if total == 0:
        print("Nothing to process for negative plan.")
        return

    # Label ranks for clearer START logs
    for i, it in enumerate(items, start=1):
        it["__rank"] = i
        it["__total"] = total

    print(f"Total DOIs to mine negative plan: {total}")
    if verbose_list:
        print("Selected DOIs:")
        for it in items:
            print(" ", f"[{it['__rank']}/{total}]", it["doi"])

    if dry_run:
        print("Dry run complete.")
        return items

    ensure_dir(Path(json_out_dir))
    ensure_dir(Path(csv_out).parent)
    if summarize_trials_first and os.path.exists(positive_csv):
        summary_path = trial_summary_csv or str(Path(csv_out).with_name("mof_trials_yes_7.csv"))
        ensure_dir(Path(summary_path).parent)
        summarize_trials_yes(positive_csv, summary_path)

    # If re-running, drop old CSV rows first for the selected DOIs
    if force_rerun and update_in_place and resume_mode == "csv":
        dois_to_update = {it["doi"] for it in items if it["doi"] in done_csv}
        if dois_to_update:
            removed = drop_rows_for_dois(csv_out, dois_to_update)
            print(f"[UPDATE] Removed {removed} old row(s) for {len(dois_to_update)} DOI(s) from {csv_out}")

    buffer = []
    processed = 0

    def _proc(it):
        # Keep the selected DOI rank in the progress log.
        doi = it["doi"]
        rank = it.get("__rank","?")
        tot  = it.get("__total","?")
        print(f"NEG-PLAN START [{rank}/{tot}] [{doi}]")
        return process_negative_item_yes(
            {"doi": doi, "main_pdf": it["main_pdf"], "si_pdf": it["si_pdf"]},
            model, json_out_dir, positive_csv, yes_dois,
            success_json_dir=success_json_dir, reasoning_effort=reasoning_effort,
            system_prompt=system_prompt, user_prompt_template=user_prompt_template,
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
    return {"processed_dois": processed, "selected_dois": total, "csv_out": csv_out}



def load_config(path: str | Path = DEFAULT_CONFIG) -> Dict[str, Any]:
    """Resolve input and output paths relative to the configured project root."""
    config_path = Path(path).expanduser().resolve()
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    root = (config_path.parent / settings.get("project_root", "..")).resolve()
    for key in ("manifest", "positive_csv", "success_json_dir", "csv_out", "json_out_dir",
                "trial_summary_csv", "system_prompt", "user_prompt"):
        if not settings.get(key):
            raise ValueError(f"Missing negative-extraction setting: {key}")
        settings[key] = str((root / settings[key]).resolve())
    if type(settings.get("concurrency")) is not int or settings["concurrency"] < 1:
        raise ValueError("concurrency must be a positive integer")
    if type(settings.get("start_row", 0)) is not int or settings.get("start_row", 0) < 0:
        raise ValueError("start_row must be a nonnegative integer")
    if settings.get("quick_run_n") is not None and (
        type(settings["quick_run_n"]) is not int or settings["quick_run_n"] < 1
    ):
        raise ValueError("quick_run_n must be null or a positive integer")
    for key in ("force_rerun", "update_in_place", "summarize_trials_first",
                "skip_if_plan_csv_exists", "skip_if_plan_json_exists", "verbose_skip", "verbose_list"):
        if type(settings.get(key)) is not bool:
            raise ValueError(f"{key} must be true or false")
    enumeration = settings.get("enumeration", {})
    for key in ("out_csv", "json_out_dir", "corrections_file"):
        if key not in enumeration:
            raise ValueError(f"Missing enumeration setting: {key}")
        if key == "corrections_file" and enumeration[key] is None:
            continue
        enumeration[key] = str((root / enumeration[key]).resolve())
    for key in ("yes_only", "skip_if_enum_csv_exists", "skip_if_enum_json_exists",
                "skip_empty_options", "verbose_skip"):
        if type(enumeration.get(key)) is not bool:
            raise ValueError(f"enumeration.{key} must be true or false")
    if type(enumeration.get("flush_every")) is not int or enumeration["flush_every"] < 1:
        raise ValueError("enumeration.flush_every must be a positive integer")
    settings["project_root"] = str(root)
    settings["config_file"] = str(config_path)
    return settings


def validate_config(config: Dict[str, Any] | str | Path = DEFAULT_CONFIG) -> Dict[str, Any]:
    """Inspect the local inputs without creating files or making model calls."""
    settings = load_config(config) if not isinstance(config, dict) else config
    required = ("manifest", "positive_csv", "system_prompt", "user_prompt")
    missing = [settings[key] for key in required if not Path(settings[key]).is_file()]
    report: Dict[str, Any] = {"missing_inputs": missing}
    if missing:
        return report
    manifest = read_excel_checked(settings["manifest"])
    positive = pd.read_csv(settings["positive_csv"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for name in ("doi", "article_trial_or_failure", "article_trial_or_failure_notes"):
        if name not in positive.columns:
            raise ValueError(f"Missing column in positive extraction: {name}")
    yes = positive[positive["article_trial_or_failure"].str.strip().str.lower() == "yes"]
    yes_dois = set(yes["doi"])
    manifest_dois = set(manifest["DOI"].str.strip())
    selected = manifest[manifest["DOI"].str.strip().isin(yes_dois)].drop_duplicates("DOI")
    report.update({
        "manifest_rows": len(manifest),
        "manifest_unique_dois": len(manifest_dois),
        "positive_yes_dois": len(yes_dois),
        "eligible_dois": len(selected),
        "yes_dois_without_manifest": sorted(yes_dois - manifest_dois),
        "yes_dois_without_notes": sorted(doi for doi in yes_dois if not _yes_note_for_doi(doi, settings["positive_csv"])),
        "missing_documents": [
            {"doi": row["DOI"], "column": column, "path": row[column]}
            for _, row in selected.iterrows() for column in ("Main File", "SI File")
            if row[column] and not Path(row[column]).is_file()
        ],
        "missing_success_bases": [
            row["DOI"] for _, row in selected.iterrows()
            if not _load_all_success_jsons(row["DOI"], settings["success_json_dir"], settings["positive_csv"])
        ],
    })
    return report


def _write_stage_metadata(settings: Dict[str, Any], stage: str) -> None:
    import hashlib
    metadata = {
        "stage": stage,
        "model": settings["model"],
        "reasoning_effort": settings["reasoning_effort"],
        "record_type": "evidence_guided_negative_plan" if stage == "plans" else "cartesian_reconstructed_condition",
        "interpretation": (
            "Plans contain both explicitly reported and inferred alternatives under the preserved prompt. "
            "Cartesian combinations are not individually verified experimental failures."
        ),
        "config": settings,
        "prompt_sha256": {
            key: hashlib.sha256(Path(settings[key]).read_bytes()).hexdigest()
            for key in ("system_prompt", "user_prompt")
        },
    }
    corrections = settings["enumeration"]["corrections_file"]
    if corrections is not None:
        data = Path(corrections).read_bytes()
        metadata["corrections_sha256"] = hashlib.sha256(data).hexdigest()
        metadata["corrections"] = json.loads(data)
    directory = Path(settings["csv_out"] if stage == "plans" else settings["enumeration"]["out_csv"]).parent
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stage}_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_from_config(
    config: Dict[str, Any] | str | Path = DEFAULT_CONFIG, *, dry_run: bool = False
):
    settings = load_config(config) if not isinstance(config, dict) else config
    arguments = {
        key: settings[key] for key in (
            "positive_csv", "csv_out", "json_out_dir", "trial_summary_csv", "model",
            "reasoning_effort", "concurrency", "start_row", "resume_mode", "force_rerun",
            "update_in_place", "quick_run_n", "summarize_trials_first", "skip_if_plan_csv_exists",
            "skip_if_plan_json_exists", "verbose_skip", "verbose_list", "success_json_dir"
        )
    }
    arguments["system_prompt"] = Path(settings["system_prompt"]).read_text(encoding="utf-8")
    arguments["user_prompt_template"] = Path(settings["user_prompt"]).read_text(encoding="utf-8")
    result = run_negative(settings["manifest"], dry_run=dry_run, **arguments)
    if not dry_run and result is not None:
        _write_stage_metadata(settings, "plans")
    return result


def enumerate_from_config(
    config: Dict[str, Any] | str | Path = DEFAULT_CONFIG, *, dry_run: bool = False
):
    from .enumerate_failures import enumerate_failures
    settings = load_config(config) if not isinstance(config, dict) else config
    options = dict(settings["enumeration"])
    options["enum_json_dir"] = options.pop("json_out_dir")
    result = enumerate_failures(
        settings["csv_out"], success_dir=settings["success_json_dir"],
        plan_json_dir=settings["json_out_dir"], dry_run=dry_run, **options
    )
    if not dry_run and result is not None:
        _write_stage_metadata(settings, "enumeration")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "mine", "enumerate"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true", help="Preview selected DOIs or base pairs without creating output or calling a model")
    args = parser.parse_args(argv)
    settings = load_config(args.config)
    if args.command == "validate":
        report = validate_config(settings)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return int(bool(report["missing_inputs"]))
    if args.command == "mine":
        run_from_config(settings, dry_run=args.dry_run)
    else:
        enumerate_from_config(settings, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
