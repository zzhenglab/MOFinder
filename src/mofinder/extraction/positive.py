"""Concurrent extraction of primary MOF syntheses with file-backed JSON."""

from __future__ import annotations
from typing import List, Optional, Any, Dict, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import csv
import json
import os
import re
import threading
import time
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd

from .schemas import ArticleExtraction, Reagent, Solvent

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/positive_extraction.json"
DEFAULT_PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"

def _is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5).startswith(b"%PDF-")
    except Exception:
        return False

def _is_docx(path: str) -> bool:
    # DOCX is a ZIP with word/document.xml
    try:
        with zipfile.ZipFile(path) as z:
            return "word/document.xml" in z.namelist()
    except Exception:
        return False

def _is_doc_binary(path: str) -> bool:
    # Legacy .doc is OLE Compound File: D0 CF 11 E0 A1 B1 1A E1
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
    except Exception:
        return False

    
    
def read_pdf_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    if not _is_pdf(path):
        print(f"[SKIP NON-PDF] {path}")
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
    if not _is_docx(path):
        print(f"[SKIP NON-DOCX] {path}")
        return ""
    try:
        with zipfile.ZipFile(path) as z:
            xml_bytes = z.read("word/document.xml")
        # Simple DOCX text extractor
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(xml_bytes)
        paras = []
        for p in root.findall(".//w:p", ns):
            texts = [t.text or "" for t in p.findall(".//w:t", ns)]
            line = "".join(texts).strip()
            if line:
                paras.append(line)
        return "\n".join(paras)
    except Exception:
        print(f"[SKIP BAD DOCX] {path}")
        return ""

def read_doc_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    if not _is_doc_binary(path):
        print(f"[SKIP NON-DOC] {path}")
        return ""
    # Try textract if installed
    try:
        import textract
        b = textract.process(path)  # may need antiword/catdoc installed
        return b.decode("utf-8", errors="ignore")
    except Exception:
        print(f"[SKIP .doc needs textract or antiword] {path}")
        return ""

def read_any_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = Path(path).suffix.lower()
    if ext == ".pdf" or _is_pdf(path):
        return read_pdf_text(path)
    if ext == ".docx" or _is_docx(path):
        return read_docx_text(path)
    if ext == ".doc" or _is_doc_binary(path):
        return read_doc_text(path)
    print(f"[SKIP UNSUPPORTED] {path}")
    return ""

def safe_truncate(txt: str, max_chars: int = 400000) -> str:
    return txt[:max_chars] if txt and len(txt) > max_chars else (txt or "")

def pick_reagents(rgs: List[Any], n: int) -> List[Any]:
    rgs = rgs or []
    return rgs[:n] + [None] * max(0, n - len(rgs))

def pick_solvent_by_role(svs: List[Any], role: str):
    for s in svs or []:
        if getattr(s, "role", None) == role:
            return s
    return None

