"""Shared helpers for MOFinder step-6 evaluation scripts.

This module factors out the boilerplate that was duplicated across the original
`step 6 evaluation_reaction *.ipynb` notebooks: loading JSONL records, building
chat messages, calling the OpenAI API with retries, aligning token-level
logprobs to the chosen label, computing P/N or P/U probabilities, the async
evaluation engine with resumable CSV output, and (for the 20-question
challenge) the gpt-5 responses-API path.

The per-eval scripts (`run_pn_full.py`, `run_pu_full.py`, etc.) import from
here and only specify which model, holdout, and output CSV to use.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support


# ---------------------------------------------------------------------------
# OpenAI client wiring
# ---------------------------------------------------------------------------

def ensure_api_key() -> None:
    """Fail fast if OPENAI_API_KEY is not set in the environment.

    The original notebooks hard-coded a key in plaintext; that key has been
    removed and should be rotated. Set the key with:

        $env:OPENAI_API_KEY = "sk-..."   # PowerShell
        export OPENAI_API_KEY=sk-...     # bash
    """
    if not os.getenv("OPENAI_API_KEY"):
        sys.stderr.write(
            "ERROR: OPENAI_API_KEY is not set. Export it before running.\n"
        )
        raise SystemExit(2)


def get_async_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI()


def get_sync_client():
    from openai import OpenAI
    return OpenAI()


# ---------------------------------------------------------------------------
# JSONL / record helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def get_msg(record: Dict[str, Any], role: str) -> str:
    for m in record.get("messages", []):
        if m.get("role") == role:
            return m.get("content", "")
    return ""


def build_messages_from_record(
    record: Dict[str, Any],
) -> Tuple[str, str, List[Dict[str, str]]]:
    system_text = get_msg(record, "system")
    user_text = get_msg(record, "user")
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]
    return system_text, user_text, messages


def gold_label_from_record(
    record: Dict[str, Any],
    valid_labels: Sequence[str] = ("P", "N"),
) -> Optional[str]:
    g = get_msg(record, "assistant").strip().upper()
    return g if g in valid_labels else None


def _key_text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return "" if value is None else str(value)


def build_example_key(
    source_path: Any,
    example_index: Any,
    system_text: Any,
    user_text: Any,
    gold_label: Any,
) -> str:
    """Stable resume key for a specific source example and prompt content."""
    source = _key_text(source_path)
    try:
        source = str(Path(source).resolve())
    except (OSError, RuntimeError, ValueError):
        pass
    payload = {
        "source_path": source,
        "example_index": _key_text(example_index),
        "system_text": _key_text(system_text),
        "user_text": _key_text(user_text),
        "gold_label": _key_text(gold_label),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_example_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Populate missing example_key values for current and legacy result rows."""
    key_cols = ["source_path", "example_index", "system_text", "user_text", "gold_label"]
    if any(c not in df.columns for c in key_cols):
        return df
    if "example_key" not in df.columns:
        df["example_key"] = ""
    missing = df["example_key"].astype(str).str.strip().isin(["", "nan", "None"])
    if missing.any():
        df.loc[missing, "example_key"] = df.loc[missing].apply(
            lambda r: build_example_key(
                r["source_path"],
                r["example_index"],
                r["system_text"],
                r["user_text"],
                r["gold_label"],
            ),
            axis=1,
        )
    return df


# ---------------------------------------------------------------------------
# Label parsing and metrics
# ---------------------------------------------------------------------------

def parse_pred_label(text: str, valid_labels: Sequence[str] = ("P", "N")) -> str:
    first_token = re.split(r"\s+", (text or "").strip(), maxsplit=1)[0]
    core = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", first_token).upper()
    return core if core in [v.upper() for v in valid_labels] else ""


def running_metrics(
    rows: List[Dict[str, Any]],
    pos_label: str = "P",
    neg_label: str = "N",
) -> Dict[str, float]:
    y_true: List[int] = []
    y_pred: List[int] = []
    valid = (pos_label, neg_label)
    for r in rows:
        if r.get("gold_label") in valid and r.get("pred_label") in valid:
            y_true.append(1 if r["gold_label"] == pos_label else 0)
            y_pred.append(1 if r["pred_label"] == pos_label else 0)
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    return {
        "accuracy": float(acc),
        "precision": float(p),
        "recall": float(r),
        "f1": float(f1),
    }


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Logprob alignment (works for any 2-letter label set, e.g. {P,N} or {P,U})
# ---------------------------------------------------------------------------

