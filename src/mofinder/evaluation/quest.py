"""Repeated model evaluation on the fixed MOF Quest reaction panel.

Model inputs are restricted to eight reaction-condition fields. Reference
labels remain local and are used for scoring.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

DEFAULT_MODEL_ID = "ft:gpt-4.1-2025-04-14:deep-synthesis-lab:98test:EM0eHcxS"
OUT_DIR_BASE = Path("results/evaluation/mof_quest")
MAX_CONCURRENCY = 25
PRINT_INTERVAL = 5
RETRIES = 6
SEED = 7
REPO_ROOT = Path(__file__).resolve().parents[3]
CONDITION_FIELDS = (
    "metal_precursor", "organic_linker", "modulator", "solvent",
    "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h",
)


def _default_prompt():
    return (REPO_ROOT / "prompts/dataset_classification.txt").read_text(encoding="utf-8")


def build_messages_from_question(q: Dict[str, Any], system_prompt: Optional[str] = None) -> Tuple[str, str, List[Dict[str, str]]]:
    """Build system and user messages from a manual question dict."""
    system_text = _default_prompt() if system_prompt is None else system_prompt

    allowed_fields = [
        "metal_precursor",
        "organic_linker",
        "modulator",
        "solvent",
        "metal_concentration_mM",
        "M_L_ratio",
        "temperature_C",
        "time_h",
    ]
    condition = {k: q.get(k, None) for k in allowed_fields}
    user_text = json.dumps(condition, ensure_ascii=False)

    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]
    return system_text, user_text, messages

def gold_label_from_q(q: Dict[str, Any]) -> Optional[str]:
    g = q.get("label", "").strip().upper()
    return g if g in ("P", "N") else None

def build_items_from_manual_questions(
    manual_questions: List[Dict[str, Any]], system_prompt: Optional[str] = None
) -> List[Dict[str, Any]]:
    items = []
    for idx, q in enumerate(manual_questions):
        gold = gold_label_from_q(q)
        if gold not in ("P", "N"):
            continue
        system_text, user_text, messages = build_messages_from_question(q, system_prompt)
        items.append(
            dict(
                example_index=idx,
                question=q.get("question", f"Q{idx + 1}"),
                reaction_id=q.get("reaction_id", ""),
                gold_label=gold,
                difficulty=q.get("difficulty", ""),
                system_text=system_text,
                user_text=user_text,
                messages=messages,
            )
        )
    return items

def parse_pred_label(text: str) -> str:
    m = re.search(r"[PN]", (text or "").upper())
    return m.group(0) if m else ""

def running_metrics(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    y_true, y_pred = [], []
    for r in rows:
        if r.get("gold_label") in ("P", "N") and r.get("pred_label") in ("P", "N"):
            y_true.append(1 if r["gold_label"] == "P" else 0)
            y_pred.append(1 if r["pred_label"] == "P" else 0)
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

def prob_from_pair(
    lp_P: Optional[float],
    lp_N: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if lp_P is None or lp_N is None:
        return None, None
    m = max(lp_P, lp_N)
    pP = math.exp(lp_P - m)
    pN = math.exp(lp_N - m)
    den = pP + pN
    if den <= 0:
        return None, None
    return pP / den, pN / den

def sanitize_for_filename(text: str) -> str:
    """Retain letters, digits, periods, underscores, and hyphens for filenames."""
    import re
    t = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    t = t.strip("_")
    return t or "model"

def extract_logprobs_for_label_chat(
    choice_obj: Any,
    chosen_label: str,
) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
    lp = getattr(choice_obj, "logprobs", None)
    if not lp or not getattr(lp, "content", None):
        return None, None, None

    target_item = None
    for tok in lp.content:
        t = getattr(tok, "token", "")
        norm = re.sub(r"\s+", "", t).upper()
        if norm in ("P", "N") and norm == chosen_label:
            target_item = tok
            break

    if target_item is None:
        for tok in lp.content:
            t = getattr(tok, "token", "")
            norm = re.sub(r"\s+", "", t).upper()
            if norm in ("P", "N"):
                target_item = tok
                break

    if target_item is None:
        return None, None, None

    pred_lp = getattr(target_item, "logprob", None)
    alts = getattr(target_item, "top_logprobs", None) or []

    lp_P = pred_lp if chosen_label == "P" and pred_lp is not None else None
    lp_N = pred_lp if chosen_label == "N" and pred_lp is not None else None

    for alt in alts:
        a_tok = getattr(alt, "token", "")
        a_lp = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        norm = re.sub(r"\s+", "", a_tok).upper()
        if norm == "P" and lp_P is None:
            lp_P = a_lp
        elif norm == "N" and lp_N is None:
            lp_N = a_lp

    chosen_is_argmax = None
    if lp_P is not None and lp_N is not None:
        if chosen_label == "P":
            chosen_is_argmax = lp_P >= lp_N
        else:
            chosen_is_argmax = lp_N >= lp_P

    return lp_P, lp_N, chosen_is_argmax

def extract_logprobs_for_label_responses(
    output_text_obj: Any,
    chosen_label: str,
) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
    """
    For Responses output_text objects with:
        .logprobs: List[{token, logprob, top_logprobs}]
    """
    lp_seq = getattr(output_text_obj, "logprobs", None)
    if not lp_seq:
        return None, None, None

    target_item = None

    # First pass: exact chosen label
    for tok in lp_seq:
        t = getattr(tok, "token", "")
        norm = re.sub(r"\s+", "", t).upper()
        if norm in ("P", "N") and norm == chosen_label:
            target_item = tok
            break

    # Fallback: any P or N
    if target_item is None:
        for tok in lp_seq:
            t = getattr(tok, "token", "")
            norm = re.sub(r"\s+", "", t).upper()
            if norm in ("P", "N"):
                target_item = tok
                break

    if target_item is None:
        return None, None, None

    pred_lp = getattr(target_item, "logprob", None)
    alts = getattr(target_item, "top_logprobs", None) or []

    lp_P = pred_lp if chosen_label == "P" and pred_lp is not None else None
    lp_N = pred_lp if chosen_label == "N" and pred_lp is not None else None

    for alt in alts:
        a_tok = getattr(alt, "token", "")
        a_lp = getattr(alt, "logprob", None)
        if a_lp is None:
            continue
        norm = re.sub(r"\s+", "", a_tok).upper()
        if norm == "P" and lp_P is None:
            lp_P = a_lp
        elif norm == "N" and lp_N is None:
            lp_N = a_lp

    chosen_is_argmax = None
    if lp_P is not None and lp_N is not None:
        if chosen_label == "P":
            chosen_is_argmax = lp_P >= lp_N
        else:
            chosen_is_argmax = lp_N >= lp_P

    return lp_P, lp_N, chosen_is_argmax

async def call_model_chat(
    model_id: str,
    messages: List[Dict[str, str]],
    retries: int = RETRIES,
    seed: int = SEED,
    *, client: Any,
) -> Tuple[str, Any]:
    """Call Chat Completions with fixed sampling, token-limit, and seed settings."""
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0,
                top_p=1,
                max_tokens=2,
                logprobs=True,
                top_logprobs=5,
                seed=seed,
            )
            ch = resp.choices[0]
            return (ch.message.content or "").strip(), ch
        except Exception:
            await asyncio.sleep(min(60, 2**attempt))
            if attempt == retries - 1:
                return "", None

def extract_text_from_responses_obj(resp: Any) -> str:
    """
    Extract plain text from a Responses API object.
    Fall back to model_dump() for object layouts without output_text.
    """
    # 1) Try output_text attribute if it exists and is a string
    text_attr = getattr(resp, "output_text", None)
    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr.strip()

    pieces: List[str] = []

    # Helper to pull text from a single output item (object or dict)
    def collect_from_output_item(o: Any):
        # object-like
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

    # 2) Try resp.output as attribute
    out_attr = getattr(resp, "output", None)
    if isinstance(out_attr, list):
        for o in out_attr:
            collect_from_output_item(o)

    # 3) If still nothing and model_dump exists, parse the dict
    if not pieces and hasattr(resp, "model_dump"):
        data = resp.model_dump()
        out_list = data.get("output") or []
        if isinstance(out_list, list):
            for o in out_list:
                if isinstance(o, dict):
                    collect_from_output_item(o)

    if pieces:
        return " ".join(pieces)

    # A response without text is unscored. Metadata is not a model prediction.
    return ""

async def call_model_responses_gpt5(
    model_id: str,
    system_text: str,
    user_text: str,
    reasoning_effort: Optional[str],
    use_web_search: bool,
    retries: int = RETRIES,
    *, client: Any,
) -> str:
    """
    Call the Responses API with a combined prompt and condition string.

    - system_text: classification prompt
    - user_text: the JSON condition string
    - reasoning_effort: explicit setting for the gpt-5* and gpt-6* branches
    - use_web_search: if True, add {type: "web_search"} tool

    Returns raw text output (no logprobs).
    """
    if ("gpt-5" in model_id or "gpt-6" in model_id) and reasoning_effort is None:
        raise ValueError(
            "For gpt-5 &6* models, set reasoning_effort to 'none', 'low', 'medium', or 'high'."
        )

    effort = (reasoning_effort or "none").lower()


    # Pack system prompt + JSON into a single input string
    combined_input = (
        system_text.strip()
        + "\n\nReaction conditions as JSON:\n"
        + user_text
    )

    last_error = None

    for attempt in range(retries):
        try:
            kwargs: Dict[str, Any] = dict(
                model=model_id,
                input=combined_input#,
                #top_p=1,
            )

            if effort != "none":
                kwargs["reasoning"] = {"effort": effort}

            if use_web_search:
                kwargs["tools"] = [{"type": "web_search"}]

            resp = await client.responses.create(**kwargs)

            text = extract_text_from_responses_obj(resp)
            return text.strip()

        except Exception as e:
            last_error = e
            await asyncio.sleep(min(60, 2**attempt))

    # All request attempts failed.
    print(f"[gpt-5 responses] final error for model {model_id}: {last_error}")
    return ""

async def call_model_generic(
    model_id: str,
    system_text: str,
    user_text: str,
    messages: List[Dict[str, str]],
    reasoning_effort: Optional[str],
    use_web_search: bool,
    *, client: Any, retries: int = RETRIES, seed: int = SEED,
) -> Tuple[str, Any, str]:
    """
    - Other models: chat.completions (with logprobs)
    - gpt-5* and gpt-6*: Responses API (no logprobs)
    Returns: text, extra_obj, backend
    """
    if "gpt-5" in model_id or "gpt-6" in model_id:
        text = await call_model_responses_gpt5(
            model_id=model_id,
            system_text=system_text,
            user_text=user_text,
            reasoning_effort=reasoning_effort,
            use_web_search=use_web_search,
            client=client, retries=retries,
        )
        backend = "responses"
        extra_obj = None
    else:
        text, extra_obj = await call_model_chat(
            model_id=model_id,
            messages=messages,
            client=client, retries=retries, seed=seed,
        )
        backend = "chat"

    return text, extra_obj, backend

async def evaluate_mof_classifier(
    model_ids: Optional[List[str]] = None,
    rounds: int = 1,
    out_dir: Path = OUT_DIR_BASE,
    base_csv_name: str = "mof_manual_eval",
    reasoning_effort: Optional[str] = None,
    use_web_search: bool = False,
    max_concurrency: int = MAX_CONCURRENCY,
    print_interval: int = PRINT_INTERVAL,
    manual_questions: Optional[List[Dict[str, Any]]] = None,
    *, client: Any = None, system_prompt: Optional[str] = None,
    retries: int = RETRIES, seed: int = SEED,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Evaluate one or more models on the fixed question panel for repeated rounds.

    - model_ids: list of model ids. If None, uses [DEFAULT_MODEL_ID].
    - rounds: number of repeated runs per model.
    - reasoning_effort: used by the gpt-5* and gpt-6* Responses API branches.
    - Writes one combined CSV per model after all rounds.
    - Returns metrics summary per model with round metrics, mean, and std.
    """
    out_dir = Path(out_dir)
    if manual_questions is None:
        manual_questions = load_questions(REPO_ROOT / "benchmarks/mof_quest/questions.json")

    items = build_items_from_manual_questions(manual_questions, system_prompt)
    if not items:
        print("No valid questions found.")
        return {}

    if model_ids is None or len(model_ids) == 0:
        model_ids = [DEFAULT_MODEL_ID]

    validate_request_settings(model_ids, reasoning_effort, rounds, max_concurrency,
                              print_interval, retries, seed)
    if client is None:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_summary: Dict[str, Dict[str, Any]] = {}

    for model_id in model_ids:
        print(f"\n=== Evaluating model: {model_id} ===")

        # Validate reasoning settings before creating async tasks
        effort = (reasoning_effort or "none").lower()

        if "gpt-6" in model_id and effort == "none":
            raise ValueError(
                f"The supplied workflow rejects reasoning_effort='none' for {model_id}. "
                "Use 'low', 'medium', or 'high'."
            )

        if model_id in ("gpt-5", "gpt-5-2025-08-07") and effort == "none":
            raise ValueError(
                f"The supplied workflow rejects reasoning_effort='none' for {model_id}. "
                "Use 'minimal', 'low', 'medium', or 'high'."
            )

        round_metrics_list: List[Dict[str, float]] = []

        all_round_rows: List[Dict[str, Any]] = []

        for rnd in range(1, rounds + 1):
            show_round = (rnd == 1) or (rnd % 10 == 0) or (rnd == rounds)
            if show_round:
                print(f"\n--- Round {rnd} / {rounds} ---")

            semaphore = asyncio.Semaphore(max_concurrency)
            t0 = time.time()
            completed: List[Dict[str, Any]] = []
            async def worker(it):
                async with semaphore:
                    t_start = time.time()
                    text, extra_obj, backend = await call_model_generic(
                        model_id=model_id,
                        system_text=it["system_text"],
                        user_text=it["user_text"],
                        messages=it["messages"],
                        reasoning_effort=reasoning_effort,
                        use_web_search=use_web_search,
                        client=client, retries=retries, seed=seed,
                    )
                    latency = time.time() - t_start
            
                    pred_label = parse_pred_label(text)
                    lp_P = lp_N = None
                    prob_P = prob_N = None
                    chosen_is_argmax = None
                    error = ""
            
                    if extra_obj and pred_label in ("P", "N"):
                        if backend == "chat":
                            lp_P, lp_N, chosen_is_argmax = extract_logprobs_for_label_chat(
                                extra_obj, pred_label
                            )
                            prob_P, prob_N = prob_from_pair(lp_P, lp_N)
                    else:
                        # Record empty responses and invalid labels.
                        if backend == "chat" and pred_label not in ("P", "N"):
                            error = "no_extra_or_bad_label"
                        if backend == "responses" and not text:
                            error = "empty_responses_output"
                        elif backend == "responses" and pred_label not in ("P", "N"):
                            error = "bad_responses_label"
            
                    row = dict(
                        example_index=it["example_index"],
                        question=it["question"],
                        reaction_id=it["reaction_id"],
                        reasoning_effort=reasoning_effort,
                        use_web_search=use_web_search,
                        web_search_enabled=(use_web_search and backend == "responses"),
                        difficulty=it["difficulty"],
                        system_text=it["system_text"],
                        user_text=it["user_text"],
                        gold_label=it["gold_label"],
                        model_id=model_id,
                        backend=backend,
                        model_output=text,
                        pred_label=pred_label,
                        logprob_P=lp_P,
                        logprob_N=lp_N,
                        prob_P=prob_P,
                        prob_N=prob_N,
                        chosen_is_argmax=chosen_is_argmax,
                        latency_s=latency,
                        timestamp=pd.Timestamp.utcnow().isoformat(),
                        error=error,
                    )
                    return row



            tasks = [asyncio.create_task(worker(it)) for it in items]
            total = len(tasks)
            processed = 0

            for coro in asyncio.as_completed(tasks):
                row = await coro
                completed.append(row)
                processed += 1

                if show_round and ((processed % print_interval == 0) or (processed == total)):
                    elapsed = time.time() - t0
                    avg = elapsed / processed
                    eta = avg * (total - processed)
                    m = running_metrics(completed)
                    print(
                        f"[{processed}/{total}] elapsed {fmt_time(elapsed)}  "
                        f"eta {fmt_time(eta)}  "
                        f"acc {m['accuracy']:.3f}  f1 {m['f1']:.3f}  "
                        f"prec {m['precision']:.3f}  rec {m['recall']:.3f}"
                    )

            df = pd.DataFrame(completed)
            df["round"] = rnd
            all_round_rows.extend(df.to_dict("records"))

            # Short tag: last 7 chars of model id
            model_suffix = model_id[-7:] if len(model_id) >= 7 else model_id
            model_tag = sanitize_for_filename(model_suffix)

            if reasoning_effort and reasoning_effort.lower() != "none":
                reason_tag = f"reason_{reasoning_effort.lower()}"
            else:
                reason_tag = "reason_none"

            # Round metrics
            m_round = running_metrics(completed)
            round_metrics_list.append(m_round)

            if show_round:
                print("\nRound metrics:")
                for k, v in m_round.items():
                    print(f"  {k}: {v:.4f}")

        all_rounds_df = pd.DataFrame(all_round_rows)
        csv_name = f"{base_csv_name}_{model_tag}_{reason_tag}_{rounds}rounds.csv"
        csv_path = out_dir / csv_name

        # Ensure directory exists right before writing
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        all_rounds_df.to_csv(str(csv_path), index=False, encoding="utf-8-sig")
        print(f"Wrote all {rounds} rounds for model {model_id} to: {csv_path}")

        # Aggregate over rounds
        metric_names = ["accuracy", "precision", "recall", "f1"]
        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}

        for k in metric_names:
            vals = [rm.get(k, 0.0) for rm in round_metrics_list]
            if vals:
                arr = np.array(vals, dtype=float)
                means[k] = float(arr.mean())
                stds[k] = float(arr.std(ddof=0))
            else:
                means[k] = 0.0
                stds[k] = 0.0

        print(f"\n=== Summary for model {model_id} over {rounds} round(s) ===")
        for k in metric_names:
            print(f"{k}: mean={means[k]:.4f}, std={stds[k]:.4f}")

        metrics_summary[model_id] = {
            "round_metrics": round_metrics_list,
            "mean": means,
            "std": stds,
        }

    return metrics_summary


