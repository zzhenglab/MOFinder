"""Concurrent evaluation of P/N reaction holdout records.

Only system and user messages are sent to the model. Assistant messages supply
reference labels locally. Token-pair probabilities and classification metrics
follow the original reaction evaluation notebook.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union, Sequence

import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

def get_msg(record: Dict[str, Any], role: str) -> str:
    for m in record.get("messages", []):
        if m.get("role") == role:
            return m.get("content", "")
    return ""

def extract_pn_logprobs_from_choice(choice_obj):
    """
    Works with SDK objects:
      choice.logprobs.content -> list[ChatCompletionTokenLogprob]
      Each item has attributes: token, logprob, bytes, top_logprobs
    Returns: pred_token, pred_token_logprob, logprob_P, logprob_N, prob_P
    """
    lp = getattr(choice_obj, "logprobs", None)
    if not lp or not getattr(lp, "content", None):
        return None, None, None, None, None

    first_tok = lp.content[0]  # object with .token, .logprob, .top_logprobs
    pred_tok  = getattr(first_tok, "token", "")
    pred_lp   = getattr(first_tok, "logprob", None)
    alts      = getattr(first_tok, "top_logprobs", None) or []

    def is_P(tok: str) -> bool:
        return re.sub(r"\s+", "", tok).upper() == "P"
    def is_N(tok: str) -> bool:
        return re.sub(r"\s+", "", tok).upper() == "N"

    lp_P = pred_lp if is_P(pred_tok) else None
    lp_N = pred_lp if is_N(pred_tok) else None

    for alt in alts:
        a_tok = getattr(alt, "token", "")
        a_lp  = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        if is_P(a_tok):
            lp_P = a_lp
        elif is_N(a_tok):
            lp_N = a_lp

    prob_P = None
    if lp_P is not None and lp_N is not None:
        m = max(lp_P, lp_N)
        num = math.exp(lp_P - m)
        den = num + math.exp(lp_N - m)
        prob_P = num / den if den > 0 else None

    return pred_tok, pred_lp, lp_P, lp_N, prob_P

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def build_messages(record: Dict[str, Any]) -> Tuple[str, str, List[Dict[str, str]]]:
    system_text = get_msg(record, "system")
    user_text = get_msg(record, "user")
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]
    return system_text, user_text, messages

def gold_label_from_record(record: Dict[str, Any]) -> Optional[str]:
    g = get_msg(record, "assistant").strip().upper()
    return g if g in ("P","N") else None

def parse_pred_label(text: str) -> str:
    m = re.search(r"[PN]", (text or "").upper())
    return m.group(0) if m else ""

def running_metrics(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    y_true, y_pred = [], []
    for r in rows:
        if r.get("gold_label") in ("P","N") and r.get("pred_label") in ("P","N"):
            y_true.append(1 if r["gold_label"]=="P" else 0)
            y_pred.append(1 if r["pred_label"]=="P" else 0)
    if not y_true:
        return {"accuracy":0.0,"precision":0.0,"recall":0.0,"f1":0.0}
    acc = accuracy_score(y_true, y_pred)
    p,r,f1,_ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {"accuracy":float(acc),"precision":float(p),"recall":float(r),"f1":float(f1)}

def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

def extract_logprobs_for_label(choice_obj, chosen_label: str) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
    """
    chosen_label: 'P' or 'N'
    Returns: (logprob_P, logprob_N, chosen_is_argmax)
      - logprob_P and logprob_N come from the same token position,
        namely the first output token whose text equals chosen_label (ignoring whitespace).
        If no token matches, use the first P or N token.
    """
    lp = getattr(choice_obj, "logprobs", None)
    if not lp or not getattr(lp, "content", None):
        return None, None, None

    # Find the first token whose normalized text equals the chosen label
    target_item = None
    for tok in lp.content:
        t = getattr(tok, "token", "")
        norm = re.sub(r"\s+", "", t).upper()
        if norm in ("P","N"):
            if norm == chosen_label:
                target_item = tok
                break

    if target_item is None:
        # Fall back to the first P or N token when the chosen label is absent.
        for tok in lp.content:
            t = getattr(tok, "token", "")
            norm = re.sub(r"\s+", "", t).upper()
            if norm in ("P","N"):
                target_item = tok
                break

    if target_item is None:
        return None, None, None

    pred_tok = getattr(target_item, "token", "")
    pred_lp  = getattr(target_item, "logprob", None)
    alts     = getattr(target_item, "top_logprobs", None) or []

    # Initialize with predicted token's logprob
    lp_P = pred_lp if chosen_label == "P" and pred_lp is not None else None
    lp_N = pred_lp if chosen_label == "N" and pred_lp is not None else None

    # Read alternatives at the same position
    for alt in alts:
        a_tok = getattr(alt, "token", "")
        a_lp  = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        norm = re.sub(r"\s+", "", a_tok).upper()
        if norm == "P":
            lp_P = a_lp if lp_P is None else lp_P
        elif norm == "N":
            lp_N = a_lp if lp_N is None else lp_N

    # chosen_is_argmax
    chosen_is_argmax = None
    if lp_P is not None and lp_N is not None:
        if chosen_label == "P":
            chosen_is_argmax = lp_P >= lp_N
        else:
            chosen_is_argmax = lp_N >= lp_P

    return lp_P, lp_N, chosen_is_argmax

def prob_from_pair(lp_P: Optional[float], lp_N: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    if lp_P is None or lp_N is None:
        return None, None
    m = max(lp_P, lp_N)
    pP = math.exp(lp_P - m)
    pN = math.exp(lp_N - m)
    den = pP + pN
    if den <= 0:
        return None, None
    return pP/den, pN/den

CSV_FIELDS = [
    "example_index", "source_path", "system_text", "user_text", "gold_label",
    "model_id", "model_output", "pred_label", "logprob_P", "logprob_N",
    "prob_P", "prob_N", "chosen_is_argmax", "latency_s", "timestamp", "error",
]
REQUEST_PARAMETERS = {
    "temperature": 0, "top_p": 1, "max_tokens": 2,
    "logprobs": True, "top_logprobs": 5,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_settings(config_path: Union[str, Path]) -> dict:
    """Load configuration, resolving paths against its project root."""
    config_path = Path(config_path).expanduser().resolve()
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    project_root = (config_path.parent / settings.get("project_root", "..")).resolve()
    settings["project_root"] = project_root
    settings["config_path"] = config_path
    settings["holdout_paths"] = [
        (project_root / path).resolve() for path in settings["holdout_paths"]
    ]
    settings["output_dir"] = (project_root / settings["output_dir"]).resolve()
    if settings.get("training_path"):
        settings["training_path"] = (project_root / settings["training_path"]).resolve()
    for key in ("max_concurrency", "print_interval", "retries"):
        value = settings.get(key, {"max_concurrency": 100, "print_interval": 5, "retries": 6}[key])
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive integer.")
        settings[key] = value
    seed = settings.get("seed", 7)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer.")
    settings["seed"] = seed
    if not isinstance(settings.get("test_mode", False), bool):
        raise ValueError("test_mode must be a boolean.")
    models = settings.get("models", [])
    if not models:
        raise ValueError("At least one model configuration is required.")
    names = []
    for model in models:
        if not isinstance(model.get("model_id"), str) or not model["model_id"].strip():
            raise ValueError("Each model must have a nonempty model_id.")
        name = model.get("output_name", "")
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Each output_name must be a filename stem without directories.")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("Model output_name values must be distinct.")
    return settings


def validate_inputs(settings: dict) -> dict:
    """Inspect holdout messages and provenance without API calls or output writes."""
    files, counts = [], Counter()
    for path in settings["holdout_paths"]:
        path = Path(path)
        records = load_jsonl(path)
        if not records:
            raise ValueError(f"Holdout file is empty: {path}")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(f"Expected an object at record {index} in {path}.")
            for role in ("system", "user", "assistant"):
                matches = [m for m in record.get("messages", []) if m.get("role") == role]
                if len(matches) != 1 or not isinstance(matches[0].get("content"), str) or not matches[0]["content"].strip():
                    raise ValueError(f"Record {index} in {path} must contain one nonempty {role} message.")
            gold = gold_label_from_record(record)
            if gold is None:
                raise ValueError(f"Record {index} in {path} has a reference label outside P/N.")
            counts[gold] += 1
        files.append({"path": str(path), "records": len(records), "sha256": _sha256(path)})
    if not files:
        raise ValueError("No holdout files configured.")
    training = None
    if settings.get("training_path"):
        path = Path(settings["training_path"])
        training = {"path": str(path), "sha256": _sha256(path)}
    return {
        "holdout_files": files, "records": sum(counts.values()),
        "labels": dict(sorted(counts.items())), "training_provenance": training,
        "models": settings["models"], "request_parameters": {**REQUEST_PARAMETERS, "seed": settings["seed"]},
    }


def summarize_rows(rows: List[dict]) -> dict:
    """Report the original valid-label metrics alongside response coverage."""
    scored = [r for r in rows if r.get("gold_label") in ("P", "N") and r.get("pred_label") in ("P", "N")]
    correct = sum(r["gold_label"] == r["pred_label"] for r in scored)
    return {
        "records": len(rows), "scored_records": len(scored),
        "unscored_records": len(rows) - len(scored),
        "error_records": sum(bool(r.get("error")) for r in rows),
        "coverage": len(scored) / len(rows) if rows else 0.0,
        "correct_records": correct,
        "metrics": running_metrics(rows),
    }


def analyze_saved(csv_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> dict:
    """Compute metrics from a saved prediction CSV without model access."""
    csv_path = Path(csv_path)
    frame = pd.read_csv(csv_path, keep_default_na=False)
    required = {"gold_label", "pred_label", "model_id", "example_index"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Prediction CSV is missing columns: {sorted(required - set(frame.columns))}")
    if frame["example_index"].duplicated().any():
        raise ValueError("Prediction CSV contains duplicate example indices.")
    if frame["model_id"].nunique() > 1:
        raise ValueError("A holdout prediction CSV must contain only one model.")
    rows = frame.to_dict("records")
    result = {
        "prediction_csv": str(csv_path.resolve()), "sha256": _sha256(csv_path),
        "model_id": str(frame["model_id"].iloc[0]) if len(frame) else None,
        **summarize_rows(rows),
    }
    if output_path is not None:
        _write_json(Path(output_path), result)
    return result


def _previous_rows(csv_path: Path, items: List[dict], model_id: str) -> List[dict]:
    if not csv_path.exists():
        return []
    frame = pd.read_csv(csv_path, keep_default_na=False)
    if list(frame.columns) != CSV_FIELDS:
        raise ValueError("Saved prediction CSV has different or incomplete columns.")
    rows = frame.to_dict("records")
    by_index = {item["example_index"]: item for item in items}
    seen = set()
    for row in rows:
        raw_index = row["example_index"]
        try:
            index = int(raw_index)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("Saved predictions contain an invalid example index.") from error
        if str(raw_index) != str(index) or index not in by_index or index in seen:
            raise ValueError("Saved predictions contain duplicate or out-of-range indices.")
        seen.add(index)
        item = by_index[index]
        if row["model_id"] != model_id or any(row[key] != item[key] for key in ("gold_label", "system_text", "user_text")):
            raise ValueError("Saved predictions differ from the selected model or holdout records. Choose a new output name.")
        if row["pred_label"] not in ("", "P", "N") or (row["pred_label"] == "" and not row["error"]):
            raise ValueError("Saved predictions contain an invalid or incomplete result row.")
    return rows


async def evaluate_holdout(
    model_id: str,
    holdout_paths: Union[str, Path, Sequence[Union[str, Path]]],
    output_name: str,
    out_dir: Union[str, Path] = "out",
    max_concurrency: int = 50,
    print_interval: int = 5,
    test_mode: bool = False,
    retries: int = 6,
    seed: int = 7,
    *,
    client: Any = None,
) -> dict:
    """Evaluate holdout records with the notebook's request and scoring rules.

    Completed rows, including failed requests, are retained on resume. A sidecar
    records input hashes and model parameters so a changed run cannot silently
    reuse previous predictions. Supplying ``client`` supports local mock runs.
    """
    for name, value in (("max_concurrency", max_concurrency), ("print_interval", print_interval), ("retries", retries)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if not output_name or Path(output_name).name != output_name or output_name in {".", ".."}:
        raise ValueError("output_name must be a filename stem without directories.")
    paths = [holdout_paths] if isinstance(holdout_paths, (str, Path)) else list(holdout_paths)
    items, fingerprints = [], []
    for source in paths:
        path = Path(source)
        records = load_jsonl(path)
        fingerprints.append({"path": str(path.resolve()), "sha256": _sha256(path)})
        for record in records:
            gold = gold_label_from_record(record)
            if gold not in ("P", "N"):
                continue
            system_text, user_text, messages = build_messages(record)
            if not system_text or not user_text:
                raise ValueError(f"Missing system or user message in {path}.")
            items.append(dict(example_index=len(items), source_path=str(path), gold_label=gold,
                              system_text=system_text, user_text=user_text, messages=messages))
    if not items:
        raise ValueError("No labeled holdout examples found.")

    out_dir = Path(out_dir)
    csv_path = out_dir / f"{output_name}.csv"
    manifest_path = out_dir / f"{output_name}.manifest.json"
    signature = {"model_id": model_id, "holdout_files": fingerprints,
                 "request_parameters": {**REQUEST_PARAMETERS, "seed": seed}, "retries": retries}
    if csv_path.exists() and not manifest_path.exists():
        raise ValueError("Saved prediction CSV has no run manifest. Choose a new output name; existing predictions remain available for offline analysis.")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("signature") != signature:
            raise ValueError("Saved run inputs or request settings changed. Choose a new output name.")
    previous = _previous_rows(csv_path, items, model_id)
    seen = {int(row["example_index"]) for row in previous}
    pending = [item for item in items if item["example_index"] not in seen]
    if test_mode:
        pending = pending[:10]
    if not pending:
        print("No pending examples.")
        return {"csv_path": str(csv_path), "new_records": 0, **summarize_rows(previous)}

    owns_client = client is None
    if owns_client:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY before running evaluation.")
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, {"signature": signature, "total_records": len(items)})
    total = len(pending)
    print(f"Evaluating {total} example(s) with concurrency={max_concurrency}...")
    t0 = time.time()
    semaphore = asyncio.Semaphore(max_concurrency)
    completed = []

    async def call_model(messages: List[dict]) -> Tuple[str, Any]:
        for attempt in range(retries):
            try:
                response = await client.chat.completions.create(
                    model=model_id, messages=messages, **REQUEST_PARAMETERS, seed=seed,
                )
                choice = response.choices[0]
                return (choice.message.content or "").strip(), choice
            except Exception:
                await asyncio.sleep(min(60, 2**attempt))
                if attempt == retries - 1:
                    return "", None

    async def worker(item: dict) -> dict:
        async with semaphore:
            t_start = time.time()
            text, choice = await call_model(item["messages"])
            latency = time.time() - t_start
            pred_label = parse_pred_label(text)
            lp_P = lp_N = prob_P = prob_N = chosen_is_argmax = None
            error = ""
            if choice and pred_label in ("P", "N"):
                lp_P, lp_N, chosen_is_argmax = extract_logprobs_for_label(choice, pred_label)
                prob_P, prob_N = prob_from_pair(lp_P, lp_N)
            else:
                error = "no_choice_or_bad_label"
            return dict(
                example_index=item["example_index"], source_path=item["source_path"],
                system_text=item["system_text"], user_text=item["user_text"],
                gold_label=item["gold_label"], model_id=model_id, model_output=text,
                pred_label=pred_label, logprob_P=lp_P, logprob_N=lp_N,
                prob_P=prob_P, prob_N=prob_N, chosen_is_argmax=chosen_is_argmax,
                latency_s=latency, timestamp=pd.Timestamp.utcnow().isoformat(), error=error,
            )

    tasks = [asyncio.create_task(worker(item)) for item in pending]
    try:
        # A single writer saves each completed request before the next result.
        needs_header = not csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8-sig" if needs_header else "utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            if needs_header:
                writer.writeheader()
            for future in asyncio.as_completed(tasks):
                row = await future
                writer.writerow(row)
                stream.flush()
                completed.append(row)
                processed = len(completed)
                if processed % print_interval == 0 or processed == total:
                    elapsed = time.time() - t0
                    eta = elapsed / processed * (total - processed)
                    metrics = running_metrics(completed)
                    print(f"[{processed}/{total}] elapsed {fmt_time(elapsed)}  eta {fmt_time(eta)}  "
                          f"acc {metrics['accuracy']:.3f}  f1 {metrics['f1']:.3f}  "
                          f"prec {metrics['precision']:.3f}  rec {metrics['recall']:.3f}")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if owns_client:
            await client.close()
    summary = analyze_saved(csv_path, out_dir / f"{output_name}.metrics.json")
    print("\nFinal metrics for this invocation:")
    for key, value in running_metrics(completed).items():
        print(f"{key}: {value:.4f}")
    return {"csv_path": str(csv_path), "new_records": len(completed),
            "invocation_metrics": running_metrics(completed), **summary}


async def sanity_test(settings: dict, *, client: Any = None) -> dict:
    """Run the notebook's optional first-record test, without writing results."""
    validate_inputs(settings)
    record = load_jsonl(settings["holdout_paths"][0])[0]
    _, _, messages = build_messages(record)
    model_id = settings.get("sanity_model_id", "gpt-4.1")
    owns_client = client is None
    if owns_client:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY before running evaluation.")
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
    started = time.time()
    try:
        response = await client.chat.completions.create(
            model=model_id, messages=messages, temperature=0,
            max_tokens=2, logprobs=True, top_logprobs=5,
        )
    finally:
        if owns_client:
            await client.close()
    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    token, token_lp, lp_P, lp_N, probability = extract_pn_logprobs_from_choice(choice)
    gold = gold_label_from_record(record)
    return {"model_id": model_id, "latency_s": time.time() - started,
            "gold_label": gold, "model_output": text,
            "pred_token": token, "pred_token_logprob": token_lp,
            "logprob_P": lp_P, "logprob_N": lp_N, "prob_P": probability,
            "correct": parse_pred_label(text) == gold}


