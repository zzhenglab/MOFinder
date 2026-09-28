"""Append audited process fields to an existing split without resplitting or relabeling.

Run with ``python -m mofinder.datasets.process_enrich --config CONFIG``.
The assignment table, not a fresh deduplication, selects the original source row.
"""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import shutil
import tempfile

from mofinder.display import display_paths
from mofinder.training.common import atomic_json, sha256
from mofinder.training.prepare import validate_dataset
from mofinder.training.records import (
    INPUT_FIELDS, PROCESS_FIELDS, input_fields, read_reaction_prompt, validate_process_fields,
)
from mofinder.training import records as training_records
from mofinder.training import prepare as training_prepare
from . import prepare as baseline_prepare
from .prepare import canonical_condition_key, forced_question_condition_key, normalize_doi


PATH_KEYS = ("positive_csv", "negative_csv", "baseline_train", "baseline_holdout",
             "split_assignments", "prompt_file", "output_dir")
SOURCE_FIELDS = (
    "split", "jsonl_row_number", "source_row_id", "source_table", "source_csv_row_index",
    "label", "doi_norm", "condition_key", "cluster_key", "vessel_type_raw", "stirring_raw",
    "vessel_type", "vessel_volume_mL", "stirring", "annotation_caveat",
)


def extend_input_description(prompt):
    """Change only the archived prompt's input list for the matched control."""
    original = "temperature_C, and time_h."
    expanded = "temperature_C, time_h, vessel_type, vessel_volume_mL, and stirring."
    if prompt.count(original) != 1:
        raise ValueError("Baseline system prompt must contain exactly one original input list")
    return prompt.replace(original, expanded, 1)


def load_settings(config):
    config = Path(config).resolve()
    settings = json.loads(config.read_text(encoding="utf-8"))
    root = (config.parent / settings.get("project_root", "..")).resolve()
    missing = set(PATH_KEYS) - set(settings)
    if missing:
        raise ValueError(f"Configuration lacks paths: {sorted(missing)}")
    result = {key: (root / settings[key]).resolve() for key in PATH_KEYS}
    result.update(project_root=root, config_file=config)
    return result


def _csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Missing or duplicate CSV headers: {path}")
        rows = list(reader)
    if not rows or any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Empty CSV or malformed row: {path}")
    return rows


def _process_values(row):
    missing = set(PROCESS_FIELDS) - set(row)
    if missing:
        raise ValueError(f"Enriched source lacks process fields: {sorted(missing)}")
    values = {field: row[field] for field in PROCESS_FIELDS}
    volume = values["vessel_volume_mL"]
    if volume not in ("Not reported", "Ambiguous"):
        try:
            values["vessel_volume_mL"] = float(volume)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Uncleaned vessel_volume_mL: {volume!r}") from exc
    validate_process_fields(values)
    return values


def _assignments(path, sources, positive_count):
    assignments = _csv_rows(path)
    required = {"source_row_id", "condition_key", "cluster_key", "is_success", "split", "doi_norm"}
    lookup, by_id = {}, {}
    for item in assignments:
        if not required <= set(item):
            raise ValueError(f"Split assignments lack columns: {sorted(required - set(item))}")
        if item["split"] not in ("train", "holdout") or item["is_success"] not in ("True", "False"):
            raise ValueError("Invalid split or is_success in assignment table")
        source_id = int(item["source_row_id"])
        if source_id in by_id or not 0 <= source_id < len(sources):
            raise ValueError(f"Duplicate or out-of-range source_row_id: {source_id}")
        label = "P" if item["is_success"] == "True" else "N"
        if label != ("P" if source_id < positive_count else "N"):
            raise ValueError(f"Source label / positive-row boundary mismatch: {source_id}")
        row = sources[source_id]
        if canonical_condition_key(row) != item["condition_key"]:
            raise ValueError(f"Source chemistry does not match archived assignment: {source_id}")
        if item["doi_norm"] and normalize_doi(row.get("doi") or row.get("DOI")) != item["doi_norm"]:
            raise ValueError(f"Source DOI does not match archived assignment: {source_id}")
        # Cross-split duplicates are also ambiguous, even when the labels agree.
        key = (item["condition_key"], label)
        if key in lookup:
            raise ValueError("Ambiguous condition-key / label mapping in split assignments")
        item = dict(item, label=label, source_id=source_id)
        lookup[key], by_id[source_id] = item, item
    train = [item for item in by_id.values() if item["split"] == "train"]
    holdout = [item for item in by_id.values() if item["split"] == "holdout"]
    for field in ("cluster_key", "condition_key"):
        if {item[field] for item in train} & {item[field] for item in holdout}:
            raise ValueError(f"Baseline split has overlapping {field}")
    return lookup, by_id


