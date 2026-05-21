"""20-question OOD probe (step 6b).

Runs the manually curated set in `manual_questions.py` against one or more
classifiers, for `ROUNDS` rounds each. Produces one CSV per (model, round)
plus mean/std metrics across rounds. Supports both the chat.completions path
(returns logprobs) and the Responses API path for gpt-5* models.

Edit `MODELS`, `ROUNDS`, and `REASONING_EFFORT` below to suit the run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import ensure_api_key, evaluate_manual_questions, run_async  # noqa: E402
from manual_questions import MANUAL_QUESTIONS  # noqa: E402

OUT_DIR = Path("out")
BASE_CSV_NAME = "mof_manual_eval"
ROUNDS = 20
REASONING_EFFORT = None  # set to "low" / "medium" / "high" for gpt-5* models
USE_WEB_SEARCH = False

MODELS = [
    "ft:gpt-4.1-2025-04-14:deep-synthesis-lab:cls-full:Dhhxwa0M",  # Our primary model
    # "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-full:CUx5cx8y",
    # "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-ablation:Cgcag41g",
    # "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-a:ChKaeWqB",
    # "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-ab:ChL9CqnE",
    # "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-abc:ChQTMt4w",
    # "gpt-4.1",
    # "gpt-4.1-mini",
    # "gpt-5.1",         # requires REASONING_EFFORT
    # "gpt-5-pro",       # requires REASONING_EFFORT
]


def main() -> None:
    ensure_api_key()
    run_async(evaluate_manual_questions(
        manual_questions=MANUAL_QUESTIONS,
        model_ids=MODELS,
        rounds=ROUNDS,
        out_dir=OUT_DIR,
        base_csv_name=BASE_CSV_NAME,
        reasoning_effort=REASONING_EFFORT,
        use_web_search=USE_WEB_SEARCH,
    ))


if __name__ == "__main__":
    main()