def sanitize_for_path(name: str) -> str:
    """Make a filesystem-safe slug for folder and file names."""
    if not name:
        return "unknown"
    s = name.strip()
    # Replace path separators and illegal characters
    s = s.replace("/", "_").replace("\\", "_").replace(":", "_")
    s = re.sub(r"[^A-Za-z0-9._\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_.")
    return s[:160] or "item"

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _atomic_text(path: Path, text: str) -> None:
    """Replace one payload only after its complete contents have been written."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_json_payloads(doi: str, raw_output: str, parsed_obj: ArticleExtraction, out_dir: str) -> Dict[str, Any]:
    """
    Save full JSON payloads separately from the tabular extraction summary.
    Returns dict with:
      raw_path: path to raw output json or txt
      article_parsed_path: path to full ArticleExtraction json
      syn_paths: list of paths to each SynthesisRecord json
    """
    base = Path(out_dir) / sanitize_for_path(doi)
    ensure_dir(base)

    # Save raw model output
    raw_json_path = base / "raw_output.json"
    raw_txt_path = base / "raw_output.txt"
    try:
        candidate = json.loads(raw_output)
    except (ValueError, TypeError):
        _atomic_text(raw_txt_path, raw_output if isinstance(raw_output, str) else str(raw_output))
        raw_json_path.unlink(missing_ok=True)
        raw_path = raw_txt_path
    else:
        _atomic_text(raw_json_path, json.dumps(candidate, ensure_ascii=False, indent=2))
        raw_txt_path.unlink(missing_ok=True)
        raw_path = raw_json_path

    # Save full ArticleExtraction
    article_parsed_path = base / "article_extraction.json"
    article_text = json.dumps(parsed_obj.model_dump(), ensure_ascii=False, indent=2)

    # Save each SynthesisRecord separately for per-row reference
    syn_paths: List[Path] = []
    for i, syn in enumerate(parsed_obj.syntheses or [], start=1):
        spath = base / f"synthesis_{i:03d}.json"
        _atomic_text(spath, json.dumps(syn.model_dump(), ensure_ascii=False, indent=2))
        syn_paths.append(spath)

    _atomic_text(article_parsed_path, article_text)
    # A shorter rerun must not leave obsolete syntheses for downstream indexing.
    for previous in base.glob("synthesis_*.json"):
        if re.fullmatch(r"synthesis_\d+\.json", previous.name) and previous not in syn_paths:
            previous.unlink()

    return {"raw_path": str(raw_path), "article_parsed_path": str(article_parsed_path), "syn_paths": [str(p) for p in syn_paths]}

def flatten_row(
    doi: str,
    main_pdf: str,
    si_pdf: str,
    raw_output_path: str,
    parsed_obj: ArticleExtraction,
    syn_json_paths: List[str],
    article_parsed_path: str
) -> List[Dict[str, Any]]:
    trial_flag = getattr(parsed_obj, "trial_or_failure_reported", "")
    trial_notes = getattr(parsed_obj, "trial_or_failure_notes", "")
    def rg_tuple(r: Optional[Reagent]):
        if not r:
            return ("", "", "", "", "")
        return (
            r.name_full or "",
            r.abbreviation or "",
            r.amount_text or "",
            r.amount_value if r.amount_value is not None else "",
            r.amount_unit or "",
        )

    def sv_tuple(s: Optional[Solvent]):
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
        # Reagents
        m1, m2, m3 = [rg_tuple(x) for x in pick_reagents(getattr(syn, "metals", []), 3)]
        l1, l2, l3 = [rg_tuple(x) for x in pick_reagents(getattr(syn, "linkers", []), 3)]
        md1, md2   = [rg_tuple(x) for x in pick_reagents(getattr(syn, "modulators", []), 2)]

        # Solvents
        solv_main = pick_solvent_by_role(getattr(syn, "solvents", []), "main")
        solv_sec  = pick_solvent_by_role(getattr(syn, "solvents", []), "secondary")
        sm = sv_tuple(solv_main)
        ss = sv_tuple(solv_sec)

        # Conditions
        cond = getattr(syn, "conditions", None)
        t_c = cond.temperature_c if cond else None
        t_h = cond.time_h if cond else None
        temperature_c_text = cond.temperature_c_text if cond else ""
        time_text = cond.time_text if cond else ""
        vessel_type = cond.vessel_type if cond else ""
        stirring = cond.stirring if cond else ""

        # Post-processing
        pp = getattr(syn, "post_processing", None)
        washing_solvent = pp.washing_solvent if pp else ""
        washing_cycles = pp.washing_cycles if pp else ""
        activation_text = pp.activation_text if pp else ""
        activation_temp_c = pp.activation_temp_c if (pp and pp.activation_temp_c is not None) else ""
        activation_time_h = pp.activation_time_h if (pp and pp.activation_time_h is not None) else ""

        # Structure props
        sp = getattr(syn, "structure_properties", None)

        row = {
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": raw_output_path,
            "parsed_json": syn_json_paths[idx-1] if idx-1 < len(syn_json_paths) else "",

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

            "temperature_c": t_c if t_c is not None else "",
            "temperature_c_text": temperature_c_text,
            "time_h": t_h if t_h is not None else "",
            "time_text": time_text,
            "vessel_type": vessel_type,
            "stirring": stirring,

            "washing_solvent": washing_solvent,
            "washing_cycles": washing_cycles,
            "activation_text": activation_text,
            "activation_temp_c": activation_temp_c,
            "activation_time_h": activation_time_h,

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
        }
        rows.append(row)

    # If nothing was extracted, emit one empty row to retain the DOI.
    if not rows:
        rows.append({
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": raw_output_path, "parsed_json": article_parsed_path,
            "article_trial_or_failure": "", "article_trial_or_failure_notes": "",

            "mof_name": "", "crystal_code": "",
            "metal_1":"", "metal_1_abbr":"", "metal_1_amount_text":"", "metal_1_amount_value":"", "metal_1_amount_unit":"",
            "metal_2":"", "metal_2_abbr":"", "metal_2_amount_text":"", "metal_2_amount_value":"", "metal_2_amount_unit":"",
            "metal_3":"", "metal_3_abbr":"", "metal_3_amount_text":"", "metal_3_amount_value":"", "metal_3_amount_unit":"",
            "linker_1":"", "linker_1_abbr":"", "linker_1_amount_text":"", "linker_1_amount_value":"", "linker_1_amount_unit":"",
            "linker_2":"", "linker_2_abbr":"", "linker_2_amount_text":"", "linker_2_amount_value":"", "linker_2_amount_unit":"",
            "linker_3":"", "linker_3_abbr":"", "linker_3_amount_text":"", "linker_3_amount_value":"", "linker_3_amount_unit":"",
            "modulator_1":"", "modulator_1_abbr":"", "modulator_1_amount_text":"", "modulator_1_amount_value":"", "modulator_1_amount_unit":"",
            "modulator_2":"", "modulator_2_abbr":"", "modulator_2_amount_text":"", "modulator_2_amount_value":"", "modulator_2_amount_unit":"",
            "solvent_main":"", "solvent_main_abbr":"", "solvent_main_amount_text":"", "solvent_main_ml":"",
            "solvent_secondary":"", "solvent_secondary_abbr":"", "solvent_secondary_amount_text":"", "solvent_secondary_ml":"",
            "temperature_c":"", "temperature_c_text":"", "time_h":"", "time_text":"", "vessel_type":"", "stirring":"",
            "washing_solvent":"", "washing_cycles":"", "activation_text":"", "activation_temp_c":"", "activation_time_h":"",
            "crystal_morphology":"", "yield_percent":"", "crystal_size":"",
            "topology_code":"", "metal_cluster_connectivity":"", "unit_cell_short":"",
            "pore_diameter_A":"", "BET_surface_area_m2g":"", "air_stable":"", "water_stable":"", "tga_decomposition_temp_c":"",
            "applications":"", "reference": doi, "status":"ok", "error":""
        })
    return rows


def read_csv_header(csv_path: str) -> Optional[List[str]]:
    """Read existing CSV header if file exists and is non-empty."""
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return None
    try:
        hdr_df = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=0)
        return list(hdr_df.columns)
    except Exception as error:
        raise ValueError(f"Cannot read the existing CSV header: {csv_path}") from error

def append_rows(csv_path: str, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Append rows to CSV with strict dimension checks.
    Returns (written_count, skipped_count).
    """
    if not rows:
        return (0, 0)

    existing_header = read_csv_header(csv_path)

    # Establish expected header
    if existing_header is None:
        # First write uses the first row's key order as the canonical header
        expected_header = list(rows[0].keys())
        header_needed = True
    else:
        expected_header = existing_header
        header_needed = False

    cleaned: List[Dict[str, Any]] = []
    skipped = 0

    # Validate each row has exactly the expected keys
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
        # Keep only expected keys and in fixed order
        cleaned.append({k: r.get(k, "") for k in expected_header})

    if not cleaned:
        return (0, skipped)

    df = pd.DataFrame(cleaned).fillna("")
    # sanitize only object/string columns
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].map(to_oneline)

    # Write
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        df.to_csv(f, index=False, header=header_needed, sep=",",
                  quoting=csv.QUOTE_ALL, doublequote=True, lineterminator="\n")
            
    return (len(df), skipped)

        
