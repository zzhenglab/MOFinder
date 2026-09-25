"""Data mining demo: triage, positive extraction, and negative reconstruction.

Model calls require API access; input validation runs offline.
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEMO_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from mofinder.display import display_path, display_paths

CONFIG_DIR = DEMO_DIR / "configs"
PLACEHOLDER_MARKER = "MOFINDER_DOCUMENT_PLACEHOLDER"


def require_api_key():
    """Reuse an environment key or request it without displaying the input."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        key = getpass.getpass("Enter your OpenAI API key: ").strip()
    if not key:
        raise ValueError("An API key is required for live requests.")
    os.environ["OPENAI_API_KEY"] = key


def validate_triage():
    from mofinder.config import load_triage_config
    from mofinder.literature.triage import validate_inputs, validation_summary

    config = load_triage_config(CONFIG_DIR / "triage.json")
    config["prompt_file"].read_text(encoding="utf-8")
    validated = validate_inputs(
        config["input_file"], config["ground_truth_file"],
        sheet=config["input_sheet"], benchmark_only=config["benchmark_only"],
        max_papers=config["max_papers"],
    )
    return validation_summary(validated)


def prepare_documents(config_dir=CONFIG_DIR):
    from mofinder.literature.match_documents import load_config, read_table, run_matching

    config = load_config(Path(config_dir) / "document_matching.json")
    if config.get("max_papers") is not None:
        limit = config["max_papers"]
        if type(limit) is not int or limit < 1:
            raise ValueError("max_papers must be a positive integer")
        count = len(read_table(config["input_file"]))
        if count > limit:
            raise ValueError(
                f"The inventory contains {count} papers; this demo is limited to {limit}. "
                "Select fewer inventory rows or increase max_papers in document_matching.json."
            )
    return run_matching(config)


def validate_positive(config_dir=CONFIG_DIR):
    from mofinder.extraction.positive import (
        load_config, read_any_text, read_manifest, validate_inputs,
    )

    prepare_documents(config_dir)
    config = load_config(Path(config_dir) / "positive_extraction.json")
    for key in ("system_prompt_file", "user_prompt_file"):
        config[key].read_text(encoding="utf-8")
    report = validate_inputs(config)
    if report["missing_files"] or report["dois_without_text"]:
        raise ValueError(f"The extraction documents need attention: {report}")
    manifest = read_manifest(
        config["manifest_file"], article_dir=config["article_dir"],
        si_dir=config["si_dir"], project_root=config["project_root"],
    )
    placeholders = []
    for row in manifest.to_dict("records"):
        for column in ("Main File", "SI File"):
            path = row[column]
            if path and PLACEHOLDER_MARKER in read_any_text(path):
                placeholders.append({"doi": row["DOI"], "role": column, "path": path})
    report["placeholder_documents"] = placeholders
    report["ready_for_live_extraction"] = not placeholders
    if placeholders:
        report["next_step"] = "Replace every listed template with the real document, keeping its DOI filename."
    return report


def validate_negative(config_dir=CONFIG_DIR):
    from mofinder.extraction.negative import load_config, validate_config

    config = load_config(Path(config_dir) / "negative_reconstruction.json")
    for key in ("system_prompt", "user_prompt"):
        Path(config[key]).read_text(encoding="utf-8")
    report = validate_config(config)
    if not Path(config["positive_csv"]).is_file():
        report["next_step"] = "Run positive --live to create the extraction CSV and synthesis JSON files."
    return report


def validate_all(config_dir=CONFIG_DIR):
    """Validate local inputs and create the document manifest for extraction."""
    return {
        "triage": validate_triage(),
        "positive_extraction": validate_positive(config_dir),
        "negative_reconstruction": validate_negative(config_dir),
    }


async def run_triage():
    from mofinder.literature.triage import screen

    validate_triage()
    require_api_key()
    return await screen(CONFIG_DIR / "triage.json")


def require_real_documents(report):
    """Exclude blank document templates from model requests."""
    if report["placeholder_documents"]:
        paths = [item["path"] for item in report["placeholder_documents"]]
        raise ValueError(
            "Replace the document templates before live extraction:\n" + "\n".join(paths)
        )


def run_positive(config_dir=CONFIG_DIR):
    from mofinder.extraction.positive import run_from_config

    require_real_documents(validate_positive(config_dir))
    require_api_key()
    return run_from_config(Path(config_dir) / "positive_extraction.json")


def run_negative(*, live=False, config_dir=CONFIG_DIR):
    from mofinder.extraction.negative import (
        enumerate_from_config, load_config, run_from_config,
    )

    documents = validate_positive(config_dir)
    if live:
        require_real_documents(documents)
    report = validate_negative(config_dir)
    problems = {
        key: report.get(key) for key in (
            "missing_inputs", "missing_documents", "missing_success_bases",
            "yes_dois_without_notes", "yes_dois_without_manifest",
        ) if report.get(key)
    }
    if problems:
        raise ValueError(
            "Negative reconstruction requires the positive extraction CSV and its synthesis "
            "JSON files. Inspect these inputs first: " + json.dumps(report, indent=2)
        )
    if not report["eligible_dois"]:
        return {"eligible_dois": 0, "message": "No documents were marked YES for trial or failure evidence."}
    config = load_config(Path(config_dir) / "negative_reconstruction.json")
    if not live:
        return {"validation": report, "selected_documents": run_from_config(config, dry_run=True)}
    require_api_key()
    plans = run_from_config(config)
    if not Path(config["csv_out"]).is_file():
        return {"plans": plans, "message": "No plan CSV was produced; enumeration was not run."}
    return {"plans": plans, "enumeration": enumerate_from_config(config)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", default="validate",
                        choices=("validate", "triage", "positive", "negative"))
    parser.add_argument("--live", action="store_true",
                        help="Send model requests; negative reconstruction also enumerates saved plans.")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR,
                        help="Directory containing document matching, positive extraction, and negative reconstruction configurations; triage uses configs/triage.json.")
    args = parser.parse_args(argv)
    if args.stage == "validate" and args.live:
        parser.error("Choose triage, positive, or negative with --live.")
    try:
        if args.stage == "validate":
            result = validate_all(args.config_dir)
        elif args.stage == "triage":
            if args.live:
                run = asyncio.run(run_triage())
                result = {"output_dir": str(run.output_dir),
                          "valid_answers": run.manifest["valid_answers"],
                          "expected_requests": run.manifest["expected_requests"]}
            else:
                result = validate_triage()
        elif args.stage == "positive":
            result = run_positive(args.config_dir) if args.live else validate_positive(args.config_dir)
        else:
            result = run_negative(live=args.live, config_dir=args.config_dir)
        print(json.dumps(display_paths(result), indent=2, ensure_ascii=False, default=str))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, display_path(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
