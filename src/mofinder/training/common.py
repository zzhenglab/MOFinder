"""Dependency-free input validation and result helpers."""
import gzip
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_jsonl(path, expected=None, manual=False):
    path = Path(path)
    before = path.stat()
    opener = gzip.open if path.suffix == ".gz" else open
    count = 0
    with opener(path, "rt", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if manual and "messages" not in row:
                label = str(row.get("label", "")).strip().upper()
            else:
                messages = row.get("messages", [])
                answers = [m.get("content", "").strip().upper() for m in messages
                           if m.get("role") == "assistant"]
                users = [m.get("content", "") for m in messages if m.get("role") == "user"]
                if not answers or not users or not isinstance(json.loads(users[-1]), dict):
                    raise ValueError(f"Invalid messages: {path}:{line_no}")
                label = answers[-1]
            if label not in ("P", "N"):
                raise ValueError(f"Invalid label: {path}:{line_no}")
            count += 1
    digest = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"Input still changing: {path}")
    if count == 0 or (expected is not None and count != expected):
        raise ValueError(f"Row count mismatch: {path}: {count} != {expected}")
    return {"rows": count, "sha256": digest, "bytes": after.st_size}


def binary_metrics(probabilities, labels):
    if len(probabilities) != len(labels) or not len(labels):
        raise ValueError("Nonempty equally sized predictions and labels required")
    tn = fp = fn = tp = 0
    for probability, label in zip(probabilities, labels):
        if not 0 <= float(probability) <= 1 or int(label) not in (0, 1):
            raise ValueError("Invalid prediction or label")
        pred = float(probability) >= 0.5
        tp += int(pred and label == 1)
        fp += int(pred and label == 0)
        fn += int(not pred and label == 1)
        tn += int(not pred and label == 0)
    return {"accuracy": (tp + tn) / len(labels),
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
            "total": len(labels), "correct": tp + tn,
            "confusion_matrix_NP": [[tn, fp], [fn, tp]]}


def export_predictions(path, rows, probabilities, labels, raw_scores, prompts,
                       experiment_id, step, split, source):
    """Write one prediction per input row, in the original order."""
    if not len(rows) or len({len(v) for v in (rows, probabilities, labels, raw_scores, prompts)}) != 1:
        raise ValueError("Prediction export must include every input row exactly once")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for index, (row, probability, label, score, prompt) in enumerate(
                    zip(rows, probabilities, labels, raw_scores, prompts), 1):
                probability, label, score = float(probability), int(label), float(score)
                if (not 0 <= probability <= 1 or not math.isfinite(score)
                        or label not in (0, 1) or label != int(row["labels"])):
                    raise ValueError(f"Invalid/misaligned prediction at row {index}")
                item = {"id": f"{index:04d}", "record_id": row["record_id"],
                        "messages": row["messages"], "rendered_prompt": prompt,
                        "gold": "P" if label else "N", "pred": "P" if probability >= .5 else "N",
                        "prob": probability, "raw_score": score,
                        "method": "gptoss20b_lora", "role": "PN",
                        "experiment_id": experiment_id, "step": step, "split": split,
                        "threshold": .5, "threshold_raw": 0.0,
                        "threshold_source": "fixed_0.5_no_calibration",
                        "source_file": source["path"], "source_sha256": source["sha256"],
                        "source_row_index": index - 1}
                f.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"rows": len(rows), "sha256": sha256(path), "bytes": path.stat().st_size}