def already_done_dois(csv_path: str) -> set:
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return set()
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        return set(df['doi'].astype(str).tolist())
    except Exception as error:
        raise ValueError(f"Cannot resume from the existing CSV: {csv_path}") from error


def extract_one(client: Any, doi: str, main_pdf: str, si_pdf: str, model_name = "gpt-5",
                system_prompt: str | None = None, user_prompt_template: str | None = None):
    main_text = read_any_text(main_pdf)
    si_text = read_any_text(si_pdf) if si_pdf else ""
    if not main_text.strip() and not si_text.strip():
        raise ValueError(f"No readable article or supporting-information text for {doi}")
    if system_prompt is None:
        system_prompt = (DEFAULT_PROMPT_DIR / "positive_system.txt").read_text(encoding="utf-8")
    if user_prompt_template is None:
        user_prompt_template = (DEFAULT_PROMPT_DIR / "positive_user.txt").read_text(encoding="utf-8")
    user_msg = user_prompt_template.format(
        doi=doi,
        article_text=safe_truncate(main_text),
        si_text=safe_truncate(si_text),
    )
    resp = client.responses.parse(
        model=model_name,
        input=[{"role": "system", "content": system_prompt},
               {"role": "user", "content": user_msg}],
        text_format=ArticleExtraction,
    )
    raw_output = resp.output_text or json.dumps(resp.model_dump(), ensure_ascii=False)
    parsed: ArticleExtraction = resp.output_parsed
    if parsed is None:
        raise ValueError("The response did not contain a parsed ArticleExtraction")
    return raw_output, parsed