def _display_source(path, root):
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _read_baseline(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"Blank baseline JSONL line: {path}:{line_number}")
            row = json.loads(line)
            messages = row.get("messages", [])
            if [message.get("role") for message in messages] != ["system", "user", "assistant"]:
                raise ValueError(f"Expected exactly system/user/assistant: {path}:{line_number}")
            conditions = json.loads(messages[1]["content"])
            if not isinstance(conditions, dict) or set(conditions) != set(INPUT_FIELDS):
                raise ValueError(f"Baseline must have exactly eight input fields: {path}:{line_number}")
            if messages[2]["content"] not in ("P", "N"):
                raise ValueError(f"Invalid baseline label: {path}:{line_number}")
            yield row, conditions, messages[2]["content"]


def prepare_process_enrich(settings):
    """Write matched JSONL, source-row sidecars, and deterministic provenance."""
    output = Path(settings["output_dir"])
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    input_paths = {key: Path(settings[key]) for key in PATH_KEYS if key != "output_dir"}
    if "config_file" in settings:
        input_paths["config_file"] = Path(settings["config_file"])
    initial_hashes = {key: sha256(path) for key, path in input_paths.items()}
    positives, negatives = _csv_rows(settings["positive_csv"]), _csv_rows(settings["negative_csv"])
    sources = positives + negatives
    process = [_process_values(row) for row in sources]
    lookup, by_id = _assignments(settings["split_assignments"], sources, len(positives))
    prompt = read_reaction_prompt(settings["prompt_file"])
    for field in input_fields("process_enrich"):
        if field not in prompt:
            raise ValueError(f"Process prompt does not describe input field: {field}")
    root = Path(settings.get("project_root", Path.cwd()))
    manifest = {
        "schema_version": 1,
        "feature_profile": "process_enrich",
        "source_path_base": "project_root (absolute paths retained for external inputs)",
        "output_path_base": "manifest_directory",
        "description": "Matched control: archived eight inputs plus vessel_type, vessel_volume_mL, and stirring.",
        "input_fields": list(input_fields("process_enrich")),
        "vessel_volume_unit": "mL",
        "missing_value": "Not reported",
        "ambiguous_value": "Ambiguous",
        "source_csv_rows": {"P": len(positives), "N": len(negatives)},
        "sources": {key: {"path": _display_source(path, root), "sha256": initial_hashes[key]}
                    for key, path in input_paths.items()},
        "implementation": {
            name: {"path": _display_source(path, root), "sha256": sha256(path)}
            for name, path in {
                "process_enrich": Path(__file__).resolve(),
                "baseline_condition_normalization": Path(baseline_prepare.__file__).resolve(),
                "feature_profiles": Path(training_records.__file__).resolve(),
                "training_validation": Path(training_prepare.__file__).resolve(),
            }.items()
        },
        "datasets": {},
        "caveats": [
            "Negative process annotations may be inherited from successful source recipes; this control does not establish causal benefit.",
            "The archived chemistry-cluster split is retained; it is not a DOI-disjoint split.",
            "No experimental validation, model training, new split, deduplication, or rebalancing is performed.",
            "The 22-question benchmark has no curated process annotations and is not included here.",
        ],
    }
    seen = set()
    split_dois = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".process-enrich-", dir=output.parent) as temporary:
        staged = Path(temporary) / "processed_enrich"
        staged.mkdir()
        for split in ("train", "holdout"):
            labels = Counter()
            distributions = {field: defaultdict(Counter) for field in PROCESS_FIELDS}
            dois = set()
            destination = staged / f"{split}.jsonl"
            sidecar = staged / f"{split}_sources.csv"
            with destination.open("w", encoding="utf-8", newline="\n") as out, sidecar.open("w", encoding="utf-8", newline="") as side:
                writer = csv.DictWriter(side, fieldnames=SOURCE_FIELDS, lineterminator="\n")
                writer.writeheader()
                for index, (record, conditions, label) in enumerate(_read_baseline(settings[f"baseline_{split}"]), 1):
                    if prompt != extend_input_description(record["messages"][0]["content"]):
                        raise ValueError(f"Process system prompt must change only the input list: {split} row {index}")
                    key = (forced_question_condition_key(conditions), label)
                    if key not in lookup:
                        raise ValueError(f"No archived source mapping: {split} row {index}")
                    assignment = lookup[key]
                    source_id = assignment["source_id"]
                    if assignment["split"] != split or source_id in seen:
                        raise ValueError(f"Wrong split or reused source row: {split} row {index}")
                    seen.add(source_id)
                    source = sources[source_id]
                    enriched = dict(conditions)
                    enriched.update(process[source_id])
                    # Retain all record structure and original message metadata.
                    record["messages"][0]["content"] = prompt
                    record["messages"][1]["content"] = json.dumps(enriched, ensure_ascii=False, allow_nan=False)
                    out.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    labels[label] += 1
                    for field, value in process[source_id].items():
                        distributions[field][label][str(value)] += 1
                    if assignment["doi_norm"]:
                        dois.add(assignment["doi_norm"])
                    writer.writerow({
                        "split": split, "jsonl_row_number": index, "source_row_id": source_id,
                        "source_table": "positive" if label == "P" else "negative",
                        "source_csv_row_index": source_id if label == "P" else source_id - len(positives),
                        "label": label, "doi_norm": assignment["doi_norm"],
                        "condition_key": assignment["condition_key"], "cluster_key": assignment["cluster_key"],
                        "vessel_type_raw": source.get("vessel_type_raw", ""),
                        "stirring_raw": source.get("stirring_raw", ""),
                        **process[source_id],
                        "annotation_caveat": "May be inherited from successful source recipe" if label == "N" else "",
                    })
            metadata, _ = validate_dataset(destination, "process_enrich", prompt)
            if metadata["rows"] != sum(labels.values()):
                raise ValueError(f"Output row count mismatch: {split}")
            manifest["datasets"][split] = {
                "path": destination.name, **metadata,
                "source_rows": {"path": sidecar.name, "sha256": sha256(sidecar)},
                "process_distributions_by_label": {
                    field: {label: dict(sorted(counts.items())) for label, counts in by_label.items()}
                    for field, by_label in distributions.items()
                },
            }
            split_dois[split] = dois
        if seen != set(by_id):
            raise ValueError(f"Archived assignment rows not consumed: {len(set(by_id) - seen)}")
        if any(sha256(path) != initial_hashes[key] for key, path in input_paths.items()):
            raise ValueError("A source file changed during preparation")
        shutil.copyfile(settings["prompt_file"], staged / "reaction_prediction_process_enrich.txt")
        atomic_json(staged / "class_map.json", {"P": "success", "N": "failure"})
        manifest["class_map"] = {"path": "class_map.json", "sha256": sha256(staged / "class_map.json")}
        manifest["reaction_prediction"] = {"path": "reaction_prediction_process_enrich.txt", "sha256": sha256(staged / "reaction_prediction_process_enrich.txt")}
        manifest["validation"] = {
            "mapped_source_rows": len(seen), "all_assignments_consumed_once": True,
            "baseline_order_labels_and_eight_inputs_preserved": True,
            "system_prompt_only_expands_original_input_list": True,
            "source_chemistry_and_doi_match_assignments": True,
            "condition_and_cluster_overlap": 0,
            "shared_train_holdout_dois": len(split_dois["train"] & split_dois["holdout"]),
        }
        atomic_json(staged / "manifest.json", manifest)
        (staged / "README.md").write_text(
            "# Process-enriched matched control\n\n"
            "`train.jsonl` and `holdout.jsonl` preserve the standard split, record order, labels, and eight original inputs. "
            "They add only `vessel_type`, `vessel_volume_mL` (capacity in mL), and `stirring`. "
            "The system prompt is identical to each original prompt except for these three names appended to its input list. "
            "Missing values are `Not reported`; unresolved capacities are `Ambiguous`.\n\n"
            "The source CSVs retain all rows; these JSONL files retain the standard dataset's existing filtered cohort. "
            "The `*_sources.csv` sidecars map every JSONL row to its original source row and are never model input. "
            "`jsonl_row_number` is one-based; source indices are zero-based, with positives preceding negatives.\n\n"
            "Negative process annotations can be inherited from successful recipes. The existing split shares "
            f"{manifest['validation']['shared_train_holdout_dois']} DOIs across training and holdout. "
            "Use this dataset as a matched control; do not interpret it as causal process validation. "
            "No manual benchmark process details are invented and no model was trained.\n\n"
            "Reproduce with `python -m mofinder.datasets.process_enrich --config configs/dataset_preparation_process_enrich.json "
            "--output results/datasets/process_enrich` using a new output directory. "
            "See [training preparation](../../../docs/process_enrich_training.md) for the training bundle route.\n",
            encoding="utf-8",
        )
        staged.rename(output)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[3] / "configs/dataset_preparation_process_enrich.json")
    parser.add_argument("--output", type=Path, help="New output directory, resolved relative to the current working directory")
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.output is not None:
        settings["output_dir"] = args.output.resolve()
    manifest = prepare_process_enrich(settings)
    print(json.dumps(display_paths({"datasets": {name: {key: value for key, value in item.items()
                       if key != "process_distributions_by_label"} for name, item in manifest["datasets"].items()},
                       "validation": manifest["validation"]}), indent=2))


if __name__ == "__main__":
    main()
