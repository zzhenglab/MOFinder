"""Prepare one train/holdout pair for transfer to a GPU workstation or cluster."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile

from mofinder.display import display_paths
from .common import atomic_json, inspect_jsonl, read_json, sha256
from .records import INPUT_FIELDS, REACTION_PROMPT_FILE, read_message_rows, read_reaction_prompt


def _validate_recipe(recipe):
    if recipe.get("prompt_style") != "reaction_prediction":
        raise ValueError("Set recipe.prompt_style to reaction_prediction to use the full instructions")
    if type(recipe.get("max_length")) is not int or recipe["max_length"] < 1:
        raise ValueError("recipe.max_length must be a positive integer")


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
    _validate_recipe(settings["recipe"])
    prompt = Path(prompt) if prompt is not None else REACTION_PROMPT_FILE
    reaction_prompt = read_reaction_prompt(prompt)
    if settings["protocol"]["threshold"] != 0.5:
        raise ValueError("The P/N classifier uses a fixed probability threshold of 0.5")
    if read_json(class_map) != {"P": "success", "N": "failure"}:
        raise ValueError("Expected class map P=success and N=failure")
    datasets = {}
    for name, path in (("train", train), ("holdout", holdout)):
        metadata, _ = validate_dataset(path)
        datasets[name] = {"path": f"data/{name}.jsonl", **metadata}
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
                {"role": "system", "content": reaction_prompt},
                {"role": "user", "content": json.dumps(item["conditions"], ensure_ascii=False)},
                {"role": "assistant", "content": item["label"]},
            ],
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".training-", dir=output.parent) as temporary:
        staged = Path(temporary) / "bundle"
        (staged / "data").mkdir(parents=True)
        (staged / "prompts").mkdir()
        shutil.copyfile(prompt, staged / "prompts/reaction_prediction.txt")
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
            "schema_version": 2,
            "model_name": settings["model_name"],
            "model_directory": settings.get("model_directory"),
            "datasets": datasets,
            "class_map": {"path": "data/class_map.json", "sha256": sha256(staged / "data/class_map.json")},
            "question_panel_sha256": sha256(questions),
            "configuration_sha256": sha256(config),
            "reaction_prediction": {"path": "prompts/reaction_prediction.txt", "sha256": sha256(staged / "prompts/reaction_prediction.txt")},
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
    if manifest.get("schema_version") != 2 or "reaction_prediction" not in manifest:
        raise ValueError("Rebuild this bundle with tools/training/prepare_hpc.py to use the reaction prediction prompt")
    _validate_recipe(manifest["recipe"])
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
    prompt = manifest["reaction_prediction"]
    path = (bundle / prompt["path"]).resolve()
    if not path.is_relative_to(bundle) or sha256(path) != prompt["sha256"]:
        raise ValueError("Changed reaction prediction prompt")
    read_reaction_prompt(path)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--train", type=Path, default=root / "data/final_json/train.jsonl")
    parser.add_argument("--holdout", type=Path, default=root / "data/final_json/holdout.jsonl")
    parser.add_argument("--questions", type=Path, default=root / "benchmarks/mof_quest/questions.json")
    parser.add_argument("--class-map", type=Path, default=root / "data/final_json/class_map.json")
    parser.add_argument("--config", type=Path, default=root / "configs/training_hpc.json")
    parser.add_argument("--prompt", type=Path, default=REACTION_PROMPT_FILE,
                        help="Full reaction-prediction instructions; conditions are appended separately")
    parser.add_argument("--output", type=Path, default=root / "results/local/hpc_training")
    parser.add_argument("--validate-bundle", type=Path)
    args = parser.parse_args(argv)
    if args.validate_bundle:
        manifest = validate_bundle(args.validate_bundle)
    else:
        manifest = prepare_bundle(args.train, args.holdout, args.questions, args.class_map, args.config, args.output, args.prompt)
    print(json.dumps(display_paths(manifest["datasets"]), indent=2))


if __name__ == "__main__":
    main()
