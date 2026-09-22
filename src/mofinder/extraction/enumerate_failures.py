"""Cartesian expansion of negative plans around recorded successful syntheses.

Enumerated combinations retain their parent success and plan provenance. They
are reconstructed candidate conditions, not independently observed experiments.
"""
from __future__ import annotations

import copy
import csv
import itertools
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from mofinder.display import display_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORRECTIONS = PROJECT_ROOT / "configs" / "negative_corrections.json"

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


def json_or_empty_list(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    if isinstance(x, (list, dict)):
        return x
    try:
        return json.loads(str(x))
    except Exception:
        return []


def read_success_syn(doi: str, idx_1based: int, success_dir: str = "mof_json_store", plan_json_dir: str | None = None) -> Optional[Dict[str, Any]]:
    """Load one success synthesis JSON by 1-based index. Fallback to article_extraction.json."""
    if plan_json_dir is not None:
        snapshot = Path(plan_json_dir) / sanitize_for_path(doi) / "success_bases.json"
        provenance_path = snapshot.with_name("plan_provenance.json")
        if provenance_path.exists():
            import hashlib
            try:
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
                if provenance.get("doi") != doi or provenance.get("success_snapshot") != snapshot.name:
                    raise ValueError("invalid parent snapshot reference")
                if not snapshot.is_file():
                    raise ValueError("recorded parent snapshot is missing")
                if hashlib.sha256(snapshot.read_bytes()).hexdigest() != provenance.get("success_snapshot_sha256"):
                    raise ValueError("recorded parent snapshot has changed")
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f"Cannot use recorded parent for {doi} index {idx_1based}: {exc}") from exc
        if snapshot.exists():
            try:
                data = json.loads(snapshot.read_text(encoding="utf-8"))
                syntheses = data["syntheses"]
                if data.get("doi") != doi or not isinstance(syntheses, list):
                    raise ValueError("invalid success snapshot")
                if not 1 <= idx_1based <= len(syntheses):
                    raise ValueError("success index is absent from the recorded model input")
                parent = syntheses[idx_1based - 1]
                if not isinstance(parent, dict):
                    raise ValueError("recorded parent synthesis is not an object")
                return parent
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Cannot use recorded parent for {doi} index {idx_1based}: {exc}") from exc
    base = Path(success_dir) / sanitize_for_path(doi)
    synp = base / f"synthesis_{idx_1based:03d}.json"
    if synp.exists():
        try:
            return json.loads(synp.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Fallback
    art = base / "article_extraction.json"
    if art.exists():
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
            syns = (data or {}).get("syntheses", [])
            if 1 <= idx_1based <= len(syns):
                return syns[idx_1based-1]
        except Exception:
            pass
    return None


def reagent_tuple(r: Optional[Dict[str, Any]]):
    if not r:
        return ("", "", "", "", "")
    return (
        r.get("name_full","") or "",
        r.get("abbreviation","") or "",
        r.get("amount_text","") or "",
        r.get("amount_value","") if r.get("amount_value") is not None else "",
        r.get("amount_unit","") or "",
    )


def pick_reagents(lst: Optional[List[Dict[str,Any]]], n: int) -> List[Optional[Dict[str,Any]]]:
    lst = lst or []
    if len(lst) >= n:
        return lst[:n]
    return lst + [None] * (n - len(lst))


def pick_solvent_by_role(lst: Optional[List[Dict[str,Any]]], role: str) -> Optional[Dict[str,Any]]:
    for s in lst or []:
        if s.get("role") == role:
            return s
    return None


def mk_amount_text(val, unit, kind="mol"):
    if val is None or unit is None or str(val) == "":
        return ""
    if kind == "mL":
        return f"{val} mL"
    return f"{val} {unit}"


def write_enum_json(doi: str, base_idx: int, combo_idx: int, payload: Dict[str, Any], enum_json_dir: str = "mof_negative_enum_store") -> str:
    root = Path(enum_json_dir) / sanitize_for_path(doi) / f"base_{base_idx:03d}"
    ensure_dir(root)
    p = root / f"combo_{combo_idx:04d}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def append_rows(csv_path: str, rows: List[Dict[str, Any]]):
    if not rows:
        return (0,0)
    header_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        w = None
        if not header_exists:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_ALL)
            w.writeheader()
        else:
            try:
                hdr = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=0).columns.tolist()
            except Exception:
                hdr = list(rows[0].keys())
            w = csv.DictWriter(f, fieldnames=hdr, quoting=csv.QUOTE_ALL)
        for r in rows:
            w.writerow(r)
    return (len(rows), 0)