def _norm_tok(t: str) -> str:
    return re.sub(r"\s+", "", t).upper()


def extract_logprobs_for_label_chat(
    choice_obj: Any,
    chosen_label: str,
    label_pair: Tuple[str, str] = ("P", "N"),
) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
    """Align token logprobs to the chosen label inside `choice.logprobs.content`.

    Returns `(logprob_pos, logprob_neg, chosen_is_argmax)` where pos = label_pair[0]
    and neg = label_pair[1]. Both numbers come from the SAME token position —
    the first generated token whose normalized text equals chosen_label.
    """
    pos_label, neg_label = label_pair
    lp = getattr(choice_obj, "logprobs", None)
    if not lp or not getattr(lp, "content", None):
        return None, None, None

    target_item = None
    for tok in lp.content:
        norm = _norm_tok(getattr(tok, "token", ""))
        if norm in label_pair and norm == chosen_label:
            target_item = tok
            break
    if target_item is None:
        for tok in lp.content:
            norm = _norm_tok(getattr(tok, "token", ""))
            if norm in label_pair:
                target_item = tok
                break
    if target_item is None:
        return None, None, None

    pred_lp = getattr(target_item, "logprob", None)
    alts = getattr(target_item, "top_logprobs", None) or []

    lp_pos = pred_lp if chosen_label == pos_label else None
    lp_neg = pred_lp if chosen_label == neg_label else None

    for alt in alts:
        a_lp = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        a_norm = _norm_tok(getattr(alt, "token", ""))
        if a_norm == pos_label and lp_pos is None:
            lp_pos = a_lp
        elif a_norm == neg_label and lp_neg is None:
            lp_neg = a_lp

    chosen_is_argmax: Optional[bool] = None
    if lp_pos is not None and lp_neg is not None:
        chosen_is_argmax = (lp_pos >= lp_neg) if chosen_label == pos_label else (lp_neg >= lp_pos)
    return lp_pos, lp_neg, chosen_is_argmax


def extract_logprobs_for_label_responses(
    output_text_obj: Any,
    chosen_label: str,
    label_pair: Tuple[str, str] = ("P", "N"),
) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
    """Same as the chat variant but reads from a Responses-API output_text logprobs list."""
    pos_label, neg_label = label_pair
    lp_seq = getattr(output_text_obj, "logprobs", None)
    if not lp_seq:
        return None, None, None

    target_item = None
    for tok in lp_seq:
        norm = _norm_tok(getattr(tok, "token", ""))
        if norm in label_pair and norm == chosen_label:
            target_item = tok
            break
    if target_item is None:
        for tok in lp_seq:
            norm = _norm_tok(getattr(tok, "token", ""))
            if norm in label_pair:
                target_item = tok
                break
    if target_item is None:
        return None, None, None

    pred_lp = getattr(target_item, "logprob", None)
    alts = getattr(target_item, "top_logprobs", None) or []

    lp_pos = pred_lp if chosen_label == pos_label else None
    lp_neg = pred_lp if chosen_label == neg_label else None

    for alt in alts:
        a_lp = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        a_norm = _norm_tok(getattr(alt, "token", ""))
        if a_norm == pos_label and lp_pos is None:
            lp_pos = a_lp
        elif a_norm == neg_label and lp_neg is None:
            lp_neg = a_lp

    chosen_is_argmax: Optional[bool] = None
    if lp_pos is not None and lp_neg is not None:
        chosen_is_argmax = (lp_pos >= lp_neg) if chosen_label == pos_label else (lp_neg >= lp_pos)
    return lp_pos, lp_neg, chosen_is_argmax


def prob_from_pair(
    lp_pos: Optional[float],
    lp_neg: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if lp_pos is None or lp_neg is None:
        return None, None
    m = max(lp_pos, lp_neg)
    p_pos = math.exp(lp_pos - m)
    p_neg = math.exp(lp_neg - m)
    den = p_pos + p_neg
    if den <= 0:
        return None, None
    return p_pos / den, p_neg / den


# ---------------------------------------------------------------------------
# Async model calls
# ---------------------------------------------------------------------------

async def call_chat_completions(
    aclient: Any,
    model_id: str,
    messages: List[Dict[str, str]],
    retries: int = 6,
    seed: int = 7,
    max_tokens: int = 2,
    top_logprobs: int = 5,
) -> Tuple[str, Any]:
    """Chat completions call with capped exponential backoff. Returns (text, choice)."""
    for attempt in range(retries):
        try:
            resp = await aclient.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0,
                top_p=1,
                max_tokens=max_tokens,
                logprobs=True,
                top_logprobs=top_logprobs,
                seed=seed,
            )
            ch = resp.choices[0]
            return (ch.message.content or "").strip(), ch
        except Exception:
            await asyncio.sleep(min(60, 2 ** attempt))
            if attempt == retries - 1:
                return "", None
    return "", None