def extract_with_retry(client: Any, doi: str, main_pdf: str, si_pdf: str, model_name: str,
                       system_prompt: str | None = None, user_prompt_template: str | None = None):
    try:
        return extract_one(client, doi, main_pdf, si_pdf, model_name, system_prompt, user_prompt_template)
    except Exception:
        time.sleep(0.5)
        return extract_one(client, doi, main_pdf, si_pdf, model_name, system_prompt, user_prompt_template)


# ASCII control chars + DEL + NEL + Unicode LINE/PARAGRAPH separators
_HARD_BREAKS = re.compile(r'[\r\n\u0085\u2028\u2029]')
_CTRL = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
_ZERO_WIDTH = re.compile(r'[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]')

def to_oneline(val) -> str:
    if val is None:
        return ""
    s = val if isinstance(val, str) else str(val)

    # normalize composed characters (e.g., "°", accents)
    s = unicodedata.normalize("NFC", s)

    # PDF artifact: "·" as NUL+'b7' or the literal string "\u0000b7"
    s = s.replace("\x00b7", "·").replace("\\u0000b7", "·")

    # Normalize line breaks and remove control and zero-width characters.
    s = _HARD_BREAKS.sub("\n", s)
    s = _CTRL.sub(" ", s)
    s = _ZERO_WIDTH.sub("", s)

    # Replace nonbreaking spaces and tabs with ordinary spaces.
    s = s.replace("\u00A0", " ").replace("\t", " ")

    # collapse spaces and newlines, then escape newline as \n (literal)
    s = re.sub(r"[ ]{2,}", " ", s)
    s = re.sub(r"\n+", "\n", s).replace("\n", "\\n")
    return s

# Concurrency utilities and continuous worker queue.

def _process_item(item: Dict[str, str], model: str, json_out_dir: str,
                  system_prompt: str | None = None, user_prompt_template: str | None = None) -> Dict[str, Any]:
    """Worker that handles one DOI. Creates its own OpenAI client for thread safety."""
    doi = item["doi"]
    main_pdf = item["main_pdf"]
    si_pdf = item["si_pdf"]
    row_t0 = time.perf_counter()
    print(f"START [{doi}] on {threading.current_thread().name}")
    try:
        from openai import OpenAI
        client = OpenAI()  # expects OPENAI_API_KEY in env
        raw, parsed = extract_with_retry(client, doi, main_pdf, si_pdf, model, system_prompt, user_prompt_template)
        # Save complete payloads before flattening the CSV rows.
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
        row_dt = time.perf_counter() - row_t0
        print(f"DONE  [{doi}] in {row_dt:.2f}s, syntheses parsed: {synth_count}")
        return {
            "doi": doi,
            "rows": rows,
            "synth_count": synth_count,
            "status": "ok",
            "error": "",
            "elapsed": row_dt
        }
    except Exception as e:
        row_dt = time.perf_counter() - row_t0
        print(f"[ERROR] {doi}: {e}")
        rows = [{
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": "", "parsed_json": "",
            "article_trial_or_failure": "", "article_trial_or_failure_notes": "",
            "mof_name": "", "crystal_code": "",
            "metal_1":"", "metal_1_abbr":"", "metal_1_amount_text":"", "metal_1_amount_value":"", "metal_1_amount_unit":"",
            "metal_2":"", "metal_2_abbr":"", "metal_2_amount_text":"", "metal_2_amount_value":"", "metal_2_amount_unit":"",
            "metal_3":"", "metal_3_abbr":"", "metal_3_amount_text":"", "metal_3_amount_value":"", "metal_3_amount_unit":"",
            "linker_1":"", "linker_1_abbr":"", "linker_1_amount_text":"", "linker_1_amount_value":"", "linker_1_amount_unit":"",
            "linker_2":"", "linker_2_abbr":"", "linker_2_amount_text":"", "linker_2_amount_value":"", "linker_2_amount_unit":"",
            "linker_3":"", "linker_3_abbr":"", "linker_3_amount_text":"", "linker_3_amount_value":"", "linker_3_amount_unit":"",
            "modulator_1":"", "modulator_1_abbr":"", "modulator_1_amount_text":"", "modulator_1_amount_value":"", "modulator_1_amount_unit":"",
            "modulator_2":"", "modulator_2_abbr":"", "modulator_2_amount_text":"", "modulator_2_amount_value":"", "modulator_2_amount_unit":"",
            "solvent_main":"", "solvent_main_abbr":"", "solvent_main_amount_text":"", "solvent_main_ml":"",
            "solvent_secondary":"", "solvent_secondary_abbr":"", "solvent_secondary_amount_text":"", "solvent_secondary_ml":"",
            "temperature_c":"", "temperature_c_text":"", "time_h":"", "time_text":"", "vessel_type":"", "stirring":"",
            "washing_solvent":"", "washing_cycles":"", "activation_text":"", "activation_temp_c":"", "activation_time_h":"",
            "crystal_morphology":"", "yield_percent":"", "crystal_size":"",
            "topology_code":"", "metal_cluster_connectivity":"", "unit_cell_short":"",
            "pore_diameter_A":"", "BET_surface_area_m2g":"", "air_stable":"", "water_stable":"", "tga_decomposition_temp_c":"",
            "applications":"", "reference": doi, "status":"failed", "error": str(e)
        }]
        return {
            "doi": doi,
            "rows": rows,
            "synth_count": 0,
            "status": "failed",
            "error": str(e),
            "elapsed": row_dt
        }

