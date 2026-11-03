"""Build inference JSONL shards using the shared reaction prediction prompt."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

from mofinder.training.records import INPUT_FIELDS, REACTION_PROMPT_FILE, read_reaction_prompt


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_CSV = REPO_ROOT / "results/million_conditions/millioncombos_1M_conditions.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_CSV.parent / "inference_jsonl_5parts"
CONDITION_COLUMNS = list(INPUT_FIELDS)
NUMERIC_COLUMNS = {
    "metal_concentration_mM",
    "M_L_ratio",
    "temperature_C",
    "time_h",
}
DEFAULT_DROP_COLUMNS = ["pN", "pP", "pred"]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert reaction-condition CSV into sharded inference JSONL."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--prompt-file", type=Path, default=REACTION_PROMPT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--gold", default="")
    parser.add_argument("--prefix", default="part")
    parser.add_argument(
        "--drop-columns",
        nargs="*",
        default=DEFAULT_DROP_COLUMNS,
        help="Columns known to be previous predictions and excluded from user JSON.",
    )
    return parser.parse_args(argv)


def count_csv_rows(input_csv: Path) -> int:
    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is missing a header row: {input_csv}")
        return sum(1 for _ in reader)


def split_sizes(total_rows: int, splits: int) -> list[int]:
    if splits <= 0:
        raise ValueError("--splits must be positive")
    if total_rows < 0:
        raise ValueError("total_rows must be nonnegative")
    base, remainder = divmod(total_rows, splits)
    return [base + (1 if index < remainder else 0) for index in range(splits)]


def parse_cell(column: str, value: str | None) -> Any:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if column in NUMERIC_COLUMNS:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{column} must be finite, got {value!r}")
        return number
    return value


def condition_from_row(row: dict[str, str | None]) -> dict[str, Any]:
    return {column: parse_cell(column, row.get(column)) for column in CONDITION_COLUMNS}


def validate_header(fieldnames: Iterable[str] | None, drop_columns: Iterable[str]) -> None:
    if fieldnames is None:
        raise ValueError("CSV is missing a header row")
    fields = list(fieldnames)
    if len(fields) != len(set(fields)):
        raise ValueError("CSV contains duplicate column names")
    missing = [column for column in CONDITION_COLUMNS if column not in fields]
    if missing:
        raise ValueError(f"CSV missing required condition columns: {missing}")

    expected = set(CONDITION_COLUMNS) | set(drop_columns)
    unexpected = [column for column in fields if column not in expected]
    if unexpected:
        print(
            f"Warning: ignoring unexpected non-condition columns: {unexpected}",
            file=sys.stderr,
        )


def write_shards(
    input_csv: Path,
    output_dir: Path,
    sizes: list[int],
    prefix: str,
    system_prompt: str,
    gold: str,
    drop_columns: list[str],
) -> dict[str, Any]:
    if not sizes or any(type(size) is not int or size < 0 for size in sizes):
        raise ValueError("Shard sizes must be a nonempty list of nonnegative integers")
    total_rows = sum(sizes)
    id_width = max(4, len(str(total_rows)))
    files: list[dict[str, Any]] = []

    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames, drop_columns)
        output_dir.mkdir(parents=True, exist_ok=True)

        row_index = 0
        for part_index, part_size in enumerate(sizes, start=1):
            out_path = output_dir / f"{prefix}{part_index}_inference.jsonl"
            written = 0
            with out_path.open("w", encoding="utf-8", newline="\n") as output:
                while written < part_size:
                    row = next(reader, None)
                    if row is None:
                        raise RuntimeError("CSV had fewer rows than the pre-counted total")
                    row_index += 1
                    condition = condition_from_row(row)
                    record = {
                        "id": str(row_index).zfill(id_width),
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": json.dumps(condition, ensure_ascii=False, allow_nan=False),
                            },
                        ],
                        "gold": gold,
                    }
                    output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    written += 1

            files.append({"path": str(out_path), "rows": written})

        if next(reader, None) is not None:
            raise RuntimeError("CSV had more rows than the pre-counted total")

    return {"total_rows": row_index, "files": files}


def main(argv=None) -> int:
    args = parse_args(argv)
    input_csv = args.input_csv.resolve()
    prompt_file = args.prompt_file.resolve()
    output_dir = args.output_dir.resolve()

    system_prompt = read_reaction_prompt(prompt_file)
    total_rows = count_csv_rows(input_csv)
    sizes = split_sizes(total_rows, args.splits)
    result = write_shards(
        input_csv=input_csv,
        output_dir=output_dir,
        sizes=sizes,
        prefix=args.prefix,
        system_prompt=system_prompt,
        gold=args.gold,
        drop_columns=args.drop_columns,
    )

    summary = {
        "input_csv": str(input_csv),
        "prompt_file": str(prompt_file),
        "output_dir": str(output_dir),
        "splits": args.splits,
        "split_sizes": sizes,
        "condition_columns": CONDITION_COLUMNS,
        "dropped_columns": args.drop_columns,
        "gold": args.gold,
        **result,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {result['total_rows']} records into {len(result['files'])} shards.")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
