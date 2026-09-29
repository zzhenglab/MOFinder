#!/usr/bin/env python3
"""Manual, opt-in inference timing benchmark for the 22 MOF-Quest reactions.

This is not a test, demo or CI entry point. Importing it, --help, --list-models,
and --analyze never load credentials or make network requests. Install the
official Python SDK separately (``python -m pip install openai``).

Examples (paid API requests occur only with --run):
  python src/mofinder/evaluation/benchmark_inference_time.py --list-models
  python src/mofinder/evaluation/benchmark_inference_time.py --run --arms gpt41mini --output timings
  python src/mofinder/evaluation/benchmark_inference_time.py --run --ft-model YOUR_ACCESSIBLE_FT_ID
  python src/mofinder/evaluation/benchmark_inference_time.py --analyze timings/events.jsonl
  python src/mofinder/evaluation/benchmark_inference_time.py --run --arms local_ft \
      --local-url http://127.0.0.1:8081 --output local_timings

API credentials come only from OPENAI_API_KEY or a hidden interactive prompt.
Each arm runs separately. --concurrency controls reaction pipelines within a
panel, not the number of model arms. At concurrency 1, five repeats request
110 evaluations per arm; a web evaluation makes two model calls. Retries can
add calls. No Batch jobs or million-call runs are submitted.

Local mode targets the released GPT-oss-MOF Harmony/P/N scoring protocol on
an already-running llama.cpp server, with N=45/P=47 checked by its tokenizer.
It does not download a model, start/restart a server or clear caches. Supply
--local-model-file to hash and verify the loaded GGUF. Local results therefore
describe the supplied server/cache lifecycle, not automatically the cold-panel
startup protocol used in the paper. Tokenization and scoring are both timed.

Reference interfaces:
https://developers.openai.com/api/docs/libraries
https://developers.openai.com/api/docs/guides/tools-web-search
https://developers.openai.com/api/docs/guides/rate-limits
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date, datetime, timezone
import getpass
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import sys
import time
from urllib.parse import urlparse
import warnings

FIELDS = ("metal_precursor", "organic_linker", "modulator", "solvent",
          "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h")
# Exact notebook instruction, including its embedded indentation/newlines.
SYSTEM_PROMPT = (
    "Act as an expert in reticular chemistry. You will receive reaction conditions as a JSON object with the fields: \n"
    "    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, and time_h. \n"
    "    Based on these inputs, output exactly one uppercase label: 'P' if the conditions are likely to yield a crystalline \n"
    "    metal-organic framework under experimental conditions, or 'N' if not."
)
LOCAL_SYSTEM_PROMPT = " ".join(SYSTEM_PROMPT.split())
FINAL_INSTRUCTION = ("Using the retrieved evidence above, output exactly one uppercase label: P or N "
                     "for the same reaction conditions. Do not provide an explanation.")
DEFAULT_FT = "ft:gpt-4.1-2025-04-14:deep-synthesis-lab:mofinder-re:EQdimPJB"
ARMS = {
    "gpt41_ft": (DEFAULT_FT, "chat"),
    "gpt41mini": ("gpt-4.1-mini", "chat"),
    "gpt41mini_web": ("gpt-4.1-mini", "web_evidence_then_label_v1"),
    "gpt41": ("gpt-4.1", "chat"),
    "gpt41_web": ("gpt-4.1", "web_evidence_then_label_v1"),
    "gpt4o": ("gpt-4o", "chat"),
    "gpt4o_web": ("gpt-4o", "web_evidence_then_label_v1"),
    "gpt5_high": ("gpt-5", "high_reasoning"),
    "gpt6astra_high": ("gpt-6-astra", "high_reasoning"),
    "local_ft": ("StarLiu714/GPT-oss-MOF", "local_raw_pn"),
}
LOCAL_LABEL_IDS = {"N": 45, "P": 47}
LOCAL_N_PROBS = (100, 1000, 201088)
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def redact(text, secret=""):
    if secret:
        text = text.replace(secret, "[REDACTED]")
        text = text.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", text)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def conditions_json(question):
    # Neither the reference label nor question metadata enters the prompt.
    return json_text({key: question["conditions"][key] for key in FIELDS})


def load_questions(path):
    rows = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list) or len(rows) != 22:
        raise ValueError("The benchmark requires exactly 22 question records.")
    if [row.get("question") for row in rows] != [f"Q{i}" for i in range(1, 23)]:
        raise ValueError("Question IDs must be unique and ordered Q1 through Q22.")
    for row in rows:
        if set(row.get("conditions", {})) != set(FIELDS) or row.get("label") not in ("P", "N"):
            raise ValueError("Each question requires the eight native fields and a P/N reference label.")
        conditions_json(row)  # Reject nonfinite values without changing types.
    return rows


def chat_payload(model, user_json):
    return {"model": model, "messages": [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_json}], "temperature": 0, "top_p": 1,
            "max_tokens": 2, "logprobs": True, "top_logprobs": 5, "seed": 7, "store": False}


def responses_payload(model, user_json, web=False):
    payload = {"model": model, "input": SYSTEM_PROMPT.strip() + "\n\nReaction conditions as JSON:\n" + user_json,
               "store": False}
    if web:
        payload.update(tools=[{"type": "web_search"}], tool_choice="required")
    else:
        payload["reasoning"] = {"effort": "high"}
    return payload


def response_headers(headers):
    # Never retain Authorization, cookies, organization/project IDs or all headers.
    return {str(key).lower(): str(value) for key, value in headers.items()
            if str(key).lower().startswith("x-ratelimit-") or str(key).lower() in
            {"retry-after", "retry-after-ms", "x-request-id", "openai-processing-ms"}}


def usage_counts(raw):
    usage = raw.get("usage") or {}
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    return {"input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
            "cached_input_tokens": input_details.get("cached_tokens"),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
            "reasoning_tokens": output_details.get("reasoning_tokens")}


def response_text(raw, endpoint):
    if endpoint == "chat.completions":
        choices = raw.get("choices") or []
        return choices[0].get("message", {}).get("content") if choices else None
    return "".join(part.get("text", "") for item in raw.get("output", [])
                   if item.get("type") == "message" for part in item.get("content", [])
                   if part.get("type") == "output_text")


def strict_label(text):
    return text.strip() if isinstance(text, str) and text.strip() in ("P", "N") else None


def retry_delay(headers, attempt):
    delay = 2 ** attempt
    for name, divisor in (("retry-after-ms", 1000), ("retry-after", 1)):
        try:
            value = float(headers.get(name, "")) / divisor
            if math.isfinite(value) and value >= 0:
                return min(300.0, max(delay, value))
        except (TypeError, ValueError):
            pass
    return float(delay)


async def hosted_call(client, endpoint, payload, attempts, secret):
    """Capture SDK raw-response headers; SDK retries are disabled by the caller."""
    stage = {"endpoint": endpoint, "request": payload, "attempts": [], "response": None}
    start = time.perf_counter()
    for index in range(1, attempts + 1):
        tick = time.perf_counter()
        item = {"attempt": index, "started_utc": utc_now()}
        try:
            resource = client.responses if endpoint == "responses" else client.chat.completions
            raw = await resource.with_raw_response.create(**payload)
            item.update(http_status=raw.status_code, headers=response_headers(raw.headers))
            response = raw.parse()
            if inspect.isawaitable(response):
                response = await response
            data = response.model_dump(mode="json")
            item.update(status="success", elapsed_seconds=time.perf_counter() - tick)
            stage["attempts"].append(item)
            stage.update(response=data, usage=usage_counts(data), actual_model=data.get("model"))
            break
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            error_response = getattr(exc, "response", None)
            headers = response_headers(getattr(error_response, "headers", {}))
            message = redact(str(exc), secret)[:4000]
            item.update(status="error", http_status=status, headers=headers, error_type=type(exc).__name__,
                        error=message, elapsed_seconds=time.perf_counter() - tick)
            stage["attempts"].append(item)
            transient = status in (408, 409, 429) or (isinstance(status, int) and status >= 500) or type(exc).__name__ in ("APIConnectionError", "APITimeoutError")
            if not transient or index == attempts or "insufficient_quota" in message:
                break
            item["backoff_seconds"] = retry_delay(headers, index)
            await asyncio.sleep(item["backoff_seconds"])
    stage["elapsed_seconds"] = time.perf_counter() - start
    return stage


def local_prompt(user_json, current_date):
    date.fromisoformat(current_date)
    return ("<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.\n"
            "Knowledge cutoff: 2024-06\n" + f"Current date: {current_date}\n\nReasoning: medium\n\n"
            "# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>"
            "<|start|>developer<|message|># Instructions\n\n" + LOCAL_SYSTEM_PROMPT +
            "\n\n<|end|><|start|>user<|message|>" + user_json +
            "<|end|><|start|>assistant<|channel|>final<|message|>")


def local_scores(raw):
    if raw.get("truncated") or raw.get("generation_settings", {}).get("post_sampling_probs"):
        raise ValueError("Truncated prompts or post-sampling probabilities cannot be scored.")
    groups = raw.get("completion_probabilities", raw.get("probs"))
    if not isinstance(groups, list) or len(groups) != 1 or not isinstance(groups[0].get("top_logprobs"), list):
        raise ValueError("Local server must return one token's raw top_logprobs.")
    found = {}
    by_id = {number: label for label, number in LOCAL_LABEL_IDS.items()}
    for entry in groups[0]["top_logprobs"]:
        label = by_id.get(entry["id"]) if "id" in entry else entry.get("token")
        if label not in LOCAL_LABEL_IDS:
            continue
        value = entry.get("logprob")
        if type(value) not in (int, float) or not math.isfinite(value) or not -3e38 < value <= 1e-5 or label in found:
            raise ValueError("Invalid, duplicate or underflowed local label logprob.")
        found[label] = value
    return found if len(found) == 2 else None


async def local_call(client, endpoint, payload=None):
    tick = time.perf_counter()
    item = {"attempt": 1, "started_utc": utc_now()}
    stage = {"endpoint": endpoint, "request": payload, "attempts": [item], "response": None}
    try:
        response = await (client.get(endpoint) if payload is None else client.post(endpoint, json=payload))
        item.update(http_status=response.status_code, headers=response_headers(response.headers))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or "error" in data:
            raise ValueError("Local endpoint returned an error or non-object response.")
        stage["response"] = data
        item["status"] = "success"
    except Exception as exc:
        item.update(status="error", error_type=type(exc).__name__, error=redact(str(exc))[:4000])
    item["elapsed_seconds"] = stage["elapsed_seconds"] = time.perf_counter() - tick
    return stage


async def local_prediction(client, user_json, args):
    stages = [await local_call(client, "/tokenize", {"content": local_prompt(user_json, args.local_date),
                                                    "add_special": False, "parse_special": True})]
    tokens = (stages[-1]["response"] or {}).get("tokens")
    if not isinstance(tokens, list) or not tokens or any(type(token) is not int for token in tokens):
        return stages, None, "invalid_tokenization", None
    if len(tokens) > args.local_context:
        return stages, None, "prompt_too_long", None
    for n_probs in LOCAL_N_PROBS:
        payload = {"prompt": tokens, "n_predict": 1, "stream": False, "seed": 42, "temperature": 1.0,
                   "top_k": 0, "top_p": 1.0, "min_p": 0.0, "repeat_penalty": 1.0,
                   "presence_penalty": 0.0, "frequency_penalty": 0.0, "n_probs": n_probs,
                   "post_sampling_probs": False, "backend_sampling": False,
                   "cache_prompt": True, "return_tokens": True}
        stage = await local_call(client, "/completion", payload)
        stages.append(stage)
        if stage["response"] is None:
            return stages, None, "request_error", None
        try:
            scores = local_scores(stage["response"])
        except ValueError as exc:
            stage["validation_error"] = str(exc)
            return stages, None, "invalid_raw_logprobs", None
        if scores is not None:
            delta = scores["P"] - scores["N"]
            probability = 1 / (1 + math.exp(-delta)) if delta >= 0 else math.exp(delta) / (1 + math.exp(delta))
            return stages, "P" if probability >= 0.5 else "N", "complete", {
                "logprob_P": scores["P"], "logprob_N": scores["N"], "probability_P": probability,
                "prompt_tokens": len(tokens), "n_probs": n_probs}
    return stages, None, "missing_label_logprobs", None


async def predict(client, arm, model, question, args, secret):
    user_json = conditions_json(question)
    mode = ARMS[arm][1]
    stages, label, status, answer, extra = [], None, "request_error", None, None
    if mode == "local_raw_pn":
        stages, label, status, extra = await local_prediction(client, user_json, args)
    else:
        web = mode == "web_evidence_then_label_v1"
        endpoint = "chat.completions" if mode == "chat" else "responses"
        payload = chat_payload(model, user_json) if mode == "chat" else responses_payload(model, user_json, web)
        stages.append(await hosted_call(client, endpoint, payload, args.attempts, secret))
        raw = stages[-1]["response"]
        if raw is not None:
            status = "complete"
            if endpoint == "responses" and raw.get("status") != "completed":
                status = "incomplete_response"
            if web and status == "complete":
                searches = [item for item in raw.get("output", []) if item.get("type") == "web_search_call"]
                extra = {"web_search_calls": len(searches), "completed_web_search_calls": sum(item.get("status") == "completed" for item in searches)}
                evidence = response_text(raw, "responses")
                if not extra["completed_web_search_calls"] or not evidence:
                    status = "invalid_web_retrieval"
                else:
                    verdict = chat_payload(model, user_json)
                    verdict["messages"].extend([{"role": "assistant", "content": evidence},
                                                {"role": "user", "content": FINAL_INSTRUCTION}])
                    stages.append(await hosted_call(client, "chat.completions", verdict, args.attempts, secret))
                    raw, endpoint = stages[-1]["response"], "chat.completions"
                    if raw is None:
                        status = "request_error"
            if status == "complete":
                answer = response_text(raw, endpoint)
                label = strict_label(answer)
                if label is None:
                    status = "invalid_label"
    return {"status": status, "response_complete": status in ("complete", "invalid_label"),
            "answer": answer, "label": label, "correct": label == question["label"],
            "stages": stages, "extra": extra}


def describe(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "sample_sd": statistics.stdev(values) if len(values) > 1 else None, "sd_ddof": 1}


def summarize(events):
    manifests = [event for event in events if event.get("event") == "manifest"]
    if len(manifests) != 1:
        raise ValueError("Expected one benchmark manifest in the event log.")
    manifest = manifests[0]
    result = {"schema_version": 1, "protocol": manifest, "arms": {}}
    for arm in manifest["arms"]:
        panels = [event for event in events if event.get("event") == "panel" and event["arm"] == arm]
        records = [event for event in events if event.get("event") == "reaction" and event["arm"] == arm]
        complete = [panel for panel in panels if panel["status"] == "complete"]
        walls = [panel["wall_seconds"] for panel in complete]
        stages = [stage for record in records for stage in record.get("stages", [])]
        attempts = [attempt for stage in stages for attempt in stage["attempts"]]
        usage = {field: {"sum_reported": sum(stage.get("usage", {}).get(field) or 0 for stage in stages),
                         "responses_reporting": sum(stage.get("usage", {}).get(field) is not None for stage in stages)} for field in USAGE_FIELDS}
        entry = {"requested_model": manifest["arms"][arm]["model"], "mode": manifest["arms"][arm]["mode"],
                 "complete_panels": len(complete), "requested_panels": manifest["repeats"],
                 "panel_wall_seconds": describe(walls),
                 "reaction_latency_panel_mean_seconds": describe([panel["reaction_latency_mean_seconds"] for panel in complete]),
                 "http_attempt_latency_panel_mean_seconds": describe([panel["http_attempt_latency_mean_seconds"] for panel in complete]),
                 "amortized_panel_wall_per_reaction_seconds": describe([value / 22 for value in walls]),
                 "reaction_status_counts": dict(Counter(record["status"] for record in records)),
                 "strict_valid_labels": sum(record.get("label") in ("P", "N") for record in records),
                 "invalid_labels": sum(record["status"] == "invalid_label" for record in records),
                 "correct_labels": sum(record.get("correct") is True for record in records),
                 "api_or_local_http_attempts": len(attempts),
                 "failed_http_attempts": sum(item["status"] == "error" for item in attempts),
                 "retries": sum(max(0, len(stage["attempts"]) - 1) for stage in stages),
                 "actual_model_ids": dict(Counter(stage["actual_model"] for stage in stages if stage.get("actual_model"))),
                 "usage": usage, "panels": panels,
                 "serial_million_evaluations_estimate": None}
        if walls and manifest["concurrency"] == 1:
            seconds = statistics.mean(walls) / 22 * 1_000_000
            entry["serial_million_evaluations_estimate"] = {
                "seconds": seconds, "hours": seconds / 3600, "days": seconds / 86400,
                "basis": "Mean complete serial panel wall/22; same workload/cache/reset pattern assumed. Not measured; invalid final labels, if any, still count as evaluations."}
        elif manifest["concurrency"] != 1:
            entry["serial_projection_unavailable_reason"] = "Parallel wall/22 is amortized wall time, not request latency or a serial-runtime estimate."
        result["arms"][arm] = entry
    return result


class EventLog:
    def __init__(self, directory, secret):
        self.directory, self.secret, self.events = directory, secret, []
        self.handle = (directory / "events.jsonl").open("x", encoding="utf-8", newline="\n")

    def write(self, event):
        # Serialize once, redact credentials even from unexpected provider errors,
        # and retain exactly the same records in memory as on disk.
        encoded = redact(json_text(event), self.secret)
        self.handle.write(encoded + "\n")
        self.handle.flush()
        self.events.append(json.loads(encoded))

    def save_summary(self):
        path = self.directory / "summary.json"
        staging = path.with_suffix(".json.tmp")
        staging.write_text(json.dumps(summarize(self.events), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staging.replace(path)


async def run_panel(client, arm, model, questions, repeat, args, secret, log):
    limit = asyncio.Semaphore(min(args.concurrency, len(questions)))
    stop = asyncio.Event()
    panel_start = time.perf_counter()
    started_utc = utc_now()

    async def worker(question):
        async with limit:
            tick = time.perf_counter()
            record = {"event": "reaction", "arm": arm, "repeat": repeat, "question": question["question"],
                      "conditions": question["conditions"], "input_json": conditions_json(question),
                      "gold": question["label"], "queue_wait_seconds": tick - panel_start,
                      "started_utc": utc_now()}
            if stop.is_set():
                record.update(status="not_attempted_after_access_error", response_complete=False,
                              label=None, correct=False, stages=[])
            else:
                try:
                    record.update(await predict(client, arm, model, question, args, secret))
                except Exception as exc:
                    record.update(status="validation_error", response_complete=False, label=None,
                                  correct=False, stages=[], error=redact(str(exc), secret)[:4000])
                if any(item.get("http_status") in (401, 403, 404) for stage in record["stages"] for item in stage["attempts"]):
                    stop.set()
            record["latency_seconds"] = time.perf_counter() - tick
            record["ended_utc"] = utc_now()
            log.write(record)
            return record

    records = await asyncio.gather(*(worker(question) for question in questions))
    wall = time.perf_counter() - panel_start
    attempt_times = [item["elapsed_seconds"] for record in records for stage in record["stages"] for item in stage["attempts"]]
    panel = {"event": "panel", "arm": arm, "repeat": repeat, "started_utc": started_utc, "ended_utc": utc_now(),
             "question_count": 22, "completed_evaluations": sum(row["response_complete"] for row in records),
             "valid_labels": sum(row["label"] in ("P", "N") for row in records),
             "status": "complete" if all(row["response_complete"] for row in records) else "incomplete",
             "wall_seconds": wall, "reaction_latency_mean_seconds": statistics.mean(row["latency_seconds"] for row in records),
             "http_attempt_latency_mean_seconds": statistics.mean(attempt_times) if attempt_times else None}
    log.write(panel)
    log.save_summary()
    print(f"{arm}: panel {repeat}/{args.repeats}, {panel['completed_evaluations']}/22 completed, "
          f"{panel['valid_labels']}/22 strict labels, wall {wall:.3f} s", flush=True)
    return panel


async def local_preflight(client, args, log):
    props_stage = await local_call(client, "/props")
    log.write({"event": "local_preflight", "timed": False, "stage": props_stage})
    if props_stage["response"] is None:
        raise ValueError("Local /props preflight failed; see events.jsonl.")
    if args.local_model_file:
        path = args.local_model_file.resolve(strict=True)
        props = props_stage["response"]
        server_model = props.get("model_path") or props.get("default_generation_settings", {}).get("model")
        if not server_model or not Path(server_model).resolve().samefile(path):
            raise ValueError("--local-model-file does not match the server-reported loaded path.")
        log.write({"event": "local_model_file", "timed": False, "file_bytes": path.stat().st_size,
                   "sha256": sha256_file(path), "model_identity": "User-supplied file; no automatic checkpoint substitution."})
    for label, token in LOCAL_LABEL_IDS.items():
        stage = await local_call(client, "/tokenize", {"content": label, "add_special": False, "parse_special": True})
        log.write({"event": "local_preflight", "timed": False, "label": label, "stage": stage})
        if (stage["response"] or {}).get("tokens") != [token]:
            raise ValueError(f"Local tokenizer does not match the release's {label} token ID.")


async def run_benchmark(args, questions, selected, secret, log):
    # Lazy dependency imports ensure every offline command works without the SDK.
    import httpx
    hosted = None
    local = None
    try:
        if any(arm != "local_ft" for arm in selected):
            from openai import AsyncOpenAI
            hosted = AsyncOpenAI(api_key=secret, base_url="https://api.openai.com/v1", max_retries=0,
                                 timeout=httpx.Timeout(args.timeout, connect=min(30, args.timeout)))
        if "local_ft" in selected:
            local = httpx.AsyncClient(base_url=args.local_url, timeout=args.timeout, trust_env=False)
            await local_preflight(local, args, log)
        for arm in selected:
            model = args.ft_model if arm == "gpt41_ft" else ARMS[arm][0]
            client = local if arm == "local_ft" else hosted
            for repeat in range(1, args.repeats + 1):
                panel = await run_panel(client, arm, model, questions, repeat, args, secret, log)
                if panel["status"] != "complete":
                    log.write({"event": "arm_stopped", "arm": arm, "reason": "Incomplete panel; subsequent repeats were not requested."})
                    break
    finally:
        if hosted is not None:
            await hosted.close()
        if local is not None:
            await local.aclose()


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = result.add_mutually_exclusive_group()
    action.add_argument("--run", action="store_true", help="Explicitly authorize this manual benchmark's API/local requests.")
    action.add_argument("--list-models", action="store_true", help="List configuration IDs; no credentials or network.")
    action.add_argument("--analyze", type=Path, metavar="EVENTS_JSONL", help="Recompute summary from saved events; no network.")
    result.add_argument("--arms", nargs="+", choices=tuple(ARMS), help="Default: all nine hosted arms; adds local_ft when --local-url is supplied.")
    result.add_argument("--data", type=Path,
                        default=Path(__file__).resolve().parents[3] / "benchmarks" / "mof_quest" / "questions.json",
                        help="Repository 22-question dataset; provide a path if installed outside the source checkout.")
    result.add_argument("--output", type=Path, help="New output directory (must not already exist).")
    result.add_argument("--repeats", type=int, default=5)
    result.add_argument("--concurrency", type=int, default=1, help="Requested in-flight pipelines (default 1); a 22-question panel can exercise at most 22.")
    result.add_argument("--attempts", type=int, default=3, help="Maximum HTTP attempts per hosted stage; SDK retries disabled.")
    result.add_argument("--timeout", type=float, default=1200, help="Timeout seconds per HTTP attempt.")
    result.add_argument("--ft-model", default=DEFAULT_FT, help="Exact fine-tuned model ID accessible to your API account.")
    result.add_argument("--local-url", help="Already-running local llama.cpp HTTP server; loopback only.")
    result.add_argument("--local-model-file", type=Path, help="Optional loaded GGUF to verify and hash outside timing.")
    result.add_argument("--local-date", default="2026-09-26", help="Pinned release prompt date; explicitly recorded.")
    result.add_argument("--local-context", type=int, default=2048)
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.list_models:
        print(json.dumps({arm: {"model": model, "mode": mode} for arm, (model, mode) in ARMS.items()}, indent=2))
        return 0
    if args.analyze:
        events = [json.loads(line) for line in args.analyze.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        print(json.dumps(summarize(events), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if not args.run:
        cli.print_help()
        return 0
    if not (args.repeats > 0 and args.concurrency > 0 and 1 <= args.attempts <= 10 and math.isfinite(args.timeout) and args.timeout > 0 and args.local_context > 0):
        cli.error("Require positive repeats/concurrency, attempts 1..10, and positive finite timeout/context.")
    selected = args.arms or [arm for arm in ARMS if arm != "local_ft"] + (["local_ft"] if args.local_url else [])
    if len(set(selected)) != len(selected):
        cli.error("Duplicate arms are not allowed.")
    if "local_ft" in selected:
        parsed = urlparse(args.local_url or "")
        if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            cli.error("local_ft requires a credential-free loopback HTTP --local-url.")
        date.fromisoformat(args.local_date)
    questions = load_questions(args.data)
    directory = args.output or Path.cwd() / ("inference_timing_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if directory.exists():
        cli.error("Output directory already exists; choose a new directory to preserve prior runs.")
    planned_hosted_calls = 22 * args.repeats * sum(2 if ARMS[arm][1] == "web_evidence_then_label_v1" else 1
                                                  for arm in selected if arm != "local_ft")
    print(f"Manual benchmark: {len(selected)} arms, {args.repeats} panels/arm, "
          f"{planned_hosted_calls} planned hosted calls before retries; concurrency requested "
          f"{args.concurrency}, 22-question ceiling {min(args.concurrency, 22)}.", flush=True)
    secret = ""
    if any(arm != "local_ft" for arm in selected):
        secret = os.environ.get("OPENAI_API_KEY", "").strip()
        if not secret:
            # Refuse getpass's echoing fallback, including in unattended CI.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                secret = getpass.getpass("OpenAI API key (hidden): ").strip()
        if not secret:
            raise ValueError("An API credential is required for hosted arms.")
    directory.mkdir(parents=True, exist_ok=False)
    log = EventLog(directory, secret)
    manifest = {"event": "manifest", "schema_version": 1, "started_utc": utc_now(),
                "question_count": 22, "repeats": args.repeats, "concurrency": args.concurrency,
                "effective_concurrency_ceiling": min(args.concurrency, 22),
                "concurrency_note": "A panel has only 22 evaluations; larger requested concurrency does not benchmark a larger sustained workload.",
                "arms_run_concurrently": False, "maximum_hosted_attempts": args.attempts,
                "planned_hosted_calls_before_retries": planned_hosted_calls,
                "sdk_retries": 0, "retry_backoff_cap_seconds": 300, "timeout_seconds": args.timeout,
                "arms": {arm: {"model": args.ft_model if arm == "gpt41_ft" else ARMS[arm][0], "mode": ARMS[arm][1]} for arm in selected},
                "dataset_sha256": sha256_file(args.data), "script_sha256": sha256_file(__file__),
                "fields": list(FIELDS), "system_prompt": SYSTEM_PROMPT, "web_verdict_instruction": FINAL_INSTRUCTION,
                "gold_labels_sent_to_model": False, "sdk_version": None,
                "client": {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor()},
                "hosted_resource_note": "Provider hardware and caching are not controlled; no inference GPU/memory is inferred from the client.",
                "timing_note": "Panel wall includes queueing, all requests/retries/backoff and per-reaction event serialization; panel/summary writes occur afterward. Reaction latency starts after semaphore acquisition, includes its required stages, and excludes its final event write. HTTP attempt latency is separately recorded. Complete-panel statistics include invalid-label responses; correctness/format are reported separately. SD is across panel totals or panel means, not pooled individual calls.",
                "local_protocol": {"enabled": "local_ft" in selected, "prompt_date": args.local_date,
                    "label_token_ids": LOCAL_LABEL_IDS, "context_limit": args.local_context,
                    "cache_prompt": True, "n_probs_schedule": list(LOCAL_N_PROBS),
                    "server_restart_or_cache_clear": False, "system_prompt": LOCAL_SYSTEM_PROMPT,
                    "model_file_verification_requested": bool(args.local_model_file),
                    "note": "Existing server; local preflight/hash excluded. Tokenization/scoring timed. No checkpoint identity guarantee without the user-supplied GGUF; hash records identity but does not certify its publisher."}}
    try:
        try:
            manifest["sdk_version"] = importlib.metadata.version("openai")
        except importlib.metadata.PackageNotFoundError:
            pass
        log.write(manifest)
        asyncio.run(run_benchmark(args, questions, selected, secret, log))
        log.write({"event": "finished", "ended_utc": utc_now()})
        log.save_summary()
    except BaseException as exc:
        log.write({"event": "interrupted" if isinstance(exc, KeyboardInterrupt) else "fatal_error",
                   "ended_utc": utc_now(), "error_type": type(exc).__name__, "error": redact(str(exc), secret)[:4000]})
        log.save_summary()
        print(redact(f"Benchmark stopped: {type(exc).__name__}: {exc}", secret), file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        log.handle.close()
    print(f"Saved credential-free events and summary to {directory}")
    return 0 if all(arm["complete_panels"] == args.repeats for arm in summarize(log.events)["arms"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
