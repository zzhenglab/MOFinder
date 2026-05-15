from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Column names (must match the input Excel exactly)
# ---------------------------------------------------------------------------
COL_DOI           = "DOI"
COL_ARTICLE_TITLE = "Article Title"
COL_SOURCE_TITLE  = "Source Title"
COL_AUTHOR_KEYW   = "Author Keywords"
COL_KEYWORDS_PLUS = "Keywords Plus"
COL_ABSTRACT      = "Abstract"

REQUIRED_INPUT_COLS = [
    COL_DOI, COL_ARTICLE_TITLE, COL_SOURCE_TITLE,
    COL_AUTHOR_KEYW, COL_KEYWORDS_PLUS, COL_ABSTRACT,
]

COL_AGENT_ANSWER = "Agent_YN"   # written to output: 'Y' / 'N' / empty


# ---------------------------------------------------------------------------
# RunConfig — one object captures every dial for a single classification run
# ---------------------------------------------------------------------------
@dataclass
class RunConfig:
    # --- input/output ---
    input_name: str = "Full"
    # input_xlsx  → derived property
    # output_xlsx → derived property

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
    debug_per_row: bool = True

    # ---- derived helpers ----

    @property
    def input_xlsx(self) -> str:
        return self.input_name + ".xlsx"

    @property
    def output_xlsx(self) -> str:
        if self.reasoning_effort is not None:
            return f"{self.input_name}_{self.model_name}_{self.reasoning_effort}.xlsx"
        return f"{self.input_name}_{self.model_name}.xlsx"

    def is_reasoning_model(self) -> bool:
        """True when the model uses the reasoning API path (gpt-5 family + effort set)."""
        return self.model_name.startswith("gpt-5") and self.reasoning_effort is not None
