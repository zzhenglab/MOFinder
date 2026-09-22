"""Prepare condition-classification JSONL from the bundled curated records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from mofinder.datasets.prepare import load_settings, prepare

DEMO_DIR = Path(__file__).resolve().parent


def run(config_file=DEMO_DIR / "config.json", *, positive_csv=None, output_dir=None, check=False):
    """Run the same cluster split and JSONL preparation used for the full dataset."""
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
    if check:
        for name in ("mof_ft_train.jsonl", "mof_ft_holdout.jsonl", "mof_ft_class_map.json", "demo_summary.json"):
            if (out / name).read_text(encoding="utf-8") != (DEMO_DIR / "expected" / name).read_text(encoding="utf-8"):
                raise AssertionError(f"Generated {name} differs from the bundled expected output.")
        actual = pd.read_csv(out / "mof_ft_split_assignments.csv", keep_default_na=False)
        expected = pd.read_csv(DEMO_DIR / "expected/mof_ft_split_assignments.csv", keep_default_na=False)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
        print("Expected JSONL, labels, and split assignments match.")
    print(f"Training: {summary['counts']['train_rows']} records; holdout: {summary['counts']['holdout_rows']} records.")
    print(f"Shared clusters: {compact['shared_clusters']}")
    print(f"Output: {out}")
    return compact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEMO_DIR / "config.json")
    parser.add_argument("--positive-csv", type=Path, help="Use a newly generated cleaning-demo stage 6 table")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare with the bundled expected datasets")
    args = parser.parse_args()
    run(args.config, positive_csv=args.positive_csv, output_dir=args.output_dir, check=args.check)


if __name__ == "__main__":
    main()
