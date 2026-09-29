"""Prepare the matched eight-condition-plus-stirring JSONL control and ZIP."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from itertools import zip_longest
import json
from pathlib import Path
import tempfile
import zipfile

from mofinder.curation import agitation_source_reviews, process_stirring, stirring_presence
from mofinder.curation.stirring_presence import classify_stirring, STIRRING_VALUES
from mofinder.training.common import sha256
from mofinder.training.records import INPUT_FIELDS, PROCESS_FIELDS, read_reaction_prompt
from .process_enrich import _csv_rows, _assignments, _read_baseline, extend_input_description
from .prepare import forced_question_condition_key

FIELDS = INPUT_FIELDS + ("stirring",)
PATH_KEYS = ("positive_csv", "negative_csv", "baseline_train", "baseline_holdout",
             "enriched_dir", "split_assignments", "prompt_file", "output_dir")
STIRRING_DESCRIPTION = (
    "    The stirring field is 'yes' when stirring is reported, including preparation-stage stirring "
    "unless a subsequent static synthesis is explicitly stated; 'no' when synthesis is explicitly "
    "static or unstirred, including stirring only before static synthesis; or 'not reported' when "
    "the stirring state is unspecified or ambiguous. Sonication, shaking, rotation, or mixing alone "
    "do not establish stirring. A 'yes' value does not imply continuous stirring throughout synthesis.\n"
)


def extend_prompt(prompt):
    original = "temperature_C, and time_h."
    insertion = "    Based on these inputs,"
    if prompt.count(original) != 1 or prompt.count(insertion) != 1:
        raise ValueError("Expected the original eight-field system prompt")
    return prompt.replace(original, "temperature_C, time_h, and stirring.", 1).replace(
        insertion, STIRRING_DESCRIPTION + insertion, 1)


def load_settings(config):
    config = Path(config).resolve()
    settings = json.loads(config.read_text(encoding="utf-8"))
    root = (config.parent / settings.get("project_root", "..")).resolve()
    result = {key: (root / settings[key]).resolve() for key in PATH_KEYS}
    result.update(project_root=root, config_file=config)
    return result


def _typed_equal(first, second):
    return json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)


def _readme(manifest):
    lines = ["# Nine-field process-enriched dataset", "",
             "The original eight reaction inputs plus `stirring`. The existing split, row order, "
             "P/N labels, and all eight original values are preserved.", "",
             "| File | P | N | Total |", "|---|---:|---:|---:|"]
    for item in manifest["datasets"].values():
        lines.append(f"| [{item['path']}]({item['path']}) | {item['labels']['P']:,} | "
                     f"{item['labels']['N']:,} | {item['rows']:,} |")
    lines += ["", "- `yes`: stirring is reported, including preparation stirring when a later static stage is not stated.",
              "- `no`: synthesis is explicitly static or unstirred, including stirring only before static synthesis.",
              "- `not reported`: stirring is unspecified or ambiguous; sonication, shaking, rotation, or mixing alone is insufficient.",
              "", "The [nine-field system prompt](../../../prompts/training/reaction_prediction_process_enrich_9field.txt) "
              "lists the nine inputs and defines these values. A `yes` value does not imply continuous reaction-stage stirring.",
              "", "[Download training, holdout, and prompt](process_enrich_9field_train_holdout.zip).", "",
              "Regenerate from the existing eleven-field files, source mappings, and processed CSVs:", "", "```bash",
              "python -m mofinder.datasets.process_enrich_9field --config configs/dataset_preparation_process_enrich_9field.json --output results/datasets/process_enrich_9field",
              "```", ""]
    return "\n".join(lines)


def _package(directory, prompt):
    names = [f"{split}_process_enrich_9field.jsonl" for split in ("train", "holdout")]
    payloads = {name: (directory / name).read_bytes() for name in names}
    prompt_name = "reaction_prediction_process_enrich_9field.txt"
    readme = (directory / "README.md").read_text(encoding="utf-8").replace(
        "../../../prompts/training/" + prompt_name, prompt_name)
    readme = readme.replace("[Download training, holdout, and prompt](process_enrich_9field_train_holdout.zip).\n\n", "")
    payloads.update({"README.md": readme.encode("utf-8"), prompt_name: prompt.encode("utf-8")})
    path = directory / "process_enrich_9field_train_holdout.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or any(archive.read(name) != value for name, value in payloads.items()):
            raise ValueError("Package differs from the verified outputs")
    return {"path": path.name, "sha256": sha256(path), "members": list(payloads)}


def prepare(settings, review_csv=None):
    output = Path(settings["output_dir"])
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    root = settings["project_root"]
    inputs = {key: Path(settings[key]) for key in PATH_KEYS if key not in ("output_dir", "enriched_dir")}
    inputs["config"] = Path(settings["config_file"])
    for split in ("train", "holdout"):
        inputs[f"enriched_{split}"] = settings["enriched_dir"] / f"{split}_process_enrich.jsonl"
        inputs[f"sources_{split}"] = settings["enriched_dir"] / f"{split}_sources.csv"
    hashes = {key: sha256(path) for key, path in inputs.items()}
    positives, negatives = _csv_rows(inputs["positive_csv"]), _csv_rows(inputs["negative_csv"])
    sources = positives + negatives
    decisions = [classify_stirring(row.get("stirring"), row.get("doi", "")) for row in sources]
    lookup, by_id = _assignments(settings["split_assignments"], sources, len(positives))
    prompt = read_reaction_prompt(inputs["prompt_file"])
    def identity(path):
        path = Path(path)
        try:
            name = path.relative_to(root).as_posix()
        except ValueError:
            name = path.name
        return {"path": name, "sha256": sha256(path)}
    manifest = {
        "schema_version": 1, "input_fields": list(FIELDS), "stirring_values": list(STIRRING_VALUES),
        "classifier_version": stirring_presence.STIRRING_PRESENCE_VERSION,
        "sources": {key: identity(path) for key, path in inputs.items()},
        "implementation": {name: identity(path) for name, path in {
            "generator": __file__, "classifier": stirring_presence.__file__,
            "agitation_parser": process_stirring.__file__, "source_reviews": agitation_source_reviews.__file__,
        }.items()},
        "source_csv_rows": {"P": len(positives), "N": len(negatives)},
        "all_source_stirring_counts": {
            label: dict(Counter(item["stirring"] for item in selection))
            for label, selection in (("P", decisions[:len(positives)]), ("N", decisions[len(positives):]))},
        "datasets": {},
    }
    seen, review_rows = set(), []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".process-enrich-9field-", dir=output.parent) as temporary:
        staged = Path(temporary) / "dataset"
        staged.mkdir()
        for split in ("train", "holdout"):
            labels, distribution = Counter(), defaultdict(Counter)
            maps = _csv_rows(inputs[f"sources_{split}"])
            target = staged / f"{split}_process_enrich_9field.jsonl"
            with inputs[f"enriched_{split}"].open(encoding="utf-8") as old, target.open("w", encoding="utf-8", newline="\n") as out:
                rows = zip_longest(_read_baseline(inputs[f"baseline_{split}"]), old, maps)
                for index, triple in enumerate(rows, 1):
                    if any(item is None for item in triple):
                        raise ValueError(f"Mismatched baseline/enriched/source row counts: {split}")
                    (baseline, conditions, label), enriched_line, mapping = triple
                    enriched = json.loads(enriched_line)
                    messages = enriched.get("messages", [])
                    if list(enriched) != ["messages"] or [m.get("role") for m in messages] != ["system", "user", "assistant"]:
                        raise ValueError(f"Unexpected eleven-field record envelope: {split}:{index}")
                    old_input = json.loads(messages[1]["content"])
                    if list(old_input) != list(INPUT_FIELDS + PROCESS_FIELDS):
                        raise ValueError(f"Expected eleven original fields: {split}:{index}")
                    if not _typed_equal(conditions, {key: old_input[key] for key in INPUT_FIELDS}):
                        raise ValueError(f"Eight-field values/types/order differ: {split}:{index}")
                    expected = deepcopy(baseline)
                    expected["messages"][0]["content"] = extend_input_description(baseline["messages"][0]["content"])
                    expected["messages"][1]["content"] = messages[1]["content"]
                    if expected != enriched or prompt != extend_prompt(baseline["messages"][0]["content"]):
                        raise ValueError(f"Unexpected prompt/label/metadata change: {split}:{index}")
                    assignment = lookup[(forced_question_condition_key(conditions), label)]
                    source_id = assignment["source_id"]
                    source = sources[source_id]
                    decision = decisions[source_id]
                    if (mapping["split"] != split or int(mapping["jsonl_row_number"]) != index
                            or int(mapping["source_row_id"]) != source_id or mapping["label"] != label
                            or mapping["stirring_raw"] != source.get("stirring", "")
                            or mapping["agitation"] != old_input["agitation"]
                            or decision["agitation"] != old_input["agitation"]
                            or assignment["split"] != split or source_id in seen):
                        raise ValueError(f"Source mapping or agitation mismatch: {split}:{index}")
                    seen.add(source_id)
                    new = deepcopy(baseline)
                    new_input = dict(conditions, stirring=decision["stirring"])
                    new["messages"][0]["content"] = prompt
                    new["messages"][1]["content"] = json.dumps(new_input, ensure_ascii=False, allow_nan=False)
                    out.write(json.dumps(new, ensure_ascii=False, allow_nan=False) + "\n")
                    labels[label] += 1
                    distribution[label][decision["stirring"]] += 1
                    review_rows.append({"split": split, "jsonl_row_number": index, "source_row_id": source_id,
                                        "label": label, "doi": source.get("doi", ""),
                                        "stirring_raw": source.get("stirring", ""), **decision})
            manifest["datasets"][split] = {
                "path": target.name, "rows": sum(labels.values()), "labels": dict(labels),
                "sha256": sha256(target), "size_bytes": target.stat().st_size,
                "stirring_counts_by_label": {label: {state: distribution[label][state] for state in STIRRING_VALUES}
                                             for label in ("P", "N")},
                "rows_dropped": {"P": 0, "N": 0},
            }
        if seen != set(by_id):
            raise ValueError("Not all baseline source assignments were consumed exactly once")
        if any(sha256(path) != hashes[key] for key, path in inputs.items()):
            raise ValueError("An input changed during preparation")
        manifest["validation"] = {"mapped_source_rows": len(seen), "all_assignments_consumed_once": True,
                                  "original_eight_values_types_order_and_labels_preserved": True,
                                  "eleven_field_source_alignment_verified": True,
                                  "system_prompt_lists_nine_fields_and_defines_stirring": True}
        (staged / "README.md").write_bytes(_readme(manifest).encode("utf-8"))
        manifest["package"] = _package(staged, prompt)
        (staged / "manifest.json").write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        staged.rename(output)
    if review_csv is not None:
        review_csv = Path(review_csv)
        review_csv.parent.mkdir(parents=True, exist_ok=True)
        with review_csv.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=list(review_rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(review_rows)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[3] / "configs/dataset_preparation_process_enrich_9field.json")
    parser.add_argument("--output", type=Path, help="New output directory")
    parser.add_argument("--review-csv", type=Path, help="Optional local row-level classification review")
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.output is not None:
        settings["output_dir"] = args.output.resolve()
    result = prepare(settings, args.review_csv)
    print(json.dumps({"datasets": result["datasets"], "validation": result["validation"]}, indent=2))


if __name__ == "__main__":
    main()