def load_config(config_file=DEFAULT_CONFIG) -> dict:
    """Resolve all paths relative to the configured project root."""
    config_file = Path(config_file).expanduser().resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    root = (config_file.parent / config.get("project_root", "..")).resolve()
    path_keys = ("manifest_file", "article_dir", "si_dir", "csv_out", "json_out_dir",
                 "system_prompt_file", "user_prompt_file")
    for key in path_keys:
        if not config.get(key):
            raise ValueError(f"Missing configuration field: {key}")
        config[key] = (root / Path(config[key]).expanduser()).resolve()
    for key in ("concurrency", "flush_every"):
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if type(config.get("start_row", 0)) is not int or config.get("start_row", 0) < 0:
        raise ValueError("start_row must be a nonnegative integer")
    if not isinstance(config.get("model"), str) or not config["model"].strip():
        raise ValueError("model must be a nonempty string")
    config["project_root"] = root
    return config


def _document_path(value: str, directory: str | Path | None, project_root: str | Path | None) -> str:
    if not value:
        return ""
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    if directory is None:
        return str((Path(project_root or Path.cwd()) / path).resolve())
    # Bare filenames are relative to their document directory; paths written by
    # the manifest builder can also be relative to the project root.
    rooted = Path(project_root or Path.cwd()) / path
    if len(path.parts) > 1 and rooted.exists():
        return str(rooted.resolve())
    return str((Path(directory) / path).resolve())


def read_manifest(manifest_file: str | Path, *, article_dir=None, si_dir=None,
                  project_root=None) -> pd.DataFrame:
    """Read DOI, Main File and SI File from CSV or Excel, retaining text values."""
    path = Path(manifest_file)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        frame = pd.read_excel(path, dtype=str, keep_default_na=False)
    for col in ("DOI", "Main File", "SI File"):
        if col not in frame:
            raise ValueError(f"Missing column in manifest: {col}")
        frame[col] = frame[col].str.strip()
    if (frame["DOI"] == "").any():
        raise ValueError("The manifest contains an empty DOI")
    for col, directory in (("Main File", article_dir), ("SI File", si_dir)):
        frame[col] = frame[col].map(lambda value: _document_path(value, directory, project_root))
    seen = {}
    slugs = {}
    for row in frame.to_dict("records"):
        doi = row["DOI"]
        pair = (row["Main File"], row["SI File"])
        if doi in seen and seen[doi] != pair:
            raise ValueError(f"Conflicting document paths for duplicate DOI: {doi}")
        seen[doi] = pair
        slug = sanitize_for_path(doi)
        if slug in slugs and slugs[slug] != doi:
            raise ValueError(f"DOIs resolve to the same JSON directory: {slugs[slug]} and {doi}")
        slugs[slug] = doi
    return frame