def load_done_pairs_from_csv(enum_csv: str) -> Set[Tuple[str,int]]:
    done = set()
    if not os.path.exists(enum_csv):
        return done
    try:
        df = pd.read_csv(enum_csv, encoding="utf-8-sig", usecols=["doi","based_on_success_index"])
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


def enum_exists_for_pair(doi: str, base_idx: int, enum_json_dir: str = "mof_negative_enum_store") -> bool:
    b = Path(enum_json_dir) / sanitize_for_path(doi) / f"base_{base_idx:03d}"
    if not b.exists():
        return False
    for _ in b.glob("combo_*.json"):
        return True
    return False


def all_options_empty(metal_opts, linkr_opts, mod_opts, solv_opts, t_opts, h_opts) -> bool:
    def empty_or_none_list(lst):
        if not lst:
            return True
        return all(x is None for x in lst)
    return all([
        empty_or_none_list(metal_opts),
        empty_or_none_list(linkr_opts),
        empty_or_none_list(mod_opts),
        empty_or_none_list(solv_opts),
        empty_or_none_list(t_opts),
        empty_or_none_list(h_opts),
    ])


def keep_first_half(seq):
    """Return the first half of a list (rounded up). Keeps 1 item if length is 1."""
    if not seq:
        return []
    if isinstance(seq, dict):
        return [seq]
    if not isinstance(seq, list):
        try:
            seq = list(seq)
        except Exception:
            return []
    k = (len(seq) + 1) // 2  # ceil
    return seq[:k]


