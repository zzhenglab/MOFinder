"""Prepare condition-classification JSONL from the bundled curated records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mofinder.datasets.prepare import load_settings, prepare
from mofinder.display import display_path
from mofinder.demo_records import DemoRun, verify_files

DEMO_DIR = Path(__file__).resolve().parent


def _run(config_file=DEMO_DIR / "config.json", *, positive_csv=None, output_dir=None):
    """Run the same grouped split and dataset preparation used for the full dataset."""
    settings = load_settings(config_file)
    if positive_csv:
        settings["positive_csv"] = Path(positive_csv).resolve()
    if output_dir:
        settings["output_dir"] = Path(output_dir).resolve()
    result = prepare(settings)
    summary = result["summary"]
    out = Path(settings["output_dir"])
    train_clusters = set(result["train"]["cluster_key"])
    holdout_clusters = set(result["holdout"]["cluster_key"])
    compact = {
        "counts": summary["counts"],
        "labels": summary["labels"],
        "clusters": summary["clusters"],
        "shared_clusters": len(train_clusters & holdout_clusters),
    }
    (out / "demo_summary.json").write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")
    print(f"Training: {summary['counts']['train_rows']} records; holdout: {summary['counts']['holdout_rows']} records.")
    print(f"Shared clusters: {compact['shared_clusters']}")
    print(f"Output: {display_path(out)}")
    return compact


EXPECTED_FILES = ("mof_ft_train.jsonl", "mof_ft_holdout.jsonl", "mof_ft_class_map.json",
                  "demo_summary.json", "mof_ft_split_assignments.csv")


def verify_outputs(output_dir=DEMO_DIR / "outputs"):
    """Compare actual records, labels, counts, and assignments with expected files."""
    return verify_files(output_dir, DEMO_DIR / "expected", EXPECTED_FILES)


def run(config_file=DEMO_DIR / "config.json", *, positive_csv=None, output_dir=None, check=False, history_dir=None):
    settings = load_settings(config_file)
    out = Path(output_dir).resolve() if output_dir else Path(settings["output_dir"])
    inputs = {key: settings[key] for key in ("positive_csv", "negative_csv", "metadata_file", "prompt_file", "forced_questions_file")}
    if positive_csv:
        inputs["positive_csv"] = Path(positive_csv).resolve()
    inputs.update(config=Path(config_file).resolve(), runner=Path(__file__))
    inputs["preparation_code"] = DEMO_DIR.parents[1] / "src/mofinder/datasets/prepare.py"
    inputs["run_record_code"] = DEMO_DIR.parents[1] / "src/mofinder/demo_records.py"
    with DemoRun(DEMO_DIR, out, inputs, history_dir=history_dir) as record:
        summary = _run(config_file, positive_csv=positive_csv, output_dir=record.work_dir)
        if check:
            record.verification = verify_outputs(record.work_dir)
            print("Expected JSONL, labels, and split assignments:", "PASS" if record.verification["passed"] else "FAIL")
            if not record.verification["passed"]:
                raise AssertionError(f"Dataset preparation differs from expected; see {record.reference(record.record_path)}")
    summary.update(verification=record.verification, run_record=record.reference(record.record_path))
    print(f"Run record: {summary['run_record']}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEMO_DIR / "config.json")
    parser.add_argument("--positive-csv", type=Path, help="Use a newly generated processed positive table")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare with the bundled expected datasets")
    args = parser.parse_args()
    run(args.config, positive_csv=args.positive_csv, output_dir=args.output_dir, check=args.check)


if __name__ == "__main__":
    main()