def load_questions(path):
    """Read a fixed panel; metadata stays outside the model's condition JSON."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("The question file must contain a nonempty list.")
    ids, question_names, questions = set(), set(), []
    for record in records:
        conditions = record.get("conditions")
        if not isinstance(conditions, dict) or set(conditions) != set(CONDITION_FIELDS):
            raise ValueError("Each question needs the eight reaction condition fields.")
        if record.get("label") not in ("P", "N"):
            raise ValueError("Each question needs a P or N label.")
        rid, name = record.get("reaction_id"), record.get("question")
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError("Reaction IDs must be present and unique within the panel.")
        if not isinstance(name, str) or not name or name in question_names:
            raise ValueError("Question names must be present and unique within the panel.")
        for key in CONDITION_FIELDS[4:]:
            value = conditions[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError(f"{name}: {key} must be a finite number or null.")
        ids.add(rid)
        question_names.add(name)
        questions.append(dict(conditions, label=record["label"], question=name,
                              reaction_id=rid, difficulty=record.get("difficulty", "")))
    return questions


def load_config(path):
    """Resolve configuration paths against its project root."""
    path = Path(path).expanduser().resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / config.get("project_root", "..")).resolve()
    for key in ("questions_file", "prompt_file", "output_root"):
        config[key] = (root / Path(config[key]).expanduser()).resolve()
    config["config_file"] = path
    config["project_root"] = root
    return config


def validate_request_settings(model_ids, reasoning_effort, rounds, max_concurrency,
                              print_interval, retries, seed):
    """Validate model IDs, reasoning settings, and execution limits before dispatch."""
    for name, value in (("rounds", rounds), ("max_concurrency", max_concurrency),
                        ("print_interval", print_interval), ("retries", retries)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer.")
    if not model_ids or any(not isinstance(m, str) or not m.strip() for m in model_ids):
        raise ValueError("Provide at least one nonempty model ID.")
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("Model IDs must be unique within a group.")
    tags = [sanitize_for_filename(m[-7:]) for m in model_ids]
    if len(set(tags)) != len(tags):
        raise ValueError("Model suffixes collide in the original output filenames; use separate groups.")
    effort = (reasoning_effort or "none").lower()
    for model_id in model_ids:
        if "gpt-6" in model_id and effort == "none":
            raise ValueError(f"{model_id}: the supplied workflow requires an explicit reasoning effort.")
        if model_id in ("gpt-5", "gpt-5-2025-08-07") and effort == "none":
            raise ValueError(f"{model_id}: the supplied workflow rejects reasoning_effort='none'.")
        if ("gpt-5" in model_id or "gpt-6" in model_id) and reasoning_effort is None:
            raise ValueError(f"{model_id}: specify reasoning_effort explicitly.")


def validate_config(config, group=None):
    """Inspect inputs and request settings without constructing an API client."""
    questions = load_questions(config["questions_file"])
    prompt = config["prompt_file"].read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("The classification prompt is empty.")
    names = [group] if group else list(config["groups"])
    if not names:
        raise ValueError("The configuration contains no model groups.")
    reports = {}
    for name in names:
        if name not in config["groups"]:
            raise ValueError(f"Unknown model group: {name}")
        selected = config["groups"][name]
        warnings = []
        errors = []
        if type(selected.get("use_web_search")) is not bool:
            errors.append("use_web_search must be a boolean.")
        try:
            validate_request_settings(selected["model_ids"], selected.get("reasoning_effort"),
                                      selected["rounds"], config["max_concurrency"],
                                      config["print_interval"], config["retries"], config["seed"])
        except ValueError as exc:
            errors.append(str(exc))
        if selected.get("use_web_search"):
            chat_models = [m for m in selected["model_ids"] if "gpt-5" not in m and "gpt-6" not in m]
            if chat_models:
                warnings.append("The Chat Completions branch does not send a web-search tool: " + ", ".join(chat_models))
        reports[name] = {"valid": not errors, "errors": errors, "warnings": warnings,
                         "requests": len(questions) * selected["rounds"] * len(selected["model_ids"])}
    return {"questions": len(questions),
            "labels": {label: sum(q["label"] == label for q in questions) for label in ("P", "N")},
            "groups": reports}


async def run_evaluation(config, group=None, *, client=None, output_dir=None):
    """Run one configured group and save its input hashes and metric summary."""
    group = group or config["default_group"]
    report = validate_config(config, group)
    selected_report = report["groups"][group]
    if not selected_report["valid"]:
        raise ValueError("; ".join(selected_report["errors"]))
    for warning in selected_report["warnings"]:
        print("Warning:", warning)
    selected = config["groups"][group]
    if client is None:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = config["output_root"] / group / stamp
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Choose an empty output directory to preserve previous runs.")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "group": group,
        "settings": dict(selected, max_concurrency=config["max_concurrency"],
                         retries=config["retries"], seed=config["seed"],
                         print_interval=config["print_interval"]),
        "inputs": {name: {"file": str(config[name]),
                          "sha256": hashlib.sha256(config[name].read_bytes()).hexdigest()}
                   for name in ("questions_file", "prompt_file")},
        "validation": report,
        "status": "running",
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    try:
        summary = await evaluate_mof_classifier(
            **selected, out_dir=output_dir, max_concurrency=config["max_concurrency"],
            print_interval=config["print_interval"], retries=config["retries"], seed=config["seed"],
            manual_questions=load_questions(config["questions_file"]),
            system_prompt=config["prompt_file"].read_text(encoding="utf-8"), client=client,
        )
    except BaseException:
        manifest["status"] = "interrupted"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        raise
    manifest["status"] = "completed"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "metrics_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {"output_dir": output_dir, "metrics": summary}


def run(config, group=None, **kwargs):
    """Synchronous entry point. In notebooks, await run_evaluation instead."""
    return asyncio.run(run_evaluation(config, group, **kwargs))


def analyze_results(paths, output_file=None):
    """Recompute each saved file's per-round metrics, means, and population SDs."""
    summaries = {}
    for path in paths:
        path = Path(path)
        frame = pd.read_csv(path, keep_default_na=False)
        required = {"gold_label", "pred_label", "round", "model_id", "example_index"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{path}: missing columns {sorted(required - set(frame.columns))}")
        if frame.empty:
            raise ValueError(f"{path}: no evaluation rows.")
        if frame.duplicated(["model_id", "round", "example_index"]).any():
            raise ValueError(f"{path}: duplicate model/round/example rows.")
        for model_id, model_frame in frame.groupby("model_id", sort=False):
            round_metrics, round_counts, round_ids = [], [], []
            for round_id, round_frame in model_frame.groupby("round", sort=True):
                rows = round_frame.to_dict("records")
                round_metrics.append(running_metrics(rows))
                n_valid = sum(r.get("gold_label") in ("P", "N") and r.get("pred_label") in ("P", "N") for r in rows)
                round_ids.append(int(round_id))
                round_counts.append({"total": len(rows), "scored": n_valid, "unscored": len(rows) - n_valid})
            keys = ("accuracy", "precision", "recall", "f1")
            summaries[f"{path.resolve()}::{model_id}"] = {
                "model_id": model_id, "rounds": round_ids,
                "round_metrics": round_metrics, "round_counts": round_counts,
                "mean": {key: float(np.mean([r[key] for r in round_metrics])) for key in keys},
                "std": {key: float(np.std([r[key] for r in round_metrics], ddof=0)) for key in keys},
            }
    if output_file is not None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", type=Path, default=REPO_ROOT / "configs/quest_evaluation.json")
        command.add_argument("--group")
        if name == "run":
            command.add_argument("--output-dir", type=Path)
    command = subparsers.add_parser("analyze")
    command.add_argument("csv", nargs="+", type=Path)
    command.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "analyze":
        result = analyze_results(args.csv, args.output)
    else:
        config = load_config(args.config)
        if args.command == "validate":
            result = validate_config(config, args.group)
        else:
            result = run(config, args.group, output_dir=args.output_dir)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
