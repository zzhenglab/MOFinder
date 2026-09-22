"""Validate a small abstract-screening input set without model requests."""

import json
from pathlib import Path

from mofinder.literature.triage import validate_inputs, validation_summary

ROOT = Path(__file__).resolve().parent


def main():
    validated = validate_inputs(ROOT / "metadata.csv", ROOT / "ground_truth.csv")
    summary = validation_summary(validated)
    expected = json.loads((ROOT / "expected_validation.json").read_text())
    if summary != expected:
        raise AssertionError(f"Unexpected validation result: {summary}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