def _extract_text_from_responses_obj(resp: Any) -> str:
    text_attr = getattr(resp, "output_text", None)
    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr.strip()

    pieces: List[str] = []

    def collect(o: Any) -> None:
        content = getattr(o, "content", None)
        if content is None and isinstance(o, dict):
            content = o.get("content")
        if isinstance(content, list):
            for c in content:
                txt = getattr(c, "text", None)
                if txt is None and isinstance(c, dict):
                    txt = c.get("text")
                if isinstance(txt, str) and txt.strip():
                    pieces.append(txt.strip())

    out_attr = getattr(resp, "output", None)
    if isinstance(out_attr, list):
        for o in out_attr:
            collect(o)

    if not pieces and hasattr(resp, "model_dump"):
        data = resp.model_dump()
        for o in data.get("output", []) or []:
            if isinstance(o, dict):
                collect(o)

    if pieces:
        return " ".join(pieces)
    if hasattr(resp, "model_dump"):
        try:
            return json.dumps(resp.model_dump())
        except Exception:
            pass
    return str(resp)


async def call_responses_gpt5(
    aclient: Any,
    model_id: str,
    system_text: str,
    user_text: str,
    reasoning_effort: Optional[str],
    use_web_search: bool,
    retries: int = 6,
) -> str:
    """Single-input Responses-API call for gpt-5* models. Returns raw text."""
    if "gpt-5" in model_id and reasoning_effort is None:
        raise ValueError(
            "For gpt-5* models, set reasoning_effort to 'none', 'low', 'medium', or 'high'."
        )
    effort = (reasoning_effort or "none").lower()
    combined_input = (
        system_text.strip() + "\n\nReaction conditions as JSON:\n" + user_text
    )
    last_err: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            kwargs: Dict[str, Any] = dict(
                model=model_id, input=combined_input, top_p=1,
            )
            if effort != "none":
                kwargs["reasoning"] = {"effort": effort}
            if use_web_search:
                kwargs["tools"] = [{"type": "web_search"}]
            resp = await aclient.responses.create(**kwargs)
            return _extract_text_from_responses_obj(resp).strip()
        except Exception as e:
            last_err = e
            await asyncio.sleep(min(60, 2 ** attempt))
    print(f"[gpt-5 responses] final error for model {model_id}: {last_err}")
    return ""


async def call_model_generic(
    aclient: Any,
    model_id: str,
    system_text: str,
    user_text: str,
    messages: List[Dict[str, str]],
    reasoning_effort: Optional[str] = None,
    use_web_search: bool = False,
    retries: int = 6,
    seed: int = 7,
) -> Tuple[str, Any, str]:
    """Pick chat.completions for non-gpt-5* models, Responses for gpt-5*.

    Returns (text, extra_obj_or_None, backend) where backend is "chat" or "responses".
    """
    if "gpt-5" in model_id:
        text = await call_responses_gpt5(
            aclient, model_id, system_text, user_text,
            reasoning_effort, use_web_search, retries,
        )
        return text, None, "responses"
    text, choice = await call_chat_completions(
        aclient, model_id, messages, retries=retries, seed=seed,
    )
    return text, choice, "chat"


# ---------------------------------------------------------------------------
# Async evaluation engine for JSONL holdout files
# ---------------------------------------------------------------------------

