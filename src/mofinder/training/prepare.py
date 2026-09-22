"""Prepare one train/holdout pair for transfer to a GPU workstation or cluster."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile

from .common import atomic_json, inspect_jsonl, read_json, sha256
from .records import INPUT_FIELDS, read_message_rows


def validate_dataset(path):
    metadata = inspect_jsonl(path)
    rows, system_prompt = read_message_rows(path)
    for index, row in enumerate(rows, 1):
        if set(row["reaction"]) != set(INPUT_FIELDS):
            raise ValueError(f"Expected the eight reaction-condition fields: {path}:{index}")
    metadata["labels"] = dict(Counter("P" if row["labels"] else "N" for row in rows))
    return metadata, system_prompt


def prepare_bundle(train, holdout, questions, class_map, config, output, prompt=None):
    """Copy dataset bytes and record hashes without changing the existing split."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    settings = read_json(config)
    prompt = Path(prompt) if prompt is not None else Path(__file__).resolve().parents[3] / "prompts/training/gptoss_short.txt"
    if prompt.read_text(encoding="utf-8").count("{conditions}") != 1:
        raise ValueError("The short prompt must contain one {conditions} placeholder")
    if settings["protocol"]["threshold"] != 0.5:
        raise ValueError("The P/N classifier uses a fixed probability threshold of 0.5")
    if read_json(class_map) != {"P": "success", "N": "failure"}:
        raise ValueError("Expected class map P=success and N=failure")
    datasets = {}
    for name, path in (("train", train), ("holdout", holdout)):
        metadata, system_prompt = validate_dataset(path)
        datasets[name] = {"path": f"data/{name}.jsonl", **metadata}
        if name == "train":
            training_prompt = system_prompt
    panel = read_json(questions)
    if not isinstance(panel, list) or len(panel) != 22:
        raise ValueError("Expected a list of 22 benchmark questions")
    question_rows = []
    for item in panel:
        if item.get("label") not in {"P", "N"} or set(item.get("conditions", {})) != set(INPUT_FIELDS):
            raise ValueError(f"Invalid benchmark question: {item.get('question')}")
        question_rows.append({
            "record_id": item.get("reaction_id", item["question"]),
            "messages": [
                {"role": "system", "content": training_prompt},
                {"role": "user", "content": json.dumps(item["conditions"], ensure_ascii=False)},
                {"role": "assistant", "content": item["label"]},
            ],
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".training-", dir=output.parent) as temporary:
        staged = Path(temporary) / "bundle"
        (staged / "data").mkdir(parents=True)
        (staged / "prompts").mkdir()
        shutil.copyfile(prompt, staged / "prompts/gptoss_short.txt")
        for name, path in (("train", train), ("holdout", holdout)):
            destination = staged / datasets[name]["path"]
            shutil.copyfile(path, destination)
            if sha256(destination) != datasets[name]["sha256"]:
                raise ValueError(f"Dataset changed during copying: {path}")
        manual_path = staged / "data/questions.jsonl"
        manual_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in question_rows), encoding="utf-8")
        metadata, _ = validate_dataset(manual_path)
        datasets["manual22"] = {"path": "data/questions.jsonl", **metadata}
        shutil.copyfile(class_map, staged / "data/class_map.json")
        manifest = {
            "schema_version": 1,
            "model_name": settings["model_name"],
            "model_directory": settings.get("model_directory"),
            "datasets": datasets,
            "class_map": {"path": "data/class_map.json", "sha256": sha256(staged / "data/class_map.json")},
            "question_panel_sha256": sha256(questions),
            "configuration_sha256": sha256(config),
            "short_prompt": {"path": "prompts/gptoss_short.txt", "sha256": sha256(staged / "prompts/gptoss_short.txt")},
            "recipe": settings["recipe"],
            "protocol": settings["protocol"],
        }
        atomic_json(staged / "manifest.json", manifest)
        staged.rename(output)
    return manifest


def validate_bundle(bundle):
    """Check all data files against their recorded hashes and row counts."""
    bundle = Path(bundle).resolve()
    manifest = read_json(bundle / "manifest.json")
    for name, info in manifest["datasets"].items():
        path = (bundle / info["path"]).resolve()
        if not path.is_relative_to(bundle):
            raise ValueError(f"Dataset path is outside the bundle: {name}")
        observed, _ = validate_dataset(path)
        for key in ("sha256", "rows", "bytes", "labels"):
            if observed[key] != info[key]:
                raise ValueError(f"Changed {key} for {name}")
    class_map = manifest["class_map"]
    path = (bundle / class_map["path"]).resolve()
    if not path.is_relative_to(bundle) or sha256(path) != class_map["sha256"]:
        raise ValueError("Changed class map")
    if read_json(path) != {"P": "success", "N": "failure"}:
        raise ValueError("Expected class map P=success and N=failure")
    prompt = manifest["short_prompt"]
    path = (bundle / prompt["path"]).resolve()
    if not path.is_relative_to(bundle) or sha256(path) != prompt["sha256"]:
        raise ValueError("Changed short prompt")
    if path.read_text(encoding="utf-8").count("{conditions}") != 1:
        raise ValueError("The short prompt must contain one {conditions} placeholder")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--train", type=Path, default=root / "data/training/train.jsonl")
    parser.add_argument("--holdout", type=Path, default=root / "data/training/holdout.jsonl")
    parser.add_argument("--questions", type=Path, default=root / "benchmarks/mof_quest/questions.json")
    parser.add_argument("--class-map", type=Path, default=root / "data/splits/class_map.json")
    parser.add_argument("--config", type=Path, default=root / "configs/training_hpc.json")
    parser.add_argument("--prompt", type=Path, default=root / "prompts/training/gptoss_short.txt")
    parser.add_argument("--output", type=Path, default=root / "results/local/hpc_training")
    parser.add_argument("--validate-bundle", type=Path)
    args = parser.parse_args(argv)
    if args.validate_bundle:
        manifest = validate_bundle(args.validate_bundle)
    else:
        manifest = prepare_bundle(args.train, args.holdout, args.questions, args.class_map, args.config, args.output, args.prompt)
    print(json.dumps({name: info for name, info in manifest["datasets"].items()}, indent=2))


if __name__ == "__main__":
    main()
