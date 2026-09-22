"""Run positive and negative synthesis curation with explicit local paths."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import csv
import hashlib
from importlib import import_module
import json
import math
from pathlib import Path
import sys

from .times import TIME_PARSER_VERSION

STAGES = ("initial", "metals", "linkers", "solvents", "features", "connectivity", "descriptions", "trimming")
PREFIXES = {"positive": "mof_extraction", "negative": "mof_extraction_failures_enum"}
STAGE_SUFFIXES = dict(zip(STAGES, ("_1", "_1_2", "_1_2_3", "_1_2_3_4", "_1_2_3_4_5", "_1_2_3_4_5", "_1_2_3_4_5_6", "_1_2_3_4_5_6_7")))


def load_config(path):
    """Resolve paths relative to the configured project root."""
    path = Path(path).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / data.get("project_root", "..")).resolve()
    def resolved(value):
        return (root / Path(value).expanduser()).resolve()
    data["project_root"] = root
    data["linker_mw_csv"] = resolved(data["linker_mw_csv"])
    if data.get("linker_prime_corrections"):
        data["linker_prime_corrections"] = resolved(data["linker_prime_corrections"])
    for mode in PREFIXES:
        data[mode] = dict(data[mode])
        for field in ("input_csv", "output_dir"):
            data[mode][field] = resolved(data[mode][field])
    return data


def stage_paths(settings, mode, stage):
    if mode not in PREFIXES:
        raise ValueError(f"Unknown curation mode: {mode}")
    if stage not in STAGES or (mode == "negative" and stage == "trimming"):
        raise ValueError(f"Stage {stage!r} is not available for {mode} curation")
    prefix = PREFIXES[mode]
    output_dir = Path(settings[mode]["output_dir"])
    output = output_dir / f"{prefix}{STAGE_SUFFIXES[stage]}.csv"
    position = STAGES.index(stage)
    if position == 0:
        source = Path(settings[mode]["input_csv"])
    else:
        source = output_dir / f"{prefix}{STAGE_SUFFIXES[STAGES[position - 1]]}.csv"
    return source, output


def validate_inputs(settings, mode="both", stage="all"):
    """Check selected inputs and the two-column molecular-weight table without writes."""
    issues, checks = [], []
    modes = tuple(PREFIXES) if mode == "both" else (mode,)
    if any(m not in PREFIXES for m in modes):
        raise ValueError(f"Unknown curation mode: {mode}")
    if stage not in (*STAGES, "all", "report"):
        raise ValueError(f"Unknown curation stage: {stage}")
    for current in modes:
        if stage in ("all", "initial"):
            path = Path(settings[current]["input_csv"])
        elif stage == "report":
            path = stage_paths(settings, current, "descriptions")[1]
        else:
            path = stage_paths(settings, current, stage)[0]
        check = {"mode": current, "input_csv": str(path), "exists": path.is_file()}
        if not path.is_file():
            issues.append(f"Missing {current} input: {path}")
        else:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                columns = next(reader, [])
                if not columns:
                    issues.append(f"CSV has no header: {path}")
                check["columns"] = len(columns)
                check["rows"] = sum(1 for _ in reader)
        checks.append(check)
    if stage in ("all", "linkers"):
        if settings.get("linker_prime_corrections"):
            from .linker_primes import load_corrections
            correction_path = Path(settings["linker_prime_corrections"])
            try:
                corrections = load_corrections(correction_path)
                checks.append({"linker_prime_corrections": str(correction_path), "doi_name_pairs": len(corrections)})
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append(f"Invalid linker prime correction lookup: {error}")
        lookup = Path(settings["linker_mw_csv"])
        if not lookup.is_file():
            issues.append(
                f"Missing linker molecular-weight table: {lookup}. Supply the headerless "
                "two-column linker-name/MW CSV used for the revised cleaning run and set "
                "linker_mw_csv in configs/curation.json. The supplied lookup is available "
                "at data/lookups/linker_molecular_weights.csv."
            )
        else:
            names, unresolved, count, known_rows, unknown_rows = {}, set(), 0, 0, 0
            with lookup.open(encoding="utf-8-sig", newline="") as stream:
                for line, row in enumerate(csv.reader(stream), 1):
                    if not row or not any(v.strip() for v in row):
                        continue
                    try:
                        if len(row) != 2 or not row[0].strip():
                            raise ValueError
                        # Blank weights preserve unresolved identities in the source table.
                        if not row[1].strip():
                            unresolved.add(row[0].strip().lower())
                            unknown_rows += 1
                            count += 1
                            continue
                        value = float(row[1])
                        if not math.isfinite(value) or value <= 0:
                            raise ValueError
                    except ValueError:
                        issues.append(f"Invalid linker MW row {line} in {lookup}: expected name and positive finite MW (g/mol) or a blank unresolved weight, without a header")
                        continue
                    key = row[0].strip().lower()
                    if key in names and names[key] != value:
                        issues.append(f"Conflicting molecular weights for {row[0]!r} in {lookup}")
                    names[key] = value
                    count += 1
                    known_rows += 1
            if not names:
                issues.append(f"Linker molecular-weight table has no usable rows: {lookup}")
            checks.append({
                "linker_mw_csv": str(lookup),
                "entries": count,
                "known_weight_rows": known_rows,
                "unknown_weight_rows": unknown_rows,
                "unique_names": len(set(names) | unresolved),
                "known_weight_names": len(names),
                "unknown_weight_names": len(unresolved - set(names)),
            })
    trim = settings.get("trimming", {})
    if stage in ("all", "trimming") and "positive" in modes:
        top_n, fraction = trim.get("top_n", 10), trim.get("yield_bottom_frac", 0.10)
        if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 0:
            issues.append("trimming.top_n must be a nonnegative integer")
        if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0 < fraction < 1:
            issues.append("trimming.yield_bottom_frac must be between 0 and 1")
    return {"valid": not issues, "checks": checks, "issues": issues}


def run_stage(settings, mode, stage, *, reports=True, plots=False):
    """Run one configured cleaning stage and save its CSV output."""
    validation = validate_inputs(settings, mode, stage)
    if not validation["valid"]:
        raise ValueError("\n".join(validation["issues"]))
    source, output = stage_paths(settings, mode, stage)
    output.parent.mkdir(parents=True, exist_ok=True)
    module = import_module(f"mofinder.curation.{stage}")
    function = getattr(module, f"clean_{mode}" if stage in {"initial", "linkers", "descriptions"} else "clean")
    kwargs = {}
    if stage == "initial":
        kwargs["plot_dir"] = output.parent / "reports" / "plots" if plots else None
    elif stage == "metals":
        kwargs["report_limit"] = 50 if mode == "positive" else 20
    elif stage == "linkers":
        kwargs["linker_mw_path"] = settings["linker_mw_csv"]
        kwargs["linker_prime_corrections"] = settings.get("linker_prime_corrections")
    elif stage == "trimming":
        kwargs.update(settings.get("trimming", {}))
    if reports:
        report_dir = output.parent / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        with (report_dir / f"{stage}.txt").open("w", encoding="utf-8") as stream, redirect_stdout(stream):
            frame = function(source, output, **kwargs)
    else:
        from io import StringIO
        with redirect_stdout(StringIO()):
            frame = function(source, output, **kwargs)
    return {"stage": stage, "input_csv": str(source), "output_csv": str(output), "rows": len(frame)}


def write_report(settings, mode, *, top_n_metals=None, top_n_linkers=None):
    """Describe the untrimmed stage-6 records, matching the source report order."""
    validation = validate_inputs(settings, mode, "report")
    if not validation["valid"]:
        raise ValueError("\n".join(validation["issues"]))
    from .reporting import summarize
    source = stage_paths(settings, mode, "descriptions")[1]
    report_dir = Path(settings[mode]["output_dir"]) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "summary.txt").open("w", encoding="utf-8") as stream, redirect_stdout(stream):
        summarize(source, report_dir, top_n_metals=top_n_metals, top_n_linkers=top_n_linkers)
    return report_dir


def run_pipeline(settings, mode="both", *, reports=True, plots=False, trim_positive=True):
    """Write intermediate and final tables for the requested extraction branches."""
    validation = validate_inputs(settings, mode, "all")
    if not validation["valid"]:
        raise ValueError("\n".join(validation["issues"]))
    modes = tuple(PREFIXES) if mode == "both" else (mode,)
    results = {}
    for current in modes:
        stages = STAGES if current == "positive" and trim_positive else STAGES[:-1]
        completed = []
        for stage in stages:
            record = run_stage(settings, current, stage, reports=reports, plots=plots)
            completed.append(record)
            if record["rows"] == 0 and stage != stages[-1]:
                raise ValueError(
                    f"No records remain after {current} {stage}; saved {record['output_csv']}. "
                    "Inspect the stage report before continuing."
                )
            if stage == "descriptions" and reports:
                write_report(settings, current)
        source = Path(settings[current]["input_csv"])
        lookup = Path(settings["linker_mw_csv"])
        results[current] = {
            "mode": current,
            "mass_parser": "whole-fragment-coefficients-v2",
            "time_parser": TIME_PARSER_VERSION,
            "linker_alias_revision": "h3btb-tris-carboxyphenyl-benzene-v1",
            "input_csv": str(source),
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "linker_mw_csv": str(lookup),
            "linker_mw_sha256": hashlib.sha256(lookup.read_bytes()).hexdigest(),
            "trimming": settings.get("trimming", {}) if current == "positive" and trim_positive else None,
            "stages": completed,
            "output_csv": completed[-1]["output_csv"],
        }
        if settings.get("linker_prime_corrections"):
            correction_path = Path(settings["linker_prime_corrections"])
            results[current]["linker_prime_corrections"] = str(correction_path)
            results[current]["linker_prime_corrections_sha256"] = hashlib.sha256(correction_path.read_bytes()).hexdigest()
        (Path(settings[current]["output_dir"]) / "curation_manifest.json").write_text(
            json.dumps(results[current], indent=2) + "\n", encoding="utf-8"
        )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate-inputs", "run", "report"))
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[3] / "configs" / "curation.json")
    parser.add_argument("--mode", choices=("positive", "negative", "both"), default="both")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--no-reports", action="store_true")
    parser.add_argument("--plots", action="store_true", help="Save initial-stage histograms without opening a window")
    parser.add_argument("--no-trim", action="store_true", help="Finish positive curation at stage 6")
    args = parser.parse_args(argv)
    try:
        settings = load_config(args.config)
        if args.command == "validate-inputs":
            result = validate_inputs(settings, args.mode, args.stage)
            print(json.dumps(result, indent=2))
            return 0 if result["valid"] else 1
        if args.command == "report":
            modes = tuple(PREFIXES) if args.mode == "both" else (args.mode,)
            result = {mode: str(write_report(settings, mode)) for mode in modes}
        elif args.stage == "all":
            result = run_pipeline(settings, args.mode, reports=not args.no_reports, plots=args.plots, trim_positive=not args.no_trim)
        else:
            modes = tuple(PREFIXES) if args.mode == "both" else (args.mode,)
            result = {mode: run_stage(settings, mode, args.stage, reports=not args.no_reports, plots=args.plots) for mode in modes}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"Curation error: {error}", file=sys.stderr)
        return 1
