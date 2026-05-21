"""Score synthesis-screening conditions from screening_conditions.csv (step 6c).

The input CSV is read as cp1252 to preserve the literal chemical symbols
(·, °, etc.) used in the prep tables; the `experimental` column is the
ground-truth P/N outcome.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import (  # noqa: E402
    ensure_api_key,
    evaluate_screening_dataframe,
    load_screening_csv,
    run_async,
)

MODEL_ID = "ft:gpt-4.1-2025-04-14:deep-synthesis-lab:cls-full:Dhhxwa0M"
IN_CSV = Path("out/screening_conditions.csv")
OUT_CSV = Path("out/screening_conditions_with_preds.csv")


def main() -> None:
    ensure_api_key()
    df = load_screening_csv(IN_CSV)
    if df.empty:
        print("No rows in screening_conditions.csv.")
        return
    run_async(evaluate_screening_dataframe(
        model_id=MODEL_ID,
        df=df,
        out_csv=OUT_CSV,
        label_pair=("P", "N"),
    ))


if __name__ == "__main__":
    main()
