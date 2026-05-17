from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

from openai import OpenAI

from utils.base_config import ModelConfig
from utils.response_utils import (
    dump_one_time,
    extract_text_from_output_array,
    summarize_for_debug,
    to_plain,
)


class ModelSender:
    """
    Wraps OpenAI Responses API calls for MOF Y/N classification.

    Two API paths — chosen by ``ModelConfig.is_reasoning_model()``:

      send_reasoning_model()  — gpt-5 / gpt-5.1 with reasoning effort
          Uses ``reasoning={"effort": ...}`` and a large max_output_tokens
          budget. No temperature parameter (not supported by reasoning models).

      send_chat_model()       — gpt-4o-mini style
          Uses ``temperature=0`` and a small max_output_tokens (64).

    ``call_with_timeout()`` dispatches to the right path, wraps the call in a
    thread so a wall-clock timeout can be enforced, and returns 'Y', 'N', or
    '' (skip). Non-timeout errors are retried up to ``cfg.max_tries`` times.
    """

    def __init__(self, cfg: ModelConfig, client: Optional[OpenAI] = None):
        cfg.validate()
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
            timeout=self.cfg.request_timeout_seconds,
            store=False,
        )

    def send_chat_model(self, messages: list) -> object:
        """Call gpt-4o-mini style: temperature + small token cap."""
        return self.client.responses.create(
            model=self.cfg.model_name,
            input=messages,
            temperature=self.cfg.chat_temperature,
            max_output_tokens=self.cfg.chat_max_output_tokens,
            timeout=self.cfg.request_timeout_seconds,
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

    def call_with_timeout(self, prompt: str, item_label: Any) -> str:
        """
        Send one classification request and return 'Y', 'N', or '' (skip).

        Only the first character of the model's reply is inspected; the
        prompt may permit an explanation after the letter, which is ignored.
        Retries up to ``cfg.max_tries`` times on timeout or error.
        """
        cfg = self.cfg
        for attempt in range(1, cfg.max_tries + 1):
            try:
                messages = [{"role": "user", "content": prompt}]
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(self._dispatch, messages)
                try:
                    resp = future.result(timeout=cfg.request_timeout_seconds)
                except FuturesTimeout:
                    future.cancel()
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
                except Exception:
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
                else:
                    pool.shutdown(wait=True)

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
                    if cfg.debug_per_item:
                        summarize_for_debug(item_label, resp, note="(non-Y/N text)")
                    return ""

                if cfg.debug_per_item:
                    summarize_for_debug(item_label, resp, note="(empty text)")

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
                        f"[DEBUG item {item_label}] Ran out of tokens during reasoning "
                        "(increase reasoning_max_output_tokens or reduce effort)."
                    )

                time.sleep(0.3)

            except FuturesTimeout:
                if cfg.debug_per_item:
                    print(
                        f"[DEBUG item {item_label}] timeout on attempt {attempt}; "
                        "skipping without retry to avoid duplicate in-flight requests"
                    )
                return ""
            except Exception as e:
                if cfg.debug_per_item:
                    print(f"[DEBUG item {item_label}] error on attempt {attempt}: {e}")
            time.sleep(0.7)

        return ""
