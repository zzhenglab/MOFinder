from __future__ import annotations

import argparse
import csv
import itertools
from pathlib import Path
from typing import Any, Dict, Iterable

from mofinder.training.records import INPUT_FIELDS


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[3]
    / "results/million_conditions/millioncombos_1M_conditions.csv"
)

FIELDS = list(INPUT_FIELDS)

METALS = [
    "Zn(NO3)2·6H2O", "ZrOCl2·8H2O", "Cu(NO3)2·3H2O",
    "Co(NO3)2·6H2O", "Cd(NO3)2·4H2O", "Ni(NO3)2·6H2O",
    "Al(NO3)3·9H2O", "Sc(NO3)3·6H2O", "HfCl4", "FeCl3·6H2O",
]

LINKERS = [
    "terephthalic acid",
    "benzene-1,3,5-tricarboxylic acid",
    "2-methylimidazole",
    "2-aminoterephthalic acid",
    "2,5-dihydroxyterephthalic acid",
    "biphenyl-4,4'-dicarboxylic acid",
    "2-chlorobenzene-1,4-dicarboxylic acid",
    "2-fluorobenzene-1,4-dicarboxylic acid",
    "2,5-thiophenedicarboxylic acid",
    "fumaric acid",
    "2,6-naphthalenedicarboxylic acid",
    "imidazole-4,5-dicarboxylic acid",
    "isophthalic acid",
    "tetrakis(4-carboxyphenyl)porphyrin",
    "isonicotinic acid",
    "4,4'-stilbenedicarboxylic acid",
    "1,2,4,5-benzenetetracarboxylic acid",
    "2,5-furandicarboxylic acid",
    "4,4'-bipyridine",
    "pyridine-3,5-dicarboxylic acid",
]

MODULATORS = [
    None, "acetic acid", "sodium hydroxide", "formic acid", "hydrochloric acid",
]

SOLVENTS = ["dimethylformamide", "water"]
FOCUSED_SOLVENTS = ["dimethylformamide", "water", "dimethylformamide and water"]
METAL_CONCS = [20.0, 50.0, 100.0, 150.0]
ML_RATIOS = [0.5, 0.75, 1.0, 1.5, 2.0]
TEMPS = [25.0, 100.0, 120.0, 160.0, 180.0]
TIMES = [12.0, 24.0, 36.0, 48.0, 72.0]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the 1,000,000-condition MOF combination CSV."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--encoding", default="utf-8-sig",
        help="CSV file encoding. utf-8-sig is friendlier for Excel.",
    )
    parser.add_argument("--limit", type=int, help="Write only the first N rows.")
    parser.add_argument(
        "--blank-pred-columns", action="store_true",
        help="Append empty pN, pP, pred columns.",
    )
    parser.add_argument(
        "--focused-solvents", action="store_true",
        help="Include dimethylformamide and water as a third solvent (1,500,000 rows).",
    )
    return parser.parse_args(argv)


def iter_condition_dicts(focused_solvents: bool = False) -> Iterable[Dict[str, Any]]:
    solvents = FOCUSED_SOLVENTS if focused_solvents else SOLVENTS
    for values in itertools.product(
        METALS, LINKERS, MODULATORS, solvents, METAL_CONCS, ML_RATIOS, TEMPS, TIMES,
    ):
        yield dict(zip(FIELDS, values))


def expected_total(focused_solvents: bool = False) -> int:
    solvents = FOCUSED_SOLVENTS if focused_solvents else SOLVENTS
    return (
        len(METALS) * len(LINKERS) * len(MODULATORS) * len(solvents)
        * len(METAL_CONCS) * len(ML_RATIOS) * len(TEMPS) * len(TIMES)
    )


def csv_value(value: Any) -> Any:
    return "" if value is None else value


def write_csv(
    path: Path, limit: int | None, blank_pred_columns: bool, encoding: str,
    focused_solvents: bool = False,
) -> int:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = FIELDS + (["pN", "pP", "pred"] if blank_pred_columns else [])
    conditions = iter_condition_dicts(focused_solvents)
    if limit is not None:
        conditions = itertools.islice(conditions, limit)
    written = 0
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for condition in conditions:
            row = {field: csv_value(condition[field]) for field in FIELDS}
            if blank_pred_columns:
                row.update({"pN": "", "pP": "", "pred": ""})
            writer.writerow(row)
            written += 1
    return written


def main(argv=None) -> int:
    args = parse_args(argv)
    written = write_csv(
        args.output, args.limit, args.blank_pred_columns, args.encoding,
        args.focused_solvents,
    )
    print(f"expected_total={expected_total(args.focused_solvents)}")
    print(f"written={written}")
    print(f"output={args.output}")
    print(f"encoding={args.encoding}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