async def evaluate_holdout(
    model_id: str,
    holdout_paths: Union[str, Path, Sequence[Union[str, Path]]],
    csv_path: Union[str, Path],
    label_pair: Tuple[str, str] = ("P", "N"),
    max_concurrency: int = 50,
    print_interval: int = 5,
    test_mode: bool = False,
    test_limit: int = 10,
    retries: int = 6,
    seed: int = 7,
) -> None:
    """Concurrent, resumable evaluation of one or more JSONL holdout files.

    Output CSV is appended to (deduped by example_key) so the run is resumable.
    """
    pos_label, neg_label = label_pair
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(holdout_paths, (str, Path)):
        path_list: List[Path] = [Path(holdout_paths)]
    else:
        path_list = [Path(p) for p in holdout_paths]

    # Load and assign global indices
    items: List[Dict[str, Any]] = []
    global_idx = 0
    for p in path_list:
        if not p.exists():
            print(f"Warning: holdout path does not exist: {p}")
            continue
        recs = load_jsonl(p)
        if not recs:
            print(f"Warning: holdout file is empty: {p}")
            continue
        for rec in recs:
            gold = gold_label_from_record(rec, valid_labels=label_pair)
            if gold is None:
                continue
            system_text, user_text, messages = build_messages_from_record(rec)
            items.append(dict(
                example_index=global_idx,
                source_path=str(p),
                example_key=build_example_key(str(p), global_idx, system_text, user_text, gold),
                gold_label=gold,
                system_text=system_text,
                user_text=user_text,
                messages=messages,
            ))
            global_idx += 1

    if not items:
        print("No labeled examples found.")
        return

    seen: set = set()
    if csv_path.exists():
        try:
            prev = add_example_keys(pd.read_csv(csv_path))
            if "example_key" in prev.columns:
                seen = set(prev["example_key"].astype(str).tolist())
                print(f"Found existing CSV with {len(seen)} rows. Will skip those examples.")
        except Exception:
            pass

    pending = [it for it in items if it["example_key"] not in seen]
    if test_mode:
        pending = pending[:test_limit]

    total = len(pending)
    if total == 0:
        print("No pending examples.")
        return

    print(f"Evaluating {total} example(s) with concurrency={max_concurrency}...")
    aclient = get_async_client()
    semaphore = asyncio.Semaphore(max_concurrency)
    completed: List[Dict[str, Any]] = []
    t0 = time.time()

    async def worker(it: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            t_start = time.time()
            text, choice = await call_chat_completions(
                aclient, model_id, it["messages"], retries=retries, seed=seed,
            )
            latency = time.time() - t_start

            pred_label = parse_pred_label(text, valid_labels=label_pair)
            lp_pos = lp_neg = None
            prob_pos = prob_neg = None
            chosen_is_argmax = None
            error = ""

            if choice and pred_label in label_pair:
                lp_pos, lp_neg, chosen_is_argmax = extract_logprobs_for_label_chat(
                    choice, pred_label, label_pair=label_pair,
                )
                prob_pos, prob_neg = prob_from_pair(lp_pos, lp_neg)
            else:
                error = "no_choice_or_bad_label"

            return {
                "example_index": it["example_index"],
                "source_path": it["source_path"],
                "example_key": it["example_key"],
                "system_text": it["system_text"],
                "user_text": it["user_text"],
                "gold_label": it["gold_label"],
                "model_id": model_id,
                "model_output": text,
                "pred_label": pred_label,
                f"logprob_{pos_label}": lp_pos,
                f"logprob_{neg_label}": lp_neg,
                f"prob_{pos_label}": prob_pos,
                f"prob_{neg_label}": prob_neg,
                "chosen_is_argmax": chosen_is_argmax,
                "latency_s": latency,
                "timestamp": pd.Timestamp.utcnow().isoformat(),
                "error": error,
            }

    tasks = [asyncio.create_task(worker(it)) for it in pending]
    processed = 0
    for coro in asyncio.as_completed(tasks):
        row = await coro
        completed.append(row)
        processed += 1
        if processed % print_interval == 0 or processed == total:
            elapsed = time.time() - t0
            avg = elapsed / processed
            eta = avg * (total - processed)
            m = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
            print(
                f"[{processed}/{total}] elapsed {fmt_time(elapsed)}  eta {fmt_time(eta)}  "
                f"acc {m['accuracy']:.3f}  f1 {m['f1']:.3f}  "
                f"prec {m['precision']:.3f}  rec {m['recall']:.3f}"
            )

    df_new = pd.DataFrame(completed)
    if csv_path.exists():
        old = add_example_keys(pd.read_csv(csv_path))
        merged = add_example_keys(pd.concat([old, df_new], ignore_index=True))
        merged = merged.sort_values("timestamp").drop_duplicates(
            subset=["example_key"], keep="last"
        )
        merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\nAppended results. CSV updated at: {csv_path}")
    else:
        df_new.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\nWrote CSV to: {csv_path}")

    final = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
    print("\n=== Final metrics for this run ===")
    for k, v in final.items():
        print(f"{k}: {v:.4f}")


# ---------------------------------------------------------------------------
# Async evaluation for manual question dicts (20-question challenge)
# ---------------------------------------------------------------------------

MOF_CLASSIFIER_SYSTEM_PROMPT = (
    "Act as an expert in reticular chemistry. You will receive reaction "
    "conditions as a JSON object with the fields: metal_precursor, "
    "organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, "
    "temperature_C, and time_h. Based on these inputs, output exactly one "
    "uppercase label: 'P' if the conditions are likely to yield a crystalline "
    "metal-organic framework under experimental conditions, or 'N' if not."
)

MOF_INPUT_FIELDS = (
    "metal_precursor",
    "organic_linker",
    "modulator",
    "solvent",
    "metal_concentration_mM",
    "M_L_ratio",
    "temperature_C",
    "time_h",
)


def build_messages_from_question(
    q: Dict[str, Any],
    system_prompt: str = MOF_CLASSIFIER_SYSTEM_PROMPT,
    fields: Sequence[str] = MOF_INPUT_FIELDS,
) -> Tuple[str, str, List[Dict[str, str]]]:
    condition = {k: q.get(k, None) for k in fields}
    user_text = json.dumps(condition, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    return system_prompt, user_text, messages


def sanitize_for_filename(text: str) -> str:
    t = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return t.strip("_") or "model"


async def evaluate_manual_questions(
    manual_questions: List[Dict[str, Any]],
    model_ids: Optional[List[str]] = None,
    rounds: int = 1,
    out_dir: Union[str, Path] = "out",
    base_csv_name: str = "mof_manual_eval",
    reasoning_effort: Optional[str] = None,
    use_web_search: bool = False,
    max_concurrency: int = 25,
    print_interval: int = 5,
    label_pair: Tuple[str, str] = ("P", "N"),
    system_prompt: str = MOF_CLASSIFIER_SYSTEM_PROMPT,
) -> Dict[str, Dict[str, Any]]:
    """Run a manual-question batch against one or more models for N rounds.

    Writes one CSV per (model, round). Returns a summary dict per model with
    per-round metrics, plus mean and std across rounds.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pos_label, neg_label = label_pair

    items: List[Dict[str, Any]] = []
    for idx, q in enumerate(manual_questions):
        gold = (q.get("label") or "").strip().upper()
        if gold not in label_pair:
            continue
        system_text, user_text, messages = build_messages_from_question(q, system_prompt)
        items.append(dict(
            example_index=idx,
            gold_label=gold,
            difficulty=q.get("difficulty", ""),
            system_text=system_text,
            user_text=user_text,
            messages=messages,
        ))
    if not items:
        print("No valid items found in manual_questions.")
        return {}

    if not model_ids:
        raise ValueError("evaluate_manual_questions requires at least one model_id")

    aclient = get_async_client()
    summary: Dict[str, Dict[str, Any]] = {}

    for model_id in model_ids:
        print(f"\n=== Evaluating model: {model_id} ===")
        round_metrics_list: List[Dict[str, float]] = []

        for rnd in range(1, rounds + 1):
            print(f"\n--- Round {rnd} / {rounds} ---")
            semaphore = asyncio.Semaphore(max_concurrency)
            t0 = time.time()
            completed: List[Dict[str, Any]] = []

            async def worker(it: Dict[str, Any]) -> Dict[str, Any]:
                async with semaphore:
                    t_start = time.time()
                    text, extra, backend = await call_model_generic(
                        aclient, model_id, it["system_text"], it["user_text"],
                        it["messages"], reasoning_effort, use_web_search,
                    )
                    latency = time.time() - t_start

                    pred_label = parse_pred_label(text, valid_labels=label_pair)
                    lp_pos = lp_neg = None
                    prob_pos = prob_neg = None
                    chosen_is_argmax = None
                    error = ""

                    if extra and pred_label in label_pair and backend == "chat":
                        lp_pos, lp_neg, chosen_is_argmax = extract_logprobs_for_label_chat(
                            extra, pred_label, label_pair=label_pair,
                        )
                        prob_pos, prob_neg = prob_from_pair(lp_pos, lp_neg)
                    else:
                        if backend == "chat" and pred_label not in label_pair:
                            error = "no_extra_or_bad_label"
                        if backend == "responses" and not text:
                            error = "empty_responses_output"

                    return {
                        "example_index": it["example_index"],
                        "difficulty": it["difficulty"],
                        "system_text": it["system_text"],
                        "user_text": it["user_text"],
                        "gold_label": it["gold_label"],
                        "model_id": model_id,
                        "backend": backend,
                        "model_output": text,
                        "pred_label": pred_label,
                        f"logprob_{pos_label}": lp_pos,
                        f"logprob_{neg_label}": lp_neg,
                        f"prob_{pos_label}": prob_pos,
                        f"prob_{neg_label}": prob_neg,
                        "chosen_is_argmax": chosen_is_argmax,
                        "latency_s": latency,
                        "timestamp": pd.Timestamp.utcnow().isoformat(),
                        "error": error,
                    }

            tasks = [asyncio.create_task(worker(it)) for it in items]
            total = len(tasks)
            processed = 0
            for coro in asyncio.as_completed(tasks):
                row = await coro
                completed.append(row)
                processed += 1
                if processed % print_interval == 0 or processed == total:
                    elapsed = time.time() - t0
                    avg = elapsed / processed
                    eta = avg * (total - processed)
                    m = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
                    print(
                        f"[{processed}/{total}] elapsed {fmt_time(elapsed)}  "
                        f"eta {fmt_time(eta)}  acc {m['accuracy']:.3f}  "
                        f"f1 {m['f1']:.3f}  prec {m['precision']:.3f}  "
                        f"rec {m['recall']:.3f}"
                    )

            df = pd.DataFrame(completed)
            model_suffix = model_id[-7:] if len(model_id) >= 7 else model_id
            model_tag = sanitize_for_filename(model_suffix)
            reason_tag = (
                f"reason_{reasoning_effort.lower()}"
                if reasoning_effort and reasoning_effort.lower() != "none"
                else "reason_none"
            )
            csv_path = out_dir / f"{base_csv_name}_{model_tag}_{reason_tag}_round{rnd}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"Wrote CSV for model {model_id}, round {rnd} to: {csv_path}")

            m_round = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
            round_metrics_list.append(m_round)
            print("\nRound metrics:")
            for k, v in m_round.items():
                print(f"  {k}: {v:.4f}")

        metric_names = ["accuracy", "precision", "recall", "f1"]
        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}
        for k in metric_names:
            vals = [rm.get(k, 0.0) for rm in round_metrics_list]
            arr = np.array(vals, dtype=float) if vals else np.array([0.0])
            means[k] = float(arr.mean())
            stds[k] = float(arr.std(ddof=0))

        print(f"\n=== Summary for model {model_id} over {rounds} round(s) ===")
        for k in metric_names:
            print(f"{k}: mean={means[k]:.4f}, std={stds[k]:.4f}")

        summary[model_id] = {
            "round_metrics": round_metrics_list,
            "mean": means,
            "std": stds,
        }

    return summary


# ---------------------------------------------------------------------------
# Async evaluation for arbitrary condition DataFrames (synthesis screening)
# ---------------------------------------------------------------------------

def load_screening_csv(
    path: Union[str, Path],
    encoding: str = "cp1252",
    expected_cols: Sequence[str] = (
        "metal_precursor", "organic_linker", "modulator", "solvent",
        "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h",
        "experimental",
    ),
    numeric_cols: Sequence[str] = (
        "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h",
    ),
) -> pd.DataFrame:
    df = pd.read_csv(
        path, sep=None, engine="python",
        na_values=["null", "NULL", "NaN", "", " "],
        keep_default_na=True, encoding=encoding,
    )
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()
    df = df.replace({"null": np.nan, "NULL": np.nan, "": np.nan, " ": np.nan})
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in CSV: {missing}")
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_messages_from_row(
    row: pd.Series,
    system_prompt: str = MOF_CLASSIFIER_SYSTEM_PROMPT,
    fields: Sequence[str] = MOF_INPUT_FIELDS,
) -> Tuple[str, str, List[Dict[str, str]]]:
    def convert(v: Any) -> Any:
        if pd.isna(v):
            return None
        if isinstance(v, (np.integer, np.floating)):
            return float(v)
        if isinstance(v, (int, float)):
            return v
        s = str(v).strip()
        if s.lower() == "null" or s == "":
            return None
        return s

    condition = {k: convert(row.get(k)) for k in fields}
    user_text = json.dumps(condition, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    return system_prompt, user_text, messages


async def evaluate_screening_dataframe(
    model_id: str,
    df: pd.DataFrame,
    out_csv: Union[str, Path],
    gold_col: str = "experimental",
    label_pair: Tuple[str, str] = ("P", "N"),
    max_concurrency: int = 25,
    print_interval: int = 5,
    system_prompt: str = MOF_CLASSIFIER_SYSTEM_PROMPT,
) -> pd.DataFrame:
    """Score every row of `df` and join predictions back. Returns the joined frame."""
    pos_label, neg_label = label_pair
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Sample JSON fed to the model ===")
    for i in range(min(5, len(df))):
        _, user_text, _ = build_messages_from_row(df.iloc[i], system_prompt)
        print(f"[Row {i}] {user_text}")
    print("====================================\n")

    items: List[Dict[str, Any]] = []
    for idx, row in df.reset_index(drop=True).iterrows():
        gold = str(row.get(gold_col, "")).strip().upper()
        gold_value = gold if gold in label_pair else None
        system_text, user_text, messages = build_messages_from_row(row, system_prompt)
        items.append(dict(
            example_index=idx,
            gold_label=gold_value,
            system_text=system_text,
            user_text=user_text,
            messages=messages,
        ))
    if not items:
        print("No rows to score.")
        return df

    aclient = get_async_client()
    semaphore = asyncio.Semaphore(max_concurrency)
    completed: List[Dict[str, Any]] = []
    t0 = time.time()
    total = len(items)
    print(f"Evaluating {total} row(s) with concurrency={max_concurrency}...")

    async def worker(it: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            t_start = time.time()
            text, choice = await call_chat_completions(
                aclient, model_id, it["messages"],
            )
            latency = time.time() - t_start
            pred_label = parse_pred_label(text, valid_labels=label_pair)
            lp_pos = lp_neg = None
            prob_pos = prob_neg = None
            chosen_is_argmax = None
            error = ""
            if choice and pred_label in label_pair:
                lp_pos, lp_neg, chosen_is_argmax = extract_logprobs_for_label_chat(
                    choice, pred_label, label_pair=label_pair,
                )
                prob_pos, prob_neg = prob_from_pair(lp_pos, lp_neg)
            else:
                error = "no_choice_or_bad_label"
            return {
                "example_index": it["example_index"],
                "system_text": it["system_text"],
                "user_text": it["user_text"],
                "gold_label": it["gold_label"],
                "model_output": text,
                "pred_label": pred_label,
                f"logprob_{pos_label}": lp_pos,
                f"logprob_{neg_label}": lp_neg,
                f"prob_{pos_label}": prob_pos,
                f"prob_{neg_label}": prob_neg,
                "chosen_is_argmax": chosen_is_argmax,
                "latency_s": latency,
                "timestamp": pd.Timestamp.utcnow().isoformat(),
                "error": error,
            }

    tasks = [asyncio.create_task(worker(it)) for it in items]
    processed = 0
    for coro in asyncio.as_completed(tasks):
        row = await coro
        completed.append(row)
        processed += 1
        if processed % print_interval == 0 or processed == total:
            elapsed = time.time() - t0
            avg = elapsed / processed
            eta = avg * (total - processed)
            m = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
            print(
                f"[{processed}/{total}] elapsed {fmt_time(elapsed)}  eta {fmt_time(eta)}  "
                f"acc {m['accuracy']:.3f}  f1 {m['f1']:.3f}  "
                f"prec {m['precision']:.3f}  rec {m['recall']:.3f}"
            )

    df_pred = pd.DataFrame(completed).sort_values("example_index")
    join_cols = [
        "system_text", "user_text", "pred_label",
        f"prob_{pos_label}", f"prob_{neg_label}",
    ]
    df_out = df.reset_index(drop=True).join(df_pred[join_cols], how="left")
    df_out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nWrote CSV with predictions to: {out_csv}")

    final = running_metrics(completed, pos_label=pos_label, neg_label=neg_label)
    print("\n=== Overall metrics ===")
    for k, v in final.items():
        print(f"{k}: {v:.4f}")
    return df_out


# ---------------------------------------------------------------------------
# Asyncio entrypoint shim (handles both notebook and CLI runtimes)
# ---------------------------------------------------------------------------

def run_async(coro: Awaitable[Any]) -> Any:
    """Run an awaitable in either a CLI process or an already-running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (e.g. Jupyter). Use nest_asyncio if available.
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    return loop.run_until_complete(coro)