def validate_inputs(config: dict) -> dict:
    """Inspect paths and extracted text locally without creating files or a client."""
    frame = read_manifest(config["manifest_file"], article_dir=config["article_dir"],
                          si_dir=config["si_dir"], project_root=config["project_root"])
    system = config["system_prompt_file"].read_text(encoding="utf-8")
    user = config["user_prompt_file"].read_text(encoding="utf-8")
    user.format(doi="10.example/example", article_text="", si_text="")
    if not system.strip():
        raise ValueError("The system prompt is empty")
    missing = []
    empty = []
    counts = []
    for row in frame.drop_duplicates("DOI").to_dict("records"):
        texts = []
        for col in ("Main File", "SI File"):
            path = row[col]
            if path and not Path(path).is_file():
                missing.append({"doi": row["DOI"], "column": col, "path": path})
            texts.append(read_any_text(path) if path else "")
        counts.append({"doi": row["DOI"], "article_characters": len(texts[0]),
                       "si_characters": len(texts[1])})
        if not any(text.strip() for text in texts):
            empty.append(row["DOI"])
    return {"rows": len(frame), "unique_dois": frame["DOI"].nunique(),
            "duplicate_rows": len(frame) - frame["DOI"].nunique(),
            "missing_files": missing, "dois_without_text": empty, "text_counts": counts}


def run(excel_path: str, csv_out: str = "mof_extraction.csv", start_row: int = 0,
        model: str = "gpt-5-mini", concurrency: int = 5, flush_every: int = 5,
        json_out_dir: str = "mof_json_store", *, article_dir=None, si_dir=None,
        project_root=None, system_prompt: str | None = None,
        user_prompt_template: str | None = None) -> dict:
    """Extract remaining DOIs using a continuous worker queue.

    ``excel_path`` accepts CSV or Excel with DOI, Main File and SI File columns.
    ``start_row`` is a zero-based row offset in the input table.
    Resume skips every DOI already recorded in the CSV, including failed rows.
    Repeated rows with identical DOI and document paths are submitted once.
    """
    for name, value in (("concurrency", concurrency), ("flush_every", flush_every)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if type(start_row) is not int or start_row < 0:
        raise ValueError("start_row must be a nonnegative integer")
    frame = read_manifest(excel_path, article_dir=article_dir, si_dir=si_dir,
                          project_root=project_root)
    done = already_done_dois(csv_out)
    items = [{"doi": row["DOI"], "main_pdf": row["Main File"], "si_pdf": row["SI File"]}
             for row in frame.iloc[start_row:].drop_duplicates("DOI").to_dict("records")
             if row["DOI"] not in done]
    n_total = len(items)
    print(f"Total to process: {n_total}")
    if not items:
        return {"processed": 0, "rows_written": 0, "rows_skipped": 0}
    ensure_dir(Path(json_out_dir))
    ensure_dir(Path(csv_out).parent)
    t0 = time.perf_counter()
    processed = written_total = skipped_total = 0
    buffer = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_process_item, item, model, str(json_out_dir),
                                   system_prompt, user_prompt_template) for item in items]
        for future in as_completed(futures):
            result = future.result()
            buffer.extend(result["rows"])
            processed += 1
            remaining = n_total - processed
            eta_sec = max(0.0, remaining * (time.perf_counter() - t0) / processed)
            print(f"[{processed}/{n_total}] {result['doi']} in {result['elapsed']:.2f}s, "
                  f"syntheses parsed: {result['synth_count']}, ETA {eta_sec / 60:.1f} min")
            if len(buffer) >= flush_every:
                written, skipped = append_rows(csv_out, buffer)
                written_total += written
                skipped_total += skipped
                buffer = []
    if buffer:
        written, skipped = append_rows(csv_out, buffer)
        written_total += written
        skipped_total += skipped
    return {"processed": processed, "rows_written": written_total, "rows_skipped": skipped_total}


def run_from_config(config_file=DEFAULT_CONFIG) -> dict:
    config = load_config(config_file)
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY before running extraction")
    return run(config["manifest_file"], csv_out=config["csv_out"],
               start_row=config.get("start_row", 0), model=config["model"],
               concurrency=config["concurrency"], flush_every=config["flush_every"],
               json_out_dir=config["json_out_dir"], article_dir=config["article_dir"],
               si_dir=config["si_dir"], project_root=config["project_root"],
               system_prompt=config["system_prompt_file"].read_text(encoding="utf-8"),
               user_prompt_template=config["user_prompt_file"].read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("--config", default=DEFAULT_CONFIG, type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        report = validate_inputs(load_config(args.config))
        print(json.dumps(report, indent=2))
        return int(bool(report["missing_files"] or report["dois_without_text"]))
    print(json.dumps(run_from_config(args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
