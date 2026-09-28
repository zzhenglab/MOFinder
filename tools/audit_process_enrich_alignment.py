"""Independently compare every enriched JSONL line with its archived baseline.

Run from any directory: python tools/audit_process_enrich_alignment.py
This audit uses the standard library and does not import the preparation code.
"""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from itertools import zip_longest
import json
from pathlib import Path


EXTRA_FIELDS = ("vessel_type", "vessel_volume_mL", "stirring")
ORIGINAL_INPUT_TAIL = "temperature_C, and time_h."
ENRICHED_INPUT_TAIL = "temperature_C, time_h, vessel_type, vessel_volume_mL, and stirring."


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_split(baseline, enriched):
    paths = {"baseline": Path(baseline), "enriched": Path(enriched)}
    hashes = {name: sha256(path) for name, path in paths.items()}
    counts, failures, examples = Counter(), Counter(), []
    labels = {name: Counter() for name in paths}
    prompts = {name: set() for name in paths}

    def fail(check, row):
        failures[check] += 1
        if len(examples) < 20:
            examples.append({"check": check, "row_number": row})

    with paths["baseline"].open(encoding="utf-8-sig") as left, paths["enriched"].open(encoding="utf-8-sig") as right:
        for index, (old_line, new_line) in enumerate(zip_longest(left, right), 1):
            for name, line in (("baseline", old_line), ("enriched", new_line)):
                counts[name] += line is not None
            if old_line is None or new_line is None:
                fail("row_count", index)
                continue
            counts["paired_rows"] += 1
            old, new = json.loads(old_line), json.loads(new_line)
            if any([m.get("role") for m in record.get("messages", [])] != ["system", "user", "assistant"]
                   for record in (old, new)):
                fail("message_structure", index)
                continue
            old_messages, new_messages = old["messages"], new["messages"]
            old_user, new_user = old_messages[1]["content"], new_messages[1]["content"]
            old_fields, new_fields = json.loads(old_user), json.loads(new_user)
            if len(old_fields) != 8 or list(new_fields) != list(old_fields) + list(EXTRA_FIELDS):
                fail("field_names_or_order", index)
            retained = {key: value for key, value in new_fields.items() if key not in EXTRA_FIELDS}
            if json.dumps(retained, ensure_ascii=False) != json.dumps(old_fields, ensure_ascii=False):
                fail("original_values_types_or_order", index)
            extra = {key: new_fields.get(key) for key in EXTRA_FIELDS}
            expected_user = old_user[:-1] + ", " + json.dumps(extra, ensure_ascii=False, allow_nan=False)[1:]
            if not old_user.endswith("}") or new_user != expected_user:
                fail("user_text_not_exact_append", index)
            old_prompt, new_prompt = old_messages[0]["content"], new_messages[0]["content"]
            expected_prompt = old_prompt.replace(ORIGINAL_INPUT_TAIL, ENRICHED_INPUT_TAIL, 1)
            if old_prompt.count(ORIGINAL_INPUT_TAIL) != 1 or new_prompt != expected_prompt:
                fail("system_prompt_beyond_input_list", index)
            restored = deepcopy(new)
            restored["messages"][0]["content"] = old_prompt
            restored["messages"][1]["content"] = old_user
            if json.dumps(restored, ensure_ascii=False) != json.dumps(old, ensure_ascii=False):
                fail("assistant_labels_or_other_metadata", index)
            for name, messages in (("baseline", old_messages), ("enriched", new_messages)):
                labels[name][messages[2]["content"]] += 1
                prompts[name].add(messages[0]["content"])
    if not counts["paired_rows"]:
        fail("empty_dataset", 0)
    for name, path in paths.items():
        if sha256(path) != hashes[name]:
            fail("file_changed_during_audit", 0)
    return {
        "baseline_rows": counts["baseline"], "enriched_rows": counts["enriched"],
        "rows_compared_in_file_order": counts["paired_rows"],
        "baseline_sha256": hashes["baseline"], "enriched_sha256": hashes["enriched"],
        "labels": {name: dict(sorted(values.items())) for name, values in labels.items()},
        "distinct_system_prompts": {name: len(values) for name, values in prompts.items()},
        "mismatches": dict(failures), "mismatch_examples": examples,
        "passed": not failures,
    }


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=root / "data/final_json")
    parser.add_argument("--enriched-dir", type=Path, default=root / "data/final_json/processed_enrich")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "comparison": "Every JSONL line compared directly at the same one-based row number, without sorting or matching by content.",
        "allowed_user_change": {"appended_fields_in_order": list(EXTRA_FIELDS)},
        "allowed_system_change": {"replace_once": ORIGINAL_INPUT_TAIL, "with": ENRICHED_INPUT_TAIL},
        "checks": ["same row count and sequence", "eight original values and JSON types unchanged",
                   "original key order and user-message text preserved before appending fields",
                   "assistant labels and all other record/message metadata unchanged",
                   "system prompt byte-for-byte equal outside input-list expansion",
                   "source files unchanged during audit"],
        "splits": {name: audit_split(args.baseline_dir / f"{name}.jsonl", args.enriched_dir / f"{name}.jsonl")
                   for name in ("train", "holdout")},
    }
    report["passed"] = all(item["passed"] for item in report["splits"].values())
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
