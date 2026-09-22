"""Rebuild positive-extraction CSV rows from saved JSON without API calls."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import argparse
import json

from .positive import (
    DEFAULT_CONFIG, already_done_dois, append_rows, load_config,
    read_manifest, sanitize_for_path,
)

def pick_reagents(rgs: List[Dict[str, Any]], n: int) -> List[Optional[Dict[str, Any]]]:
    rgs = rgs or []
    out = rgs[:n]
    while len(out) < n:
        out.append(None)
    return out

def pick_solvent_by_role(svs: List[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
    for s in svs or []:
        if (s or {}).get("role") == role:
            return s
    return None

# Flatten saved payloads to the extraction CSV schema.

def _rg_tuple(r: Optional[Dict[str, Any]]):
    if not r:
        return ("", "", "", "", "")
    return (
        r.get("name_full") or "",
        r.get("abbreviation") or "",
        r.get("amount_text") or "",
        r.get("amount_value") if r.get("amount_value") is not None else "",
        r.get("amount_unit") or "",
    )

def _sv_tuple(s: Optional[Dict[str, Any]]):
    if not s:
        return ("", "", "", "")
    return (
        s.get("name_full") or "",
        s.get("abbreviation") or "",
        s.get("amount_text") or "",
        s.get("amount_value_ml") if s.get("amount_value_ml") is not None else "",
    )

def flatten_rows_from_article_dir(
    doi: str,
    main_pdf: str,
    si_pdf: str,
    article_dir: Path
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    raw_json = article_dir / "raw_output.json"
    raw_txt  = article_dir / "raw_output.txt"
    raw_path = raw_json if raw_json.exists() else (raw_txt if raw_txt.exists() else None)

    article_parsed_path = article_dir / "article_extraction.json"
    syn_paths = sorted(article_dir.glob("synthesis_*.json"))

    trial_flag = ""
    trial_notes = ""
    syntheses: List[Dict[str, Any]] = []

    # The article payload is authoritative when valid. Individual synthesis
    # files recover an interrupted write when the article payload is absent or
    # unreadable; retain each recovered record's actual path.
    row_paths = []
    article_valid = False
    if article_parsed_path.exists():
        try:
            article_data = json.loads(article_parsed_path.read_text(encoding="utf-8"))
            if not isinstance(article_data, dict) or not isinstance(article_data.get("syntheses"), list):
                raise ValueError("Invalid article payload")
            syntheses = article_data["syntheses"]
            if not all(isinstance(item, dict) for item in syntheses):
                raise ValueError("Invalid synthesis payload")
            trial_flag = article_data.get("trial_or_failure_reported", "") or ""
            trial_notes = article_data.get("trial_or_failure_notes", "") or ""
            row_paths = [article_dir / f"synthesis_{i:03d}.json" for i in range(1, len(syntheses) + 1)]
            row_paths = [path if path.exists() else article_parsed_path for path in row_paths]
            article_valid = True
        except (ValueError, OSError, TypeError):
            syntheses = []
    if not article_valid:
        for path in syn_paths:
            try:
                synthesis = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(synthesis, dict) or "reference" not in synthesis:
                    raise ValueError("Invalid synthesis payload")
                syntheses.append(synthesis)
                row_paths.append(path)
            except (ValueError, OSError, TypeError):
                continue
        if not syntheses:
            raise ValueError(f"No readable parsed JSON payload in {article_dir}")

    # Build rows
    for idx, syn in enumerate(syntheses or [], start=1):
        m1, m2, m3 = [_rg_tuple(x) for x in pick_reagents(syn.get("metals") or [], 3)]
        l1, l2, l3 = [_rg_tuple(x) for x in pick_reagents(syn.get("linkers") or [], 3)]
        md1, md2   = [_rg_tuple(x) for x in pick_reagents(syn.get("modulators") or [], 2)]

        solv_main = pick_solvent_by_role(syn.get("solvents") or [], "main")
        solv_sec  = pick_solvent_by_role(syn.get("solvents") or [], "secondary")
        sm = _sv_tuple(solv_main)
        ss = _sv_tuple(solv_sec)

        cond = syn.get("conditions") or {}
        t_c = cond.get("temperature_c", "")
        t_h = cond.get("time_h", "")

        pp = syn.get("post_processing") or {}
        sp = syn.get("structure_properties") or {}

        row = {
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": str(raw_path) if raw_path else "",
            "parsed_json": str(row_paths[idx-1]),

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

            "temperature_c": t_c if t_c is not None else "",
            "temperature_c_text": cond.get("temperature_c_text") or "",
            "time_h": t_h if t_h is not None else "",
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
            "applications": ";".join(sp.get("applications") or []) if isinstance(sp.get("applications"), list) else (sp.get("applications") or ""),

            "reference": syn.get("reference") or doi,
            "status": "ok",
            "error": "",
        }
        rows.append(row)

    # If nothing to output, still log the DOI once
    if not rows:
        rows.append({
            "doi": doi, "main_pdf": main_pdf, "si_pdf": si_pdf,
            "raw_output": str(raw_path) if raw_path else "", "parsed_json": str(article_parsed_path) if article_parsed_path.exists() else "",
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


def backfill_from_json(excel_path: str, json_out_dir: str, csv_out: str,
                       flush_every: int = 50, *, article_dir=None, si_dir=None,
                       project_root=None) -> dict:
    """Append only unrecorded DOIs from saved JSON; never contact a model."""
    if type(flush_every) is not int or flush_every < 1:
        raise ValueError("flush_every must be a positive integer")
    frame = read_manifest(excel_path, article_dir=article_dir, si_dir=si_dir,
                          project_root=project_root)
    done = already_done_dois(csv_out)
    base = Path(json_out_dir)
    total = written_total = skipped_total = 0
    missing_list = []
    failed = []
    buffer = []
    for row in frame.drop_duplicates("DOI").to_dict("records"):
        doi = row["DOI"]
        if doi in done:
            continue
        article_path = base / sanitize_for_path(doi)
        if not article_path.is_dir():
            missing_list.append(doi)
            continue
        try:
            rows = flatten_rows_from_article_dir(doi, row["Main File"], row["SI File"], article_path)
        except (ValueError, TypeError, OSError, AttributeError) as error:
            # Keep an invalid payload eligible for repair and a later backfill.
            failed.append({"doi": doi, "error": str(error)})
            continue
        buffer.extend(rows)
        total += 1
        if len(buffer) >= flush_every:
            Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
            written, skipped = append_rows(csv_out, buffer)
            written_total += written
            skipped_total += skipped
            buffer = []
    if buffer:
        Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
        written, skipped = append_rows(csv_out, buffer)
        written_total += written
        skipped_total += skipped
    report = {"processed": total, "rows_written": written_total,
              "rows_skipped": skipped_total, "missing_json_dois": missing_list,
              "invalid_json_dois": failed}
    if missing_list:
        Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
        missing_path = Path(csv_out).parent / "missing_json_dois.txt"
        missing_path.write_text("\n".join(missing_list) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    report = backfill_from_json(config["manifest_file"], config["json_out_dir"],
                                config["csv_out"], flush_every=config["flush_every"],
                                article_dir=config["article_dir"], si_dir=config["si_dir"],
                                project_root=config["project_root"])
    print(json.dumps(report, indent=2))
    return int(bool(report["invalid_json_dois"] or report["rows_skipped"]))


if __name__ == "__main__":
    raise SystemExit(main())
