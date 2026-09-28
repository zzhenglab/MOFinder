#!/usr/bin/env python3
"""Package verified process-enriched JSONL with a standalone prompt comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from audit_process_enrich_alignment import audit_split

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/processed_data_json"


def build_package(directory: Path, baseline: Path, output: Path) -> dict:
    reports = {}
    for split in ("train", "holdout"):
        report = audit_split(baseline / f"{split}.jsonl", directory / f"{split}_process_enrich.jsonl")
        if not report["passed"]:
            raise ValueError(f"Baseline alignment failed for {split}: {report['mismatches']}")
        reports[split] = report

    example = None
    with (baseline / "train.jsonl").open(encoding="utf-8") as before, (directory / "train_process_enrich.jsonl").open(encoding="utf-8") as after:
        for index, (old_line, new_line) in enumerate(zip(before, after), 1):
            old, new = json.loads(old_line), json.loads(new_line)
            if list(new) != ["messages"]:
                raise ValueError("Expected messages-only records")
            old_input = json.loads(old["messages"][1]["content"])
            new_input = json.loads(new["messages"][1]["content"])
            if (new_input["vessel_type"] != "Not reported"
                    and isinstance(new_input["vessel_volume_mL"], (int, float))
                    and new_input["agitation"] == "Stirring reported"
                    and "\ufffd" not in json.dumps(new_input, ensure_ascii=False)):
                example = index, old, new, old_input, new_input
                break
    if example is None:
        raise ValueError("No complete process example found")
    index, old, new, old_input, new_input = example
    old_prompt = old["messages"][0]["content"]
    new_prompt = new["messages"][0]["content"]
    canonical = (REPO / "prompts/training/reaction_prediction_process_enrich.txt").read_text(encoding="utf-8")
    if new_prompt != canonical:
        raise ValueError("System prompt differs from the canonical process prompt")
    prompt_display = lambda text: "\n".join(line.rstrip() for line in text.splitlines())
    classes = json.loads((REPO / "data/processed_data/with_process_details/manifest.json").read_text(encoding="utf-8"))["category_consolidation"]["agitation_classes"]
    lines = [
        "# Process-enriched training and holdout", "",
        "This package contains `train_process_enrich.jsonl`, `holdout_process_enrich.jsonl`, and this README. "
        "The files use eleven inputs: the baseline eight reaction conditions plus vessel type, vessel capacity, and agitation.", "",
        "| File | Rows | P | N |", "|---|---:|---:|---:|",
    ]
    for split, report in reports.items():
        labels = report["labels"]["enriched"]
        lines.append(f"| `{split}_process_enrich.jsonl` | {report['enriched_rows']:,} | {labels['P']:,} | {labels['N']:,} |")
    lines += [
        "", "Each line contains a JSON object with `messages` in system, user, assistant order. "
        "The user-message content is a JSON object encoded as a string. The assistant content is `P` or `N`. "
        "No reaction ID or record ID is included.", "",
        "## System-prompt difference", "",
        "Only the input-field list is expanded. The chemistry task, output instructions, and all other "
        "system-prompt text and formatting remain unchanged in the JSONL files.", "",
        "```diff",
        "-    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, and time_h.",
        "+    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, time_h, vessel_type, vessel_volume_mL, and agitation.",
        "```", "", "Baseline system prompt:", "", "```text", prompt_display(old_prompt), "```", "",
        "Process-enriched system prompt:", "", "```text", prompt_display(new_prompt), "```", "",
        "Display blocks omit trailing whitespace; the JSONL files preserve the original formatting.", "",
        "## User-prompt difference", "",
        "The original eight values, JSON types, and key order are preserved. Three keys are appended: "
        "`vessel_type`, `vessel_volume_mL`, and `agitation`.", "",
        f"The following paired example comes from training row {index} (one-based), formatted for readability. "
        f"Its assistant label remains `{new['messages'][2]['content']}`.", "",
        "Baseline user content:", "", "```json", json.dumps(old_input, ensure_ascii=False, indent=2), "```", "",
        "Process-enriched user content:", "", "```json", json.dumps(new_input, ensure_ascii=False, indent=2), "```", "",
        "| Added field | Meaning |", "|---|---|",
        "| `vessel_type` | Cleaned vessel category; unavailable or selected rare categories use `Not reported`. |",
        "| `vessel_volume_mL` | Numeric vessel capacity in mL, or `Not reported` / `Ambiguous`; not inferred from solution volume. |",
        "| `agitation` | One of the nine categories below. |", "",
    ]
    lines += [f"- `{value}`" for value in classes]
    lines += [
        "", "`Stirred before main synthesis` means initial preparation before the main heating or aging step, "
        "with later conditions unspecified. `Stirred before static synthesis` requires an explicitly static subsequent stage. "
        "The same distinction applies to sonication. `Stirring reported` does not establish stirring throughout the reaction. "
        "Shaking, vortexing, rotation, mixing, and homogenization are grouped separately from stirring.", "",
        "## Verification and comparison", "",
        "Every row was compared with the corresponding baseline row in file order. Row counts, order, "
        "labels, and all eight original input values and types match. The system prompt differs only by its "
        "input-field list. No new split, filtering, or rebalancing was performed. Use these files as a matched "
        "representation control with the same training settings as the baseline.", "",
        "Negative process descriptions may be inherited from successful source protocols; they are not "
        "independently observed failed-trial process measurements. The existing split is not DOI-disjoint. "
        "No improvement in predictive performance is claimed by this dataset release.", "",
        "SHA-256 hashes of the uncompressed JSONL files:", "", "```text",
    ]
    for split, report in reports.items():
        lines.append(f"{report['enriched_sha256']}  {split}_process_enrich.jsonl")
    lines += [
        "```", "",
        "[Dataset and figures](https://github.com/zzhenglab/MOFinder/tree/main/data/processed_data_json/processed_enrich) | "
        "[Baseline dataset](https://github.com/zzhenglab/MOFinder/tree/main/data/processed_data_json) | "
        "[System prompt](https://github.com/zzhenglab/MOFinder/blob/main/prompts/training/reaction_prediction_process_enrich.txt)", "",
        "To reproduce this ZIP from the repository root:", "", "```bash", "python tools/package_process_enrich.py", "```", "",
    ]
    readme = ("\n".join(lines)).encode("utf-8")
    (directory / "README_training_package.md").write_bytes(readme)
    payloads = {f"{split}_process_enrich.jsonl": (directory / f"{split}_process_enrich.jsonl").read_bytes()
                for split in reports}
    for split, report in reports.items():
        if hashlib.sha256(payloads[f"{split}_process_enrich.jsonl"]).hexdigest() != report["enriched_sha256"]:
            raise ValueError("Dataset changed while packaging")
    for name, data in payloads.items():
        for number, line in enumerate(data.splitlines(), 1):
            record = json.loads(line)
            if list(record) != ["messages"] or [m["role"] for m in record["messages"]] != ["system", "user", "assistant"]:
                raise ValueError(f"Unexpected record envelope: {name}:{number}")
    payloads["README.md"] = readme
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payloads.items():
            item = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data, compresslevel=9)
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(payloads):
            raise ValueError("ZIP integrity check failed")
        for name, data in payloads.items():
            if archive.read(name) != data:
                raise ValueError(f"ZIP entry differs from source: {name}")
    temporary.replace(output)
    return {"zip": str(output), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "files": list(payloads), "example_train_row": index,
            "rows": {split: value["enriched_rows"] for split, value in reports.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DATA / "processed_enrich")
    parser.add_argument("--baseline", type=Path, default=DATA)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.directory / "process_enrich_train_holdout.zip"
    print(json.dumps(build_package(args.directory, args.baseline, output), indent=2))


if __name__ == "__main__":
    main()
