"""Extract misclassified rows from an eval CSV and dump them as a new JSONL
training set (the "H" / hard set used to train cls-ABH, cls-FGH).

The eval CSV is the output of `run_pn_a_on_b.py` (or any of the other
`run_pn_*` scripts).
"""

import json
import sys
from pathlib import Path

import pandas as pd

CSV_PATH = Path("out/mof_cls_B_holdout_eval_train_A.csv")
JSONL_OUT = Path("out/mof_cls_train_H_from_B.jsonl")


def extract_misclassified(csv_path: Path, jsonl_out: Path) -> int:
    df = pd.read_csv(csv_path)
    miscls = df[df["gold_label"] != df["pred_label"]].copy()
    miscls["system_text"] = miscls["system_text"].fillna("")
    miscls["user_text"] = miscls["user_text"].fillna("")
    miscls["gold_label"] = miscls["gold_label"].astype(str)

    jsonl_out.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl_out, "w", encoding="utf-8") as f:
        for _, row in miscls.iterrows():
            record = {
                "messages": [
                    {"role": "system", "content": row["system_text"]},
                    {"role": "user", "content": row["user_text"]},
                    {"role": "assistant", "content": row["gold_label"]},
                ]
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(miscls)


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    jsonl_out = Path(sys.argv[2]) if len(sys.argv) > 2 else JSONL_OUT
    n = extract_misclassified(csv_path, jsonl_out)
    print(f"Number of misclassified examples (size of H): {n}")
    print(f"Wrote JSONL to: {jsonl_out}")


if __name__ == "__main__":
    main()