def enumerate_failures(
    failplan_csv: str = "mof_extraction_failplans.csv",
    out_csv: str = "mof_extraction_failures_enum.csv",
    *,
    success_dir: str = "mof_json_store",
    enum_json_dir: str = "mof_negative_enum_store",
    plan_json_dir: str | None = None,
    corrections_file: str | Path | None = DEFAULT_CORRECTIONS,
    yes_only: bool = True,
    skip_if_enum_csv_exists: bool = True,
    skip_if_enum_json_exists: bool = False,
    skip_empty_options: bool = True,
    verbose_skip: bool = True,
    dry_run: bool = False,
    flush_every: int = 500,
):
    """Expand option lists, preserving the original product order and CSV fields.

    Empty lists retain the corresponding successful condition. Corrections are
    applied before expansion. With CSV-based resume enabled, any existing
    DOI/base pair is skipped, including pairs with incomplete saved enumeration.
    """
    if flush_every < 1:
        raise ValueError("flush_every must be >= 1")
    corrections = load_corrections(corrections_file)
    YES_ONLY = yes_only
    SKIP_IF_ENUM_CSV_EXISTS = skip_if_enum_csv_exists
    SKIP_IF_ENUM_JSON_EXISTS = skip_if_enum_json_exists
    SKIP_EMPTY_OPTIONS = skip_empty_options
    VERBOSE_SKIP = verbose_skip
    DRY_RUN = dry_run
    FLUSH_EVERY = flush_every
    if not os.path.exists(failplan_csv):
        raise FileNotFoundError(f"Missing failplan CSV: {failplan_csv}")

    df = pd.read_csv(failplan_csv, encoding="utf-8-sig")

    required_cols = [
        "doi","main_pdf","si_pdf","raw_output","parsed_json",
        "article_trial_or_failure","article_trial_or_failure_notes",
        "mof_name","modification_notes","rationale",
        "based_on_success_index",
        "metal_1_options","linker_1_options","modulator_1_options",
        "solvent_main_options","temperature_c_options","time_h_options",
    ]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"Missing column in failplan CSV: {c}")

    # YES-only gate
    if YES_ONLY:
        df = df[df["article_trial_or_failure"].fillna("").str.strip().str.lower() == "yes"].copy()
    
    # One row per (doi, base_index) this run
    df["based_on_success_index"] = pd.to_numeric(df["based_on_success_index"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["based_on_success_index"])
    df["based_on_success_index"] = df["based_on_success_index"].astype(int)
    df_pairs = df.drop_duplicates(subset=["doi","based_on_success_index"]).reset_index(drop=True)

    # Apply the resume policy to existing CSV rows and combination JSON files.
    done_pairs_csv = load_done_pairs_from_csv(out_csv) if SKIP_IF_ENUM_CSV_EXISTS else set()

    to_process = []
    for _, r in df_pairs.iterrows():
        doi = str(r["doi"]).strip()
        base_idx = int(r["based_on_success_index"])
        exclusion = exclusion_for_pair(doi, base_idx, corrections)
        if exclusion is not None:
            if VERBOSE_SKIP:
                print(f"[DROP] {doi} base {base_idx}: {exclusion['reason']}")
            continue
        if base_idx < 1:
            raise ValueError(f"Invalid 1-based success index for {doi}: {base_idx}")

        reasons = []
        if SKIP_IF_ENUM_CSV_EXISTS and (doi, base_idx) in done_pairs_csv:
            reasons.append("enum_csv")
        if SKIP_IF_ENUM_JSON_EXISTS and enum_exists_for_pair(doi, base_idx, enum_json_dir):
            reasons.append("enum_json")
        if reasons:
            if VERBOSE_SKIP:
                print(f"[SKIP] {doi} base {base_idx} due to {', '.join(reasons)}")
            continue
        to_process.append(r)

    if DRY_RUN:
        print("Dry run. Would enumerate these pairs:")
        for r in to_process:
            print(" ", str(r['doi']).strip(), int(r['based_on_success_index']))
        return [{"doi": str(r["doi"]).strip(), "based_on_success_index": int(r["based_on_success_index"])} for r in to_process]

    if not to_process:
        print("Nothing to enumerate. All pairs appear to be done.")
        return

    ensure_dir(Path(enum_json_dir))
    ensure_dir(Path(out_csv).parent)

    # Track counts per DOI
    per_doi_counts: Dict[str,int] = {}
    buffer = []
    total_written = 0

    for row in to_process:
        doi = str(row["doi"]).strip()
        base_idx = int(row["based_on_success_index"])
        syn = read_success_syn(doi, base_idx, success_dir, plan_json_dir)
        if syn is None:
            print(f"[WARN] Missing base synthesis for DOI {doi} index {base_idx}")
            continue

        main_pdf   = str(row.get("main_pdf","") or "")
        si_pdf     = str(row.get("si_pdf","") or "")
        raw_plan   = str(row.get("raw_output","") or "")
        plan_json  = str(row.get("parsed_json","") or "")
        trial_note = str(row.get("article_trial_or_failure_notes","") or "")
        mof_name   = str(row.get("mof_name","") or "")
        mod_notes  = str(row.get("modification_notes","") or "")
        rationale  = str(row.get("rationale","") or "")

        # Parse option lists
        metal_opts = json_or_empty_list(row.get("metal_1_options"))
        linkr_opts = json_or_empty_list(row.get("linker_1_options"))
        mod_opts   = json_or_empty_list(row.get("modulator_1_options"))
        solv_opts  = json_or_empty_list(row.get("solvent_main_options"))
        t_opts     = json_or_empty_list(row.get("temperature_c_options"))
        h_opts     = json_or_empty_list(row.get("time_h_options"))

        option_lists = {
            "metal_1": metal_opts, "linker_1": linkr_opts, "modulator_1": mod_opts,
            "solvent_main": solv_opts, "temperature_c": t_opts, "time_h": h_opts,
        }
        option_lists = apply_option_corrections(doi, base_idx, option_lists, corrections)
        metal_opts = option_lists["metal_1"]
        linkr_opts = option_lists["linker_1"]
        mod_opts = option_lists["modulator_1"]
        solv_opts = option_lists["solvent_main"]
        t_opts = option_lists["temperature_c"]
        h_opts = option_lists["time_h"]

        # Skip plans with no alternatives to avoid labeling the base as a failure.
        if SKIP_EMPTY_OPTIONS and all_options_empty(metal_opts, linkr_opts, mod_opts, solv_opts, t_opts, h_opts):
            if VERBOSE_SKIP:
                print(f"[SKIP EMPTY] {doi} base {base_idx} has no options in any class")
            continue

        # Use None sentinel to keep base fields when a class has no options
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
            varied = []

            # Deep copy base synthesis and apply overrides
            syn_mod = copy.deepcopy(syn)

            # Ensure lists exist
            syn_mod.setdefault("metals", [])
            syn_mod.setdefault("linkers", [])
            syn_mod.setdefault("modulators", [])
            syn_mod.setdefault("solvents", [])
            syn_mod.setdefault("conditions", {})
            syn_mod.setdefault("post_processing", {})
            syn_mod.setdefault("structure_properties", {})

            # Metal_1
            if opt_m is not None:
                varied.append("metal_1")
                r = {
                    "name_full": opt_m.get("name_full",""),
                    "abbreviation": opt_m.get("abbreviation","") or "",
                    "amount_text": mk_amount_text(opt_m.get("amount_value"), opt_m.get("amount_unit"), kind="mol"),
                    "amount_value": opt_m.get("amount_value", None),
                    "amount_unit": opt_m.get("amount_unit","") or "",
                }
                if syn_mod["metals"]:
                    syn_mod["metals"][0] = r
                else:
                    syn_mod["metals"].append(r)

            # Linker_1
            if opt_l is not None:
                varied.append("linker_1")
                r = {
                    "name_full": opt_l.get("name_full",""),
                    "abbreviation": opt_l.get("abbreviation","") or "",
                    "amount_text": mk_amount_text(opt_l.get("amount_value"), opt_l.get("amount_unit"), kind="mol"),
                    "amount_value": opt_l.get("amount_value", None),
                    "amount_unit": opt_l.get("amount_unit","") or "",
                }
                if syn_mod["linkers"]:
                    syn_mod["linkers"][0] = r
                else:
                    syn_mod["linkers"].append(r)

            # Modulator_1
            if opt_md is not None:
                varied.append("modulator_1")
                r = {
                    "name_full": opt_md.get("name_full",""),
                    "abbreviation": opt_md.get("abbreviation","") or "",
                    "amount_text": mk_amount_text(opt_md.get("amount_value"), opt_md.get("amount_unit"), kind="mol"),
                    "amount_value": opt_md.get("amount_value", None),
                    "amount_unit": opt_md.get("amount_unit","") or "",
                }
                if syn_mod["modulators"]:
                    syn_mod["modulators"][0] = r
                else:
                    syn_mod["modulators"].append(r)

            # Solvent_main
            if opt_s is not None:
                varied.append("solvent_main")
                main_s = None
                for i, s0 in enumerate(syn_mod["solvents"]):
                    if s0.get("role") == "main":
                        main_s = i
                        break
                sobj = {
                    "name_full": opt_s.get("name_full",""),
                    "abbreviation": opt_s.get("abbreviation","") or "",
                    "amount_text": mk_amount_text(opt_s.get("amount_value_ml"), "mL", kind="mL"),
                    "amount_value_ml": opt_s.get("amount_value_ml", None),
                    "role": "main"
                }
                if main_s is not None:
                    syn_mod["solvents"][main_s] = sobj
                else:
                    syn_mod["solvents"].append(sobj)

            # Temperature
            if opt_t is not None:
                varied.append("temperature_c")
                syn_mod["conditions"]["temperature_c"] = opt_t
                syn_mod["conditions"]["temperature_c_text"] = f"{opt_t} °C"

            # Time
            if opt_h is not None:
                varied.append("time_h")
                syn_mod["conditions"]["time_h"] = opt_h
                syn_mod["conditions"]["time_text"] = f"{opt_h} h"

            # Save each combination with its parent index and varied fields.
            enum_payload = {
                "based_on_success_index": int(base_idx),
                "varied_classes": varied,
                "reference": syn_mod.get("reference", doi),
                "mof_name": mof_name or syn_mod.get("mof_name",""),
                "synthesis": syn_mod
            }
            enum_json_path = write_enum_json(doi, base_idx, combo_idx, enum_payload, enum_json_dir)

            # ------------ Flatten to CSV row ------------
            def rg_tuple(r: Optional[Dict[str, Any]]):
                if not r:
                    return ("", "", "", "", "")
                return (
                    r.get("name_full","") or "",
                    r.get("abbreviation","") or "",
                    r.get("amount_text","") or "",
                    r.get("amount_value","") if r.get("amount_value") is not None else "",
                    r.get("amount_unit","") or "",
                )

            m1, m2, m3 = [rg_tuple(x) for x in pick_reagents(syn_mod.get("metals"), 3)]
            l1, l2, l3 = [rg_tuple(x) for x in pick_reagents(syn_mod.get("linkers"), 3)]
            md1, md2   = [rg_tuple(x) for x in pick_reagents(syn_mod.get("modulators"), 2)]

            def sv_tuple(s: Optional[Dict[str, Any]]):
                if not s:
                    return ("", "", "", "")
                return (
                    s.get("name_full","") or "",
                    s.get("abbreviation","") or "",
                    s.get("amount_text","") or "",
                    s.get("amount_value_ml","") if s.get("amount_value_ml") is not None else "",
                )

            sm = sv_tuple(pick_solvent_by_role(syn_mod.get("solvents"), "main"))
            ss = sv_tuple(pick_solvent_by_role(syn_mod.get("solvents"), "secondary"))

            cond = syn_mod.get("conditions", {}) or {}
            t_c = cond.get("temperature_c", "")
            t_h = cond.get("time_h", "")
            temperature_c_text = cond.get("temperature_c_text","") or ""
            time_text = cond.get("time_text","") or ""
            vessel_type = cond.get("vessel_type","") or ""
            stirring = cond.get("stirring","") or ""

            pp = syn_mod.get("post_processing", {}) or {}
            washing_solvent = pp.get("washing_solvent","") or ""
            washing_cycles  = pp.get("washing_cycles","") or ""
            activation_text = pp.get("activation_text","") or ""
            activation_temp_c = pp.get("activation_temp_c","") if pp.get("activation_temp_c") is not None else ""
            activation_time_h = pp.get("activation_time_h","") if pp.get("activation_time_h") is not None else ""

            sp = syn_mod.get("structure_properties", {}) or {}

            row_out = {
                # Source files and paper-level notes.
                "doi": doi,
                "main_pdf": main_pdf,
                "si_pdf": si_pdf,
                "raw_output": raw_plan,
                "parsed_json": enum_json_path,
                "article_trial_or_failure": "yes" if trial_note else "",
                "article_trial_or_failure_notes": trial_note,
                "mof_name": mof_name or syn_mod.get("mof_name",""),
                "modification_notes": mod_notes,
                "rationale": rationale,

                # Tracking
                "based_on_success_index": base_idx,
                "varied_classes": ";".join(varied),

                # Reagents and solvents
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

                # Conditions
                "temperature_c": t_c, "temperature_c_text": temperature_c_text,
                "time_h": t_h, "time_text": time_text,
                "vessel_type": vessel_type, "stirring": stirring,

                # Post-processing
                "washing_solvent": washing_solvent, "washing_cycles": washing_cycles,
                "activation_text": activation_text, "activation_temp_c": activation_temp_c, "activation_time_h": activation_time_h,

                # Carry-through structure props from success (optional)
                "crystal_morphology": syn_mod.get("crystal_morphology","") or "",
                "yield_percent": syn_mod.get("yield_percent","") if syn_mod.get("yield_percent") is not None else "",
                "crystal_size": syn_mod.get("crystal_size","") or "",

                "topology_code": sp.get("topology_code","") or "",
                "metal_cluster_connectivity": sp.get("metal_cluster_connectivity","") or "",
                "unit_cell_short": sp.get("unit_cell_short","") or "",
                "pore_diameter_A": sp.get("pore_diameter_A","") if sp.get("pore_diameter_A") is not None else "",
                "BET_surface_area_m2g": sp.get("BET_surface_area_m2g","") if sp.get("BET_surface_area_m2g") is not None else "",
                "air_stable": sp.get("air_stable","") or "",
                "water_stable": sp.get("water_stable","") or "",
                "tga_decomposition_temp_c": sp.get("tga_decomposition_temp_c","") if sp.get("tga_decomposition_temp_c") is not None else "",
                "applications": ";".join(sp.get("applications", []) or []),

                "reference": syn_mod.get("reference", doi),
                "status": "ok", "error": ""
            }

            buffer.append(row_out)
            per_doi_counts[doi] = per_doi_counts.get(doi, 0) + 1

            if len(buffer) >= FLUSH_EVERY:
                written, _ = append_rows(out_csv, buffer)
                total_written += written
                buffer = []
                print(f"[FLUSH] wrote {written} rows to {display_path(out_csv)}. Total so far: {total_written}")

    if buffer:
        written, _ = append_rows(out_csv, buffer)
        total_written += written
        print(f"[FINAL FLUSH] wrote {written} rows to {display_path(out_csv)}. Total: {total_written}")

    # Print per-paper counts
    print("\nPer-DOI enumerated failures:")
    for d, n in sorted(per_doi_counts.items(), key=lambda x: x[0]):
        print(f"  {d}: {n}")
    print(f"\nTotal enumerated failure conditions: {total_written}")
    return {"rows_written": total_written, "per_doi_counts": per_doi_counts, "out_csv": out_csv}



def load_corrections(path: str | Path | None = DEFAULT_CORRECTIONS) -> Dict[str, Any]:
    """Read the explicit curation rules from the revised notebook."""
    if path is None:
        return {"schema_version": 1, "rules": []}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("rules"), list):
        raise ValueError("Corrections must contain schema_version 1 and a rules list")
    allowed_fields = {"metal_1", "linker_1", "modulator_1", "solvent_main", "temperature_c", "time_h"}
    for rule in data["rules"]:
        if not isinstance(rule, dict) or not rule.get("doi") or not rule.get("reason"):
            raise ValueError("Every correction requires a DOI and reason")
        if rule.get("action") not in {"exclude", "replace_options", "keep_first_half"}:
            raise ValueError(f"Unknown correction action: {rule.get('action')}")
        if rule["action"] != "exclude" and rule.get("field") not in allowed_fields:
            raise ValueError(f"Unknown correction field: {rule.get('field')}")
        if rule["action"] == "replace_options" and not isinstance(rule.get("values"), list):
            raise ValueError("Replacement options must be a list")
        if "base_indices" in rule and (
            not isinstance(rule["base_indices"], list)
            or any(type(index) is not int or index < 1 for index in rule["base_indices"])
        ):
            raise ValueError("Correction base_indices must contain positive integers")
    return data


def _matches_rule(rule: Dict[str, Any], doi: str, base_idx: int) -> bool:
    return rule["doi"] == doi and (
        "base_indices" not in rule or base_idx in rule["base_indices"]
    )


def exclusion_for_pair(doi: str, base_idx: int, corrections: Dict[str, Any]):
    return next((rule for rule in corrections["rules"]
                 if rule["action"] == "exclude" and _matches_rule(rule, doi, base_idx)), None)


def apply_option_corrections(
    doi: str, base_idx: int, options: Dict[str, Any], corrections: Dict[str, Any]
) -> Dict[str, Any]:
    result = copy.deepcopy(options)
    for rule in corrections["rules"]:
        if not _matches_rule(rule, doi, base_idx):
            continue
        if rule["action"] == "replace_options":
            result[rule["field"]] = copy.deepcopy(rule["values"])
        elif rule["action"] == "keep_first_half":
            result[rule["field"]] = keep_first_half(result[rule["field"]])
    return result
