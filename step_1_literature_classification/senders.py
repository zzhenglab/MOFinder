from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

from openai import OpenAI

from config import RunConfig
from utils import (
    dump_one_time,
    extract_text_from_output_array,
    summarize_for_debug,
    to_plain,
)


class ModelSender:
    """
    Wraps OpenAI Responses API calls for MOF abstract classification.

    Two API paths — chosen by RunConfig.is_reasoning_model():

      send_reasoning_model()  — gpt-5 / gpt-5.1 with reasoning effort
          Uses `reasoning={"effort": ...}` and a large max_output_tokens budget.
          No temperature parameter (not supported by reasoning models).

      send_chat_model()       — gpt-4o-mini style
          Uses temperature=0 and a small max_output_tokens (64).

    call_with_timeout() dispatches to the right path, wraps the call in a
    thread so a wall-clock timeout can be enforced, and returns 'Y', 'N', or
    '' (skip) after up to cfg.max_tries attempts.
    """

    def __init__(self, cfg: RunConfig, client: Optional[OpenAI] = None):
        self.cfg    = cfg
        self.client = client or OpenAI()
        self._dumped_once = False

    # ------------------------------------------------------------------ #
    # Low-level senders (one per API path)                                 #
    # ------------------------------------------------------------------ #

    def send_reasoning_model(self, messages: list) -> object:
        """Call gpt-5 / gpt-5.1 with reasoning effort and large token budget."""
        return self.client.responses.create(
            model=self.cfg.model_name,
            input=messages,
            reasoning={"effort": self.cfg.reasoning_effort},
            max_output_tokens=self.cfg.reasoning_max_output_tokens,
            store=False,
        )

    def send_chat_model(self, messages: list) -> object:
        """Call gpt-4o-mini style: temperature + small token cap."""
        return self.client.responses.create(
            model=self.cfg.model_name,
            input=messages,
            temperature=self.cfg.chat_temperature,
            max_output_tokens=self.cfg.chat_max_output_tokens,
            store=False,
        )

    # ------------------------------------------------------------------ #
    # Dispatcher                                                           #
    # ------------------------------------------------------------------ #

    def _dispatch(self, messages: list) -> object:
        if self.cfg.is_reasoning_model():
            return self.send_reasoning_model(messages)
        return self.send_chat_model(messages)

    # ------------------------------------------------------------------ #
    # Main public call                                                     #
    # ------------------------------------------------------------------ #

    def call_with_timeout(self, prompt: str, row_idx: int) -> str:
        """
        Send one classification request and return 'Y', 'N', or '' (skip).

        Retries up to cfg.max_tries times on timeout or error.
        Prints debug info (via utils) whenever a response does not yield Y/N.
        """
        cfg = self.cfg
        for attempt in range(1, cfg.max_tries + 1):
            try:
                messages = [{"role": "user", "content": prompt}]
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._dispatch, messages)
                    resp   = future.result(timeout=cfg.request_timeout_seconds)

                if cfg.debug_one_time_dump and not self._dumped_once:
                    dump_one_time(resp)
                    self._dumped_once = True

                text = (getattr(resp, "output_text", "") or "").strip()
                if not text:
                    text = extract_text_from_output_array(to_plain(resp).get("output", []))

                if text:
                    c0 = text[0].upper()
                    if c0 in ("Y", "N"):
                        return c0
                    if cfg.debug_per_row:
                        summarize_for_debug(row_idx, resp, note="(non-Y/N text)")
                    return ""

                if cfg.debug_per_row:
                    summarize_for_debug(row_idx, resp, note="(empty text)")

                status = getattr(resp, "status", None)
                inc    = getattr(resp, "incomplete_details", None)
                reason = ""
                if inc:
                    try:
                        reason = to_plain(inc).get("reason", "")
                    except Exception:
                        reason = str(inc)
                if status == "incomplete" and reason == "max_output_tokens":
                    print(
                        f"[DEBUG row {row_idx}] Ran out of tokens during reasoning "
                        "(increase reasoning_max_output_tokens or reduce effort)."
                    )

                time.sleep(0.3)

            except FuturesTimeout:
                if cfg.debug_per_row:
                    print(f"[DEBUG row {row_idx}] timeout on attempt {attempt}")
            except Exception as e:
                if cfg.debug_per_row:
                    print(f"[DEBUG row {row_idx}] error on attempt {attempt}: {e}")
            time.sleep(0.7)

        return ""