async def run_config(settings: dict, *, client: Any = None, model_names: Optional[Sequence[str]] = None) -> List[dict]:
    """Evaluate selected model configurations, preserving their individual CSVs."""
    validate_inputs(settings)
    models = settings["models"]
    if model_names:
        known = {model["output_name"] for model in models}
        unknown = set(model_names) - known
        if unknown:
            raise ValueError(f"Unknown model output names: {sorted(unknown)}")
        models = [model for model in models if model["output_name"] in model_names]
    results = []
    for model in models:
        results.append(await evaluate_holdout(
            model_id=model["model_id"], holdout_paths=settings["holdout_paths"],
            output_name=model["output_name"], out_dir=settings["output_dir"],
            max_concurrency=settings["max_concurrency"], print_interval=settings["print_interval"],
            test_mode=settings.get("test_mode", False), retries=settings["retries"],
            seed=settings["seed"], client=client,
        ))
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "run", "sanity-test"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--config", default="configs/holdout_evaluation.json")
        if command == "run":
            subparser.add_argument("--model", action="append", help="Configured output_name; repeat for multiple models.")
            subparser.add_argument("--test-mode", action="store_true", help="Evaluate at most ten pending records per model.")
    analysis = commands.add_parser("analyze")
    analysis.add_argument("--csv", required=True)
    analysis.add_argument("--output", help="Optional path for a metrics JSON file.")
    args = parser.parse_args(argv)
    if args.command == "analyze":
        result = analyze_saved(args.csv, args.output)
    else:
        settings = load_settings(args.config)
        if args.command == "validate":
            result = validate_inputs(settings)
        elif args.command == "sanity-test":
            result = asyncio.run(sanity_test(settings))
        else:
            if args.test_mode:
                settings["test_mode"] = True
            result = asyncio.run(run_config(settings, model_names=args.model))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
