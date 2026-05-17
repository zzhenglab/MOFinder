"""Evaluate the cls-A (smaller train, set A only) PN classifier on the main holdout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import ensure_api_key, evaluate_holdout, run_async  # noqa: E402

MODEL_ID = "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-a:ChKaeWqB"
REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_PATH = REPO_ROOT / "data" / "mof_cls_holdout.jsonl"
CSV_PATH = Path("out/mof_cls_holdout_eval_train_A.csv")


def main() -> None:
    ensure_api_key()
    run_async(evaluate_holdout(
        model_id=MODEL_ID,
        holdout_paths=HOLDOUT_PATH,
        csv_path=CSV_PATH,
        label_pair=("P", "N"),
    ))


if __name__ == "__main__":
    main()
