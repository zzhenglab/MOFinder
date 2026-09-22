"""Export the six bibliographic fields used by abstract screening."""

import argparse
import hashlib
import json
from pathlib import Path

from mofinder.display import display_path
from mofinder.literature.triage import read_table, save_csv

FIELDS = ["DOI", "Article Title", "Source Title", "Author Keywords", "Keywords Plus", "Abstract"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sheet", default=None)
    args = parser.parse_args()
    headers, rows, sheets = read_table(args.source, args.sheet)
    missing = set(FIELDS) - set(headers)
    if missing:
        parser.error(f"Missing metadata columns: {sorted(missing)}")
    if args.destination.exists():
        parser.error(f"Destination already exists: {display_path(args.destination)}")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    save_csv(rows, args.destination, FIELDS)
    print(json.dumps({
        "source_filename": args.source.name,
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "source_sheet": args.sheet or sheets[0],
        "export_sha256": hashlib.sha256(args.destination.read_bytes()).hexdigest(),
        "rows": len(rows), "columns": FIELDS,
        "transformation": "Column selection only; source row order and cell text preserved.",
    }, indent=2))


if __name__ == "__main__":
    main()
