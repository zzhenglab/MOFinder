"""Update the CSV and website question records from the 22-question JSON."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "benchmarks/mof_quest/22_questions.json"
SOURCE_URL = "https://github.com/zzhenglab/MOFinder/blob/main/benchmarks/mof_quest/22_questions.json"
CONDITION_FIELDS = (
    "metal_precursor", "organic_linker", "modulator", "solvent",
    "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h",
)
CSV_FIELDS = ("question", "reaction_id", "label", "difficulty", "doi", "conditions_json")


def load_questions() -> list[dict]:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if [row["question"] for row in questions] != [f"Q{i}" for i in range(1, 23)]:
        raise ValueError("Expected Q1 through Q22 in question order.")
    if len({row["reaction_id"] for row in questions}) != 22:
        raise ValueError("Reaction IDs must be unique.")
    if [row["label"] for row in questions] != ["P"] * 11 + ["N"] * 11:
        raise ValueError("Expected 11 positive and 11 negative questions.")
    for row in questions:
        if set(row["conditions"]) != set(CONDITION_FIELDS):
            raise ValueError(f"Unexpected conditions for {row['question']}.")
    return questions


def render_csv(questions: list[dict]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in questions:
        exported = {field: row[field] for field in CSV_FIELDS[:-1]}
        exported["conditions_json"] = json.dumps(row["conditions"], ensure_ascii=False)
        writer.writerow(exported)
    return stream.getvalue()


def render_array(name: str, questions: list[dict]) -> str:
    records = []
    for row in questions:
        reaction = {"id": row["reaction_id"], "doi": row["doi"], **row["conditions"]}
        if "article_trial_or_failure_notes" in row:
            reaction["article_trial_or_failure_notes"] = row["article_trial_or_failure_notes"]
        comment = f"  // {row['question']} | {row['label']} | {row['reaction_id']} | Stratum: {row['difficulty']}\n"
        record = json.dumps(reaction, indent=2, ensure_ascii=False)
        records.append(comment + "\n".join("  " + line for line in record.splitlines()))
    return f"const {name}: BenchmarkReaction[] = [\n" + ",\n\n".join(records) + "\n];"


def render_constants(current: str, questions: list[dict]) -> str:
    current = re.sub(
        r"// Question conditions and IDs follow [^\n]+",
        "// Question conditions and IDs follow benchmarks/mof_quest/22_questions.json in MOFinder.",
        current,
    )
    for name, label in (("successData", "P"), ("failData", "N")):
        replacement = render_array(name, [row for row in questions if row["label"] == label])
        pattern = rf"const {name}: BenchmarkReaction\[\] = \[.*?^\];"
        current, count = re.subn(pattern, lambda _: replacement, current, flags=re.S | re.M)
        if count != 1:
            raise ValueError(f"Expected one {name} array in constants.ts.")
    return current


def render_metadata(current: str) -> str:
    metadata = json.loads(current)
    metadata.pop("questions", None)
    metadata["question_source"] = SOURCE_URL
    return json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"


def render_manifest(current: str, question_csv: str) -> str:
    manifest = json.loads(current)
    manifest.setdefault("recorded_question_source", manifest["question_source"])
    manifest.setdefault("recorded_questions_sha256", manifest["files"]["human_questions.csv"]["sha256"])
    manifest["question_source"] = "benchmarks/mof_quest/22_questions.json"
    manifest["question_source_sha256"] = hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()
    manifest["files"]["human_questions.csv"]["sha256"] = hashlib.sha256(question_csv.encode("utf-8")).hexdigest()
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quest-dir", type=Path, help="MOF-Quest checkout containing constants.ts")
    parser.add_argument("--check", action="store_true", help="Report stale exports without writing files")
    args = parser.parse_args()
    questions = load_questions()
    question_csv = render_csv(questions)
    manifest = ROOT / "benchmarks/mof_quest/human_manifest.json"
    exports = {
        ROOT / "benchmarks/mof_quest/human_questions.csv": question_csv,
        manifest: render_manifest(manifest.read_text(encoding="utf-8"), question_csv),
    }
    if args.quest_dir:
        constants = args.quest_dir / "constants.ts"
        metadata = args.quest_dir / "metadata.json"
        exports[constants] = render_constants(constants.read_text(encoding="utf-8"), questions)
        exports[metadata] = render_metadata(metadata.read_text(encoding="utf-8"))
    stale = []
    for path, expected in exports.items():
        current = path.read_bytes() if path.exists() else None
        encoded = expected.encode("utf-8")
        if current != encoded:
            stale.append(path)
            if not args.check:
                path.write_bytes(encoded)
                print(f"Updated {path.name}")
    if args.check and stale:
        for path in stale:
            print(f"Update required: {path}")
        raise SystemExit(1)
    print(f"Checked {len(questions)} questions across {len(exports)} exports.")


if __name__ == "__main__":
    main()
