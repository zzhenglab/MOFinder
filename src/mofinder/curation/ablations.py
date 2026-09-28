"""Reproduce the two fixed-split negative-data ablations from processed CSVs.

Run from a MOFinder checkout with
``python -m mofinder.curation.ablations --output NEW_OUTPUT_DIRECTORY``.
The existing dataset preparation code regenerates and verifies the standard
split first. Only training negatives change; the holdout is copied unchanged.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
import shutil
import tempfile

from mofinder.datasets import prepare as baseline
from mofinder.training.common import sha256
from .ablation_analysis import (analyze_neighbors, conditions_and_label, count_summary,
                               load_jsonl, minimum_distances)
from .artificial_control import (generate, generate_count_matched, inputs,
                                 processed_condition_keys)


RANDOM_DROP_SEEDS = (101, 202, 303, 404, 505)
ARTIFICIAL_SEED = 101
# These references make accidental cohort/split changes fail before publication.
REFERENCE_HASHES = {
    "data/processed_data/processed_positive.csv": "c348398050f74de5bb275546890dc26d95bbc6f49175f856ac8f6d654757c7c5",
    "data/processed_data/processed_negative.csv": "9e0db15503a21eed93c34af0de05a932df4a6fa8c9f4b7e42d32d279ad774ce7",
    "data/processed_data_json/train.jsonl": "815e0ff6d2728547d5e644c6fc1b9c583d75b053a011fa3a3962b91e179cd095",
    "data/processed_data_json/holdout.jsonl": "e60678f291fa59367c473741f8f543ae587c3c57ec2c1920fac9cf8c238fbd55",
    "data/processed_data_json/split_assignments.csv": "68946ccd61d1c4665e6896f937ee514bee31bc2a3025cc9776e7fdeb669e10aa",
}
EXPECTED_TRAIN_HASHES = {
    "train_leave_one_perturbation_out.jsonl": "859511bbfe4cf5c7391281003c2d1d2a106dc04883d935300ca40b0114a6c8ea",
    "train_random_drop_seed101.jsonl": "aa9c26294accd0ddb214c0ddeaa020f6326d8bce96c055fc720b1c99f380eb9c",
    "train_random_drop_seed202.jsonl": "7fe8a3b107a26a3190cca80c7067037bb0a6d1dbb064ce52bd746e24718b4df0",
    "train_random_drop_seed303.jsonl": "f3095a986717deb17256fc11c61779742b02d39703c8591e5d99fbcc8c5d7b66",
    "train_random_drop_seed404.jsonl": "d4ede1f4dc20c935ffd637f2a6ee8500b64adc29a07c07070f70da83ea465d94",
    "train_random_drop_seed505.jsonl": "0f0a2094f14f4596916440a08c7b6ffa476fc2fd66f2e3063fcf8f69920030aa",
    "train_artificial_field_matched.jsonl": "426b6dc74df430e7089e466145c9a6a217c8eb024b811814dba0bc36055c645e",
    "train_artificial_count_matched.jsonl": "c10877d31045f72c31f11c5331a2c710a158a2a5cf76ad763808b11afe6a41ab",
}


def _save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
                          + "\n", encoding="utf-8", newline="\n")


def _save_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False)
                             if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})


def _check_references(repo):
    for name, expected in REFERENCE_HASHES.items():
        if sha256(repo / name) != expected:
            raise ValueError(f"Study input or standard split changed: {name}")


def _baseline_stages(summary):
    labels = summary["labels"]
    pre_balance = summary["counts_before_pn_enforcement"]
    deduplicated = {label: sum(pre_balance[split][label] for split in ("train", "holdout"))
                    for label in ("P", "N")}
    stages = [
        ("Processed CSV input", labels["input"]),
        ("Required-field filtering", labels["after_required_field_checks"]),
        ("Contradictory N filtering", labels["after_conflict_filter"]),
        ("Within-label deduplication", deduplicated),
        ("Fixed split and P:N balancing", labels["after_all_drops"]),
    ]
    result = []
    previous = stages[0][1]
    for stage, retained in stages:
        dropped = {label: previous[label] - retained[label] for label in ("P", "N")}
        print(f"{stage}: P={retained['P']:,}, N={retained['N']:,}; "
              f"dropped P={dropped['P']:,}, N={dropped['N']:,}", flush=True)
        result.append({"stage": stage, "retained": retained, "dropped": dropped})
        previous = retained
    return result


def _prepare_baseline(repo, work):
    settings = baseline.load_settings(repo / "configs/dataset_preparation.json")
    settings["output_dir"] = work / "baseline"
    print("Rebuilding the standard split from processed positive and negative CSVs...", flush=True)
    result = baseline.prepare(settings)
    stages = _baseline_stages(result["summary"])
    paths = {split: settings["output_dir"] / f"mof_ft_{split}.jsonl"
             for split in ("train", "holdout")}
    for split, path in paths.items():
        if sha256(path) != REFERENCE_HASHES[f"data/processed_data_json/{split}.jsonl"]:
            raise ValueError(f"Regenerated {split} differs in content or row order from the standard split")
    assignment_path = settings["output_dir"] / "mof_ft_split_assignments.csv"
    # pandas' CSV newline convention differs across platforms. Check every cell
    # and row against the archived table, without rewriting model JSONL bytes.
    with assignment_path.open(encoding="utf-8-sig", newline="") as actual:
        with (repo / "data/processed_data_json/split_assignments.csv").open(
                encoding="utf-8-sig", newline="") as reference:
            if list(csv.reader(actual)) != list(csv.reader(reference)):
                raise ValueError("Regenerated split assignments differ from the standard split")
    return paths, assignment_path, stages, result["summary"]["labels"]


def _source_rows(assignment_path, splits):
    """Map model row order back to the verified standard split assignments."""
    with assignment_path.open(encoding="utf-8-sig", newline="") as handle:
        assignments = list(csv.DictReader(handle))
    lookup = {}
    for assignment in assignments:
        if assignment["is_success"] not in ("True", "False"):
            raise ValueError("Invalid label in split assignments")
        label = "P" if assignment["is_success"] == "True" else "N"
        key = (assignment["condition_key"], label)
        if key in lookup:
            raise ValueError("Ambiguous condition/label mapping in split assignments")
        lookup[key] = assignment
    tables, seen = {}, set()
    for split, records in splits.items():
        tables[split] = {}
        for index, record in enumerate(records, 1):
            values, label = conditions_and_label(record)
            key = (baseline.forced_question_condition_key(values), label)
            assignment = lookup[key]
            source_id = int(assignment["source_row_id"])
            if assignment["split"] != split or source_id in seen:
                raise ValueError("Wrong split or reused source row in model-to-source mapping")
            seen.add(source_id)
            tables[split][index] = dict(assignment, label=label)
    if len(seen) != len(assignments):
        raise ValueError("Not all verified source rows were mapped")
    return tables


def _export(path, records, baseline_records, baseline_lines, indices, *, synthetic=False, seed=None):
    indices = list(indices)
    with path.open("wb") as stream:
        for index in indices:
            if not synthetic or baseline_records[index]["messages"][2]["content"] == "P":
                stream.write(baseline_lines[index])
            else:
                stream.write((json.dumps(records[index], ensure_ascii=False, allow_nan=False)
                              + "\n").encode("utf-8"))
    loaded = load_jsonl(path)
    if loaded != [records[index] for index in indices]:
        raise ValueError(f"Export changed selected record order or contents: {path.name}")
    expected_positives = [record for record in baseline_records if record["messages"][2]["content"] == "P"]
    if [record for record in loaded if record["messages"][2]["content"] == "P"] != expected_positives:
        raise ValueError(f"Positive training records changed: {path.name}")
    digest = sha256(path)
    if digest != EXPECTED_TRAIN_HASHES[path.name]:
        raise ValueError(f"Generated dataset does not reproduce the study bytes: {path.name}")
    counts = Counter(record["messages"][2]["content"] for record in loaded)
    dropped = {"P": 11968 - counts["P"], "N": 11560 - counts["N"]}
    row = {"file": path.name, "seed": seed, "rows": len(loaded), "labels": dict(counts),
           "dropped": dropped, "original_N_replaced": 11560 if synthetic else 0, "sha256": digest}
    print(f"{path.name}: P={counts['P']:,}, N={counts['N']:,}; dropped P={dropped['P']:,}, "
          f"N={dropped['N']:,}; original N replaced={row['original_N_replaced']:,}", flush=True)
    return row


def build(repo, output):
    """Generate both study controls into a new directory, verifying exact bytes."""
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Choose a new output directory; refusing to overwrite {output}")
    _check_references(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Temporary outputs are isolated; expose the final directory only on success.
    with tempfile.TemporaryDirectory(prefix=".mofinder-ablations-", dir=output.parent) as temporary:
        work = Path(temporary).resolve()
        if work.parent != output.parent:
            raise ValueError("Unexpected temporary directory location")
        paths, assignments, stages, baseline_counts = _prepare_baseline(repo, work)
        train, holdout = load_jsonl(paths["train"]), load_jsonl(paths["holdout"])
        if len(train) != 23528 or len(holdout) != 2595:
            raise ValueError("Standard split row counts changed")
        lines = paths["train"].read_bytes().splitlines(keepends=True)
        sources = _source_rows(assignments, {"train": train, "holdout": holdout})
        analysis = analyze_neighbors(train, holdout, sources["train"], sources["holdout"])
        removed = {row["baseline_row_1based"] - 1 for row in analysis["train_negative"]
                   if row["min_changed_fields"] == 1}
        negatives = [index for index, record in enumerate(train) if record["messages"][2]["content"] == "N"]
        keep_n = len(negatives) - len(removed)
        if len(removed) != 3827 or keep_n != 7733:
            raise ValueError("Single-field removal count changed")
        staged = work / "datasets"
        single = staged / "leave_one_perturbation_out"
        artificial = staged / "artificial_perturbation"
        metadata = staged / "metadata"
        for directory in (single, artificial, metadata):
            directory.mkdir(parents=True)
        for directory in (single, artificial):
            shutil.copyfile(paths["holdout"], directory / "holdout.jsonl")
            if (directory / "holdout.jsonl").read_bytes() != paths["holdout"].read_bytes():
                raise ValueError("Holdout bytes changed")
        kept = [index for index in range(len(train)) if index not in removed]
        single_counts = [_export(single / "train_leave_one_perturbation_out.jsonl", train, train, lines, kept)]
        for seed in RANDOM_DROP_SEEDS:
            selected = set(random.Random(seed).sample(negatives, keep_n))
            indices = [index for index, record in enumerate(train)
                       if record["messages"][2]["content"] == "P" or index in selected]
            single_counts.append(_export(single / f"train_random_drop_seed{seed}.jsonl",
                                         train, train, lines, indices, seed=seed))
        forbidden = processed_condition_keys(repo / "data/processed_data/processed_positive.csv",
                                             repo / "data/processed_data/processed_negative.csv")
        artificial_counts = []
        for variant, generator in (("field_matched", generate), ("count_matched", generate_count_matched)):
            print(f"Generating {variant} artificial negatives with seed {ARTIFICIAL_SEED}...", flush=True)
            options = {"excluded_condition_keys": forbidden} if variant == "count_matched" else {}
            generated, provenance, diagnostics = generator(
                train, holdout, analysis["train_negative"], sources["train"], sources["holdout"],
                ARTIFICIAL_SEED, **options)
            diagnostics["variant"] = variant
            nearest = minimum_distances(
                [(i, inputs(r)) for i, r in enumerate(train, 1) if r["messages"][2]["content"] == "P"],
                [(i, inputs(r)) for i, r in enumerate(generated, 1) if r["messages"][2]["content"] == "N"],
                sources["train"], sources["train"])
            diagnostics["synthetic_nearest_training_positive"] = count_summary(nearest)
            diagnostics["real_nearest_training_positive"] = analysis["summary"]["train"]
            diagnostics["nearest_distance_changed_from_reference_mask_rows"] = sum(
                a["min_changed_fields"] != b["n_changed_fields"] for a, b in zip(nearest, provenance))
            for actual, row in zip(nearest, provenance):
                row["synthetic_nearest_training_positive_distance"] = actual["min_changed_fields"]
            artificial_counts.append(_export(artificial / f"train_artificial_{variant}.jsonl", generated,
                                             train, lines, range(len(train)), synthetic=True, seed=ARTIFICIAL_SEED))
            _save_csv(metadata / f"synthetic_provenance_{variant}_seed{ARTIFICIAL_SEED}.csv", provenance)
            _save_json(metadata / f"synthetic_diagnostics_{variant}_seed{ARTIFICIAL_SEED}.json", diagnostics)
        _save_csv(metadata / "train_negative_matching.csv", analysis["train_negative"])
        _save_csv(metadata / "holdout_strata.csv", analysis["holdout_negative"])
        manifest = {
            "input_sha256": REFERENCE_HASHES, "baseline_stages": stages,
            "baseline_counts": baseline_counts, "baseline_reused_not_included": True,
            "random_drop_seeds": list(RANDOM_DROP_SEEDS), "artificial_seed": ARTIFICIAL_SEED,
            "leave_one_perturbation_out": single_counts, "artificial_perturbation": artificial_counts,
            "neighbor_summary": analysis["summary"], "holdout_rows": len(holdout),
            "holdout_sha256": sha256(paths["holdout"]), "holdout_byte_identical": True,
            "models_trained": False,
        }
        _save_json(metadata / "manifest.json", manifest)
        _check_references(repo)
        staged.rename(output)
    print("Verified all eight training files and both unchanged holdouts against the study hashes.", flush=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="MOFinder checkout (default: current directory)")
    parser.add_argument("--output", type=Path, required=True, help="New directory for the two dataset folders and metadata")
    args = parser.parse_args(argv)
    build(args.repo, args.output)


if __name__ == "__main__":
    main()
