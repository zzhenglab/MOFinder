"""Exact eight-field nearest-positive analysis for fixed-split ablations.

Distances describe observed inputs, not a negative record's construction history.
Only training positives select training negatives for removal. Holdout strata are
also defined relative to those fixed training positives, without changing holdout.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from mofinder.training.records import INPUT_FIELDS as FIELDS


def load_jsonl(path):
    """Read model JSONL and reject blank lines or malformed model records."""
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"Blank JSONL line at {number}: {path}")
            row = json.loads(line)
            conditions_and_label(row)
            rows.append(row)
    if not rows:
        raise ValueError(f"Empty JSONL: {path}")
    return rows


def conditions_and_label(record):
    """Validate the unchanged baseline eight-field message schema."""
    if set(record) != {"messages"}:
        raise ValueError("Model records must contain only messages; no IDs.")
    messages = record["messages"]
    if len(messages) != 3 or [m.get("role") for m in messages] != ["system", "user", "assistant"]:
        raise ValueError("Expected system, user and assistant messages in that order.")
    if any(set(m) != {"role", "content"} or not isinstance(m["content"], str) for m in messages):
        raise ValueError("Each message must have exactly string role and content.")
    conditions = json.loads(messages[1]["content"])
    if not isinstance(conditions, dict) or set(conditions) != set(FIELDS):
        raise ValueError("User input must contain exactly the eight baseline fields.")
    for value in conditions.values():
        if value is not None and not isinstance(value, (str, int, float)):
            raise ValueError("Condition values must be scalar strings, numbers or null.")
        if isinstance(value, bool) or isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Boolean and nonfinite condition values are unsupported.")
    label = messages[2]["content"]
    if label not in {"P", "N"}:
        raise ValueError("Expected a P or N assistant label.")
    return conditions, label


def _doi(sources, row_number):
    if sources is None:
        return ""
    if isinstance(sources, (list, tuple)):
        item = sources[row_number - 1]
    else:
        item = sources.get(row_number, sources.get(str(row_number), ""))
    if isinstance(item, dict):
        item = item.get("doi", item.get("doi_norm", ""))
    return str(item or "").strip().lower()


def _encode(anchors, queries):
    """Factorize scalar JSON values; numerical 1 and 1.0 compare equally."""
    matrices = []
    maps = [dict() for _ in FIELDS]
    for collection in (anchors, queries):
        matrix = np.empty((len(collection), len(FIELDS)), dtype=np.int32)
        for i, (_, values) in enumerate(collection):
            for j, field in enumerate(FIELDS):
                value = values[field]
                # Separate numeric and textual values; no spelling normalization.
                key = ("null",) if value is None else ("number", value) if isinstance(value, (int, float)) else ("text", value)
                matrix[i, j] = maps[j].setdefault(key, len(maps[j]))
        matrices.append(matrix)
    return matrices


def minimum_distances(positive_records, negative_records, positive_sources=None, negative_sources=None, block_size=256):
    """Return exact Hamming distances and deterministic anchors.

    Collections contain ``(baseline_row_1based, conditions_dict)`` pairs. Choose
    same-DOI positives among minimum-distance ties where available, then the
    earliest baseline row. This tie-break changes neither distance nor removal.
    """
    if not positive_records:
        raise ValueError("At least one positive anchor is required.")
    anchors = sorted(positive_records, key=lambda item: item[0])
    anchor_matrix, query_matrix = _encode(anchors, negative_records)
    anchor_dois = [_doi(positive_sources, row) for row, _ in anchors]
    rows = []
    for start in range(0, len(negative_records), block_size):
        block = query_matrix[start:start + block_size]
        distances = np.zeros((len(block), len(anchors)), dtype=np.uint8)
        for j in range(len(FIELDS)):
            distances += block[:, j, None] != anchor_matrix[None, :, j]
        for offset, vector in enumerate(distances):
            query_index = start + offset
            row_number, values = negative_records[query_index]
            minimum = int(vector.min())
            tied = np.flatnonzero(vector == minimum)
            query_doi = _doi(negative_sources, row_number)
            same_doi = [int(i) for i in tied if query_doi and anchor_dois[int(i)] == query_doi]
            chosen = same_doi[0] if same_doi else int(tied[0])
            anchor_row, anchor_values = anchors[chosen]
            changed = [field for field in FIELDS if values[field] != anchor_values[field]]
            match_fields = set()
            if minimum == 1:
                for i in tied:
                    match_fields.update(field for field in FIELDS if values[field] != anchors[int(i)][1][field])
            assert len(changed) == minimum
            rows.append({
                "baseline_row_1based": row_number,
                "nearest_positive_row_1based": anchor_row,
                "min_changed_fields": minimum,
                "changed_fields": changed,
                "single_field_match_fields": [field for field in FIELDS if field in match_fields],
                "nearest_positive_ties": int(len(tied)),
                "same_doi_anchor": bool(query_doi and query_doi == anchor_dois[chosen]),
            })
    return rows


def count_summary(rows):
    counts = Counter(row["min_changed_fields"] for row in rows)
    return {
        "negative_rows": len(rows),
        "distance_0": counts[0],
        "distance_1": counts[1],
        "distance_2": counts[2],
        "distance_ge3": sum(n for distance, n in counts.items() if distance >= 3),
        "distance_counts": {str(k): v for k, v in sorted(counts.items())},
        "overlapping_single_field_counts": {
            field: sum(field in row["single_field_match_fields"] for row in rows)
            for field in FIELDS
        },
    }


def analyze_neighbors(train_records, holdout_records, train_sources=None, holdout_sources=None):
    """Analyze both N sets against training P only; holdout never selects removals."""
    groups = {}
    for name, records in (("train", train_records), ("holdout", holdout_records)):
        groups[name] = {"P": [], "N": []}
        for row_number, record in enumerate(records, 1):
            conditions, label = conditions_and_label(record)
            groups[name][label].append((row_number, conditions))
    train = minimum_distances(groups["train"]["P"], groups["train"]["N"], train_sources, train_sources)
    holdout = minimum_distances(groups["train"]["P"], groups["holdout"]["N"], train_sources, holdout_sources)
    if any(row["min_changed_fields"] == 0 for row in train + holdout):
        raise ValueError("An N input exactly duplicates a training P input.")
    return {
        "train_negative": train,
        "holdout_negative": holdout,
        "summary": {
            "comparison_anchor": "fixed baseline training positives",
            "definition": "minimum number of unequal model input fields; not a source modification count",
            "train": count_summary(train),
            "holdout": count_summary(holdout),
            "baseline_labels": {name: {label: len(items) for label, items in group.items()} for name, group in groups.items()},
        },
    }
