"""Clean the bundled positive extraction records with the main curation package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from mofinder.curation.pipeline import STAGES, run_stage
from mofinder.curation.times import TIME_PARSER_VERSION
from mofinder.display import display_path
from mofinder.demo_records import DemoRun, verify_files

DEMO_DIR = Path(__file__).resolve().parent
PRIVATE_COLUMNS = ("main_pdf", "si_pdf", "raw_output", "parsed_json")
AVAILABILITY_COLUMNS = ("has_main_document", "has_supporting_document")


def _run(config_file=DEMO_DIR / "config.json", *, output_dir=None):
    """Write stage tables and a before/after preview."""
    config_file = Path(config_file).resolve()
    root = config_file.parent
    config = json.loads(config_file.read_text(encoding="utf-8"))
    input_csv = root / config["input_csv"]
    lookup = root / config["linker_mw_csv"]
    prime_lookup = root / config["linker_prime_corrections"]
    output_dir = Path(output_dir).resolve() if output_dir else root / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(input_csv, dtype=str, keep_default_na=False)

    # Curation uses document availability for filtering and does not open PDFs.
    # Presence flags retain that information without distributing local paths.
    working = raw.copy()
    for flag, column in zip(AVAILABILITY_COLUMNS, ("main_pdf", "si_pdf")):
        if flag not in working:
            raise ValueError(f"Missing document availability column: {flag}")
        values = working[flag].str.strip().str.lower()
        if not values.isin({"true", "false"}).all():
            raise ValueError(f"{flag} must contain True or False.")
        working[column] = values.map({"true": "available", "false": ""})
    working = working.drop(columns=list(AVAILABILITY_COLUMNS))

    stages = []
    with TemporaryDirectory(prefix="mofinder_cleaning_") as directory:
        source = Path(directory) / "mof_extraction.csv"
        working.to_csv(source, index=False, encoding="utf-8-sig")
        settings = {
            "linker_mw_csv": lookup,
            "linker_prime_corrections": prime_lookup,
            "positive": {"input_csv": source, "output_dir": output_dir},
        }
        # The descriptions output is the input to condition dataset preparation.
        for stage in STAGES:
            result = run_stage(settings, "positive", stage, reports=False)
            stages.append({"stage": stage, "rows": result["rows"], "file": Path(result["output_csv"]).name})

    # Intermediate stages need the availability fields, but public tables do not.
    for name in {entry["file"] for entry in stages}:
        path = output_dir / name
        table = pd.read_csv(path, dtype=str, keep_default_na=False)
        table.drop(columns=list(PRIVATE_COLUMNS), errors="ignore").to_csv(path, index=False, encoding="utf-8-sig")

    final_file = output_dir / stages[-1]["file"]
    cleaned = pd.read_csv(final_file, dtype=str, keep_default_na=False)
    preview_columns = [
        "doi", "mof_name", "metal_1", "metal_1_amount_value", "metal_1_amount_unit",
        "linker_1", "linker_1_amount_value", "linker_1_amount_unit", "solvent_main",
        "solvent_main_ml", "temperature_c", "time_h", "time_text",
    ]
    raw[preview_columns].to_csv(output_dir / "raw_preview.csv", index=False, encoding="utf-8-sig")
    cleaned[preview_columns + ["M_L_ratio", "metel_concnertation"]].to_csv(output_dir / "cleaned_preview.csv", index=False, encoding="utf-8-sig")

    summary = {
        "input_rows": len(raw),
        "output_rows": len(cleaned),
        "time_parser": TIME_PARSER_VERSION,
        "input_sha256": hashlib.sha256(input_csv.read_bytes()).hexdigest(),
        "linker_mw_sha256": hashlib.sha256(lookup.read_bytes()).hexdigest(),
        "linker_prime_corrections_sha256": hashlib.sha256(prime_lookup.read_bytes()).hexdigest(),
        "stages": stages,
    }
    (output_dir / "demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Cleaned {len(raw)} input rows to {len(cleaned)} processed records.")
    print(f"Output: {display_path(output_dir)}")
    return summary


def verify_outputs(output_dir=DEMO_DIR / "outputs"):
    """Show the actual and expected row counts and compare every cleaned value."""
    return verify_files(output_dir, DEMO_DIR / "expected", ["mof_extraction_6.csv", "demo_summary.json"], rtol=1e-9, atol=1e-9)


def run(config_file=DEMO_DIR / "config.json", *, output_dir=None, check=False, history_dir=None):
    config_file = Path(config_file).resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    out = Path(output_dir).resolve() if output_dir else config_file.parent / config["output_dir"]
    inputs = {key: config_file.parent / config[key] for key in ("input_csv", "linker_mw_csv", "linker_prime_corrections")}
    inputs.update(config=config_file, runner=Path(__file__), expected=DEMO_DIR / "expected/mof_extraction_6.csv")
    source_root = DEMO_DIR.parents[1] / "src/mofinder"
    inputs.update({"code_" + path.stem: path for path in (source_root / "curation").glob("*.py")})
    inputs["run_record_code"] = source_root / "demo_records.py"
    with DemoRun(DEMO_DIR, out, inputs, history_dir=history_dir) as record:
        summary = _run(config_file, output_dir=record.work_dir)
        if check:
            record.verification = verify_outputs(record.work_dir)
            print("Expected cleaning output:", "PASS" if record.verification["passed"] else "FAIL")
            if not record.verification["passed"]:
                raise AssertionError(f"Cleaning output differs from expected; see {record.reference(record.record_path)}")
    summary.update(verification=record.verification, run_record=record.reference(record.record_path))
    print(f"Run record: {summary['run_record']}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEMO_DIR / "config.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare with the bundled expected tables")
    args = parser.parse_args()
    run(args.config, output_dir=args.output_dir, check=args.check)


if __name__ == "__main__":
    main()
