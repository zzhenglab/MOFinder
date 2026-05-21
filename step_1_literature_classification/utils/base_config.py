from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def base_model_name(model_name: str) -> str:
    """Return the underlying model name from plain or fine-tuned model IDs."""
    model = (model_name or "").strip().lower()
    if model.startswith("ft:"):
        parts = model.split(":")
        if len(parts) > 1 and parts[1]:
            return parts[1]
    return model


def is_gpt5_family(model_name: str) -> bool:
    return base_model_name(model_name).startswith("gpt-5")


def supports_none_effort(model_name: str) -> bool:
    model = base_model_name(model_name)
    return model.startswith(("gpt-5.1", "gpt-5.2", "gpt-5.3", "gpt-5.4", "gpt-5.5"))


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
    #   "low"/"medium"/"high" (and "none" only for models that support it)
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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Fail fast for model/effort combinations known to be unsupported."""
        effort = (self.reasoning_effort or "").lower()
        if (
            is_gpt5_family(self.model_name)
            and not supports_none_effort(self.model_name)
            and effort == "none"
        ):
            raise ValueError(
                "--effort none is not supported for gpt-5 models before gpt-5.1; "
                "omit --effort for chat models, use low/medium/high for gpt-5, "
                "or switch to gpt-5.1+ if you need effort none."
            )

    def is_reasoning_model(self) -> bool:
        """True when the model uses the reasoning API path (gpt-5 family + effort set)."""
        return is_gpt5_family(self.model_name) and self.reasoning_effort is not None
