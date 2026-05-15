from __future__ import annotations

import json
from typing import Any, Tuple


def to_plain(obj: Any) -> Any:
    """Convert a Pydantic/SDK response object to a plain dict."""
    for attr in ("model_dump", "dict", "to_dict"):
        if hasattr(obj, attr) and callable(getattr(obj, attr)):
            try:
                return getattr(obj, attr)()
            except Exception:
                pass
    return obj


def extract_text_from_output_array(out: Any) -> str:
    """Walk the output array of a Responses API reply and return the first text chunk."""
    try:
        if not isinstance(out, list):
            return ""
        for item in out:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                content = item.get("content") or []
                for chunk in content:
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "output_text" and "text" in chunk:
                            t = (chunk.get("text") or "").strip()
                            if t:
                                return t
                        if "text" in chunk:
                            t = (chunk.get("text") or "").strip()
                            if t:
                                return t
        return ""
    except Exception:
        return ""


def usage_tuple(resp_obj: Any) -> Tuple[int, int, int, int]:
    """Return (input_tokens, output_tokens, reasoning_tokens, total_tokens), or zeros."""
    try:
        usage = getattr(resp_obj, "usage", None)
        u = to_plain(usage) if usage else {}
        it = int(u.get("input_tokens", 0) or 0)
        ot = int(u.get("output_tokens", 0) or 0)
        rt = int((u.get("output_tokens_details", {}) or {}).get("reasoning_tokens", 0) or 0)
        tt = int(u.get("total_tokens", 0) or 0)
        return it, ot, rt, tt
    except Exception:
        return (0, 0, 0, 0)


def summarize_for_debug(idx: int, resp_obj: Any, note: str = "") -> None:
    """Print a one-line debug summary for a response that did not yield Y/N."""
    try:
        status = getattr(resp_obj, "status", None)
        inc    = getattr(resp_obj, "incomplete_details", None)
        reason = ""
        if inc:
            try:
                reason = to_plain(inc).get("reason", "")
            except Exception:
                reason = str(inc)
        plain   = to_plain(resp_obj)
        out     = plain.get("output", [])
        types   = [i.get("type") for i in out] if isinstance(out, list) else type(out).__name__
        text    = (getattr(resp_obj, "output_text", "") or "").strip()
        preview = (text[:1] if text else "") or (extract_text_from_output_array(out)[:1] if out else "")
        it, ot, rt, tt = usage_tuple(resp_obj)
        print(
            f"[DEBUG row {idx}] status={status} reason={reason or '-'} "
            f"usage(input={it}, output={ot}, reasoning={rt}, total={tt}) "
            f"types={types} output_text_len={len(text)} preview_char={repr(preview)} {note}".strip()
        )
    except Exception as e:
        print(f"[DEBUG row {idx}] <summarize error: {e}> {note}")


def dump_one_time(resp_obj: Any) -> None:
    """Print raw output array — useful for one-time debugging."""
    plain = to_plain(resp_obj)
    print("=== ONE-TIME RAW OUTPUT DUMP ===")
    try:
        print(json.dumps(plain.get("output", []), ensure_ascii=False, indent=2)[:3000])
    except Exception as e:
        print(f"<json dump err: {e}>")
