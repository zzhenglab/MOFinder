from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelConfig:
    """
    Model-side dials shared by every Step-1 classifier (1.1, 1.2, ...).

    Step-specific RunConfig dataclasses inherit from this and add their own
    input/output fields and helper properties.
    """

    # --- model ---
    model_name: str = "gpt-4o-mini"

    # reasoning_effort controls two things:
    #   None           → chat-model path  (temperature=0, max_tokens=64)
    #   "none"/"low"/"medium"/"high"
    #                  → reasoning-model path (no temperature, large token budget)
    # For gpt-4o-mini you can pass a string effort to include it in the
    # output filename without switching to the reasoning API path
    # (see is_reasoning_model()).
    reasoning_effort: Optional[str] = None

    # --- reasoning-model settings ---
    reasoning_max_output_tokens: int = 26_000

    # --- chat-model settings ---
    chat_temperature: float = 0.0
    chat_max_output_tokens: int = 64

    # --- runtime ---
    request_timeout_seconds: int = 60
    max_tries: int = 2
    save_every: int = 10

    # --- test mode ---
    test_mode: bool = False
    test_n: int = 5

    # --- debug ---
    debug_one_time_dump: bool = False
    debug_per_item: bool = True

    def is_reasoning_model(self) -> bool:
        """True when the model uses the reasoning API path (gpt-5 family + effort set)."""
        return self.model_name.startswith("gpt-5") and self.reasoning_effort is not None
