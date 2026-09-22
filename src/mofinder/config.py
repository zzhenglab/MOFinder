"""Load portable paths and settings for abstract screening."""

import json
import math
from pathlib import Path


def load_triage_config(config_file):
    """Resolve paths relative to project_root, itself relative to the JSON file."""
    config_file = Path(config_file).expanduser().resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    root = (config_file.parent / config.get("project_root", "..")).resolve()
    for key, default in [("input_file", None), ("ground_truth_file", None),
                         ("prompt_file", "prompts/abstract_triage.txt"),
                         ("output_root", "results/abstract_triage")]:
        value = config.get(key, default)
        if not value:
            raise ValueError(f"Missing configuration field: {key}")
        config[key] = (root / Path(value).expanduser()).resolve()
    config["project_root"] = root
    config["config_file"] = config_file
    allowed_efforts = {
        "gpt-4o": {None},
        "gpt-5": {"minimal", "low", "medium", "high"},
        "gpt-6-astra": {"low", "medium", "high", "xhigh", "max"},
    }
    models = config.get("models", [])
    if not models or len({m["name"] for m in models}) != len(models):
        raise ValueError("Provide at least one model and unique configuration names.")
    for model in models:
        if model["model"] not in allowed_efforts:
            raise ValueError(f"Unsupported model: {model['model']}")
        if model["reasoning_effort"] not in allowed_efforts[model["model"]]:
            raise ValueError(f"Unsupported model/effort configuration: {model}")
    for key in ["n_rounds", "max_concurrent", "save_every", "bootstraps", "max_output_tokens"]:
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    maximum = config.get("max_papers")
    if maximum is not None and (type(maximum) is not int or maximum < 1):
        raise ValueError("max_papers must be None or a positive integer.")
    if type(config.get("benchmark_only")) is not bool:
        raise ValueError("benchmark_only must be true or false.")
    timeout = config.get("request_timeout")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("request_timeout must be a positive finite number.")
    if type(config.get("statistics_seed")) is not int or config["statistics_seed"] < 0:
        raise ValueError("statistics_seed must be a nonnegative integer.")
    config.setdefault("input_sheet", None)
    return config
