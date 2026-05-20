"""Evaluate the positive/unlabeled (P/U) fine-tuned classifier.

The label set here is {P, U} rather than {P, N}: this is the PU-learning
control compared against the PN classifier (see README "Method Notes" — PU
treats negative-mined examples as Unlabeled rather than as confirmed
negatives).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import ensure_api_key, evaluate_holdout, run_async  # noqa: E402

MODEL_ID = "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:pu-full:CUymWaTf"
REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_PATH = REPO_ROOT / "data" / "mof_cls_holdout.jsonl"
CSV_PATH = Path("out/mof_pu_holdout_eval.csv")
GOLD_LABEL_MAP = {"N": "U"}


def main() -> None:
    ensure_api_key()
    run_async(evaluate_holdout(
        model_id=MODEL_ID,
        holdout_paths=HOLDOUT_PATH,
        csv_path=CSV_PATH,
        label_pair=("P", "U"),
        gold_label_map=GOLD_LABEL_MAP,
    ))


if __name__ == "__main__":
    main()
