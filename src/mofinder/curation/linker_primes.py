"""Restore documented prime glyphs in publication-specific linker fields."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

FIELDS = tuple(f"linker_{i}{suffix}" for i in (1, 2, 3) for suffix in ("", "_abbr"))
PRIME_GLYPHS = frozenset("′″‴⁗")


def load_corrections(path):
    """Load exact DOI/name pairs and reject changes beyond prime restoration."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or document.get("fields") != list(FIELDS):
        raise ValueError("Unsupported linker prime correction schema")
    lookup = {}
    for entry in document["corrections"]:
        source, corrected = entry["source_name"], entry["corrected_name"]
        if len(source) != len(corrected) or source == corrected or any(
            old != new and (old != "?" or new not in PRIME_GLYPHS)
            for old, new in zip(source, corrected)
        ):
            raise ValueError(f"Correction is not a prime glyph restoration: {source!r}")
        for doi in entry["dois"]:
            key = (doi, source)
            if key in lookup and lookup[key] != corrected:
                raise ValueError(f"Conflicting linker correction for {doi}: {source!r}")
            lookup[key] = corrected
    return lookup


def correct_record(record, lookup):
    """Return a record with exact-match linker corrections and its change count."""
    result = dict(record)
    changed = 0
    for field in FIELDS:
        value = record.get(field)
        corrected = lookup.get((record.get("doi"), value)) if isinstance(value, str) else None
        if corrected is not None and corrected != value:
            result[field] = corrected
            changed += 1
    return result, changed


def correct_frame(frame, corrections_file):
    """Copy a table and restore supported linker fields without changing its index."""
    lookup = load_corrections(corrections_file)
    result = frame.copy()
    if "doi" not in result:
        return result
    for field in FIELDS:
        if field in result:
            result[field] = [
                lookup.get((doi, value), value) if isinstance(value, str) else value
                for doi, value in zip(result["doi"], result[field])
            ]
    return result


def correct_csv(input_file, output_file, corrections_file):
    """Write a separate corrected CSV; preserve every other value and row order."""
    source, target, lookup_path = map(Path, (input_file, output_file, corrections_file))
    if source.resolve() == target.resolve():
        raise ValueError("Corrected output must be separate from the source CSV")
    lookup = load_corrections(lookup_path)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if not fields or "doi" not in fields:
            raise ValueError("Input CSV must have a doi column")
        rows = list(reader)
    corrected_rows, changed_rows, changed_cells = [], 0, 0
    for row in rows:
        corrected, count = correct_record(row, lookup)
        corrected_rows.append(corrected)
        changed_rows += bool(count)
        changed_cells += count
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(corrected_rows)
    return {
        "rows": len(rows), "changed_rows": changed_rows, "changed_cells": changed_cells,
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "corrections_sha256": hashlib.sha256(lookup_path.read_bytes()).hexdigest(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--lookup", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(correct_csv(args.input_csv, args.output_csv, args.lookup), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
