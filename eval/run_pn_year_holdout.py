"""Score F / FG / FGH classifiers on the year-I (chronologically held-out) set.

The original F_FG_FGH notebook ran every classifier on two holdouts:
    1. out/mof_cls_holdout.jsonl       (cluster-aware split — see run_pn_train_f/fg/fgh.py)
    2. out/mof_cls_holdout_year_I.jsonl (chronological out-of-time split)

This script handles the chronological holdout for all three F-family models.
Comment out any block you do not want to re-run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import ensure_api_key, evaluate_holdout, run_async  # noqa: E402

HOLDOUT_PATH = Path("out/mof_cls_holdout_year_I.jsonl")

MODELS = [
    ("ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-f:CinGCADR",
     Path("out/mof_cls_holdout_year_I_eval_train_F.csv")),
    ("ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-fg:CinrBQsO",
     Path("out/mof_cls_holdout_year_I_eval_train_FG.csv")),
    ("ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-fgh:Ciot1HEa",
     Path("out/mof_cls_holdout_year_I_eval_train_FGH.csv")),
]


def main() -> None:
    ensure_api_key()
    for model_id, csv_path in MODELS:
        print(f"\n##### {model_id} -> {csv_path}\n")
        run_async(evaluate_holdout(
            model_id=model_id,
            holdout_paths=HOLDOUT_PATH,
            csv_path=csv_path,
            label_pair=("P", "N"),
        ))


if __name__ == "__main__":
    main()
