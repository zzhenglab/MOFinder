"""
Step 1.3 — Evaluate predictions against ground truth (no LLM calls)
===================================================================
What it does
    Pure-pandas analysis. Joins one or more Step-1.1 prediction files
    (outputs of ``1_1_classify_abstract.py``) with a ground-truth Y/N
    table (typically the output of ``1_2_classify_pdf.py``, or a
    manually-curated file) by DOI, and reports per model:

        accuracy, precision, recall, F1 (for Y, for N, and macro),
        plus the 2x2 confusion matrix.

    Optionally:
      - restricts the comparison to an open-access subset of DOIs
        (used in the paper for the open-source-only comparison);
      - joins each model's labels back into a full metadata table
        (``--full``) and writes a combined workbook;
      - renders one confusion-matrix figure per model (``--plot``).

How rows are joined
    Every input file must contain a DOI column or a filename column.
    DOIs are normalized — lowercased; ``doi.org/`` / ``doi:`` prefixes
    stripped; trailing ``.pdf`` stripped; ``\\`` and ``_`` mapped to ``/``
    — so that ``10.1021/jacs.5b00001``, ``DOI: 10.1021/JACS.5b00001``,
    and ``10.1021_jacs.5b00001.pdf`` all match the same ground-truth row.

Input
    --ground-truth FILE      xlsx with 'File' (or 'DOI') + 'Agent_YN'
                             (typically the output of Step 1.2)
    --predictions NAME=FILE  one or more Step-1.1 outputs; repeat the
                             flag once per model being compared
    --full FILE              optional: Full.xlsx of paper metadata; if
                             given, each model's labels are joined into
                             Full as a new column and saved to --output
    --open-source-file FILE  optional: xlsx whose 'Downloaded' column = 1
                             restricts evaluation to that subset of DOIs

Output
    A printed metrics table per model. With ``--output FILE`` it writes
    a workbook with a ``metrics`` sheet plus, if ``--full`` was given,
    a merged metadata sheet. With ``--plot`` it shows one
    confusion-matrix figure per model.

File layout (numbered sections below)
    1. RunConfig                        4. Open-source subset audit
    2. Normalization (DOI / Y-N)        5. Main analysis
    3. Metrics                          6. CLI

Usage
-----
  python 1_3_evaluate.py [options]

Examples:

  # Default
  #   FULL_FILE        = Full.xlsx
  #   GPT5_FILE        = Full_gpt-5.xlsx
  #   GPT4MINI_FILE    = Full_gpt-4o-mini.xlsx
  #   GT_FILE          = mof_pdf_labels_using gpt5 only YN response 478.xlsx
  #   OPEN_SOURCE_FILE = ground truth open access 500 around 278 download.xlsx
  #   OUTPUT_FILE      = Full_with_gpt5_gpt4omini.xlsx
  #   OPEN_SOURCE_ONLY = True   (open-source filter on)
  #   Plot confusion matrices: on
  python 1_3_evaluate.py

  # 3-model comparison on the 478-test subset:
  python 1_3_evaluate.py \\
      --predictions gpt-5.1-high=Full_478test_only_gpt-5.1_high.xlsx \\
      --predictions gpt-5.1-none=Full_478test_only_gpt-5.1_none.xlsx \\
      --predictions gpt-4o=Full_478test_only_gpt-4o_none.xlsx

  # Drop the open-source filter, suppress plots:
  python 1_3_evaluate.py --open-source-file "" --no-plot

Requirements
------------
  pip install pandas openpyxl matplotlib   # matplotlib only for --plot
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ===========================================================================
# 1. Run configuration
# ===========================================================================
@dataclass
class RunConfig:
    """One object captures every dial for a single analysis run."""
    ground_truth_file: str
    predictions:        Dict[str, str]               # model_name → xlsx path
    full_file:          Optional[str] = None
    output_file:        Optional[str] = None
    open_source_file:   Optional[str] = None
    open_source_sheets: Optional[List[str]] = None
    pred_column:        str = "Agent_YN"
    plot_confusion:     bool = False


# ===========================================================================
# 2. Normalization helpers — DOIs and Y/N labels can be sloppy across files
# ===========================================================================
def normalize_colname(col) -> str:
    """Lowercase, strip spaces and punctuation — for fuzzy column matching."""
    return "".join(ch for ch in str(col).strip().lower() if ch.isalnum())


def norm_doi(s) -> Optional[str]:
    """
    Canonicalize a DOI/URL/file path into a bare DOI string (10.xxxx/yyyy).
    Returns None if no DOI shape is found.
    """
    if pd.isna(s):
        return None
    st = str(s).strip().lower()
    if not st:
        return None
    st = st.replace("\\", "/").replace("_", "/")
    st = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)\s*", "", st)
    st = re.sub(r"\.pdf$", "", st)
    m = re.search(r"(10\.\d{4,9}/\S+)", st)
    return m.group(1) if m else None


def to_yn(val) -> Optional[str]:
    """Map a free-form label (Y/N/yes/no/true/false/1/0) to 'Y', 'N', or None."""
    if pd.isna(val):
        return None
    u = str(val).strip().upper()
    if u in {"Y", "YES", "TRUE", "T", "1"}:
        return "Y"
    if u in {"N", "NO", "FALSE", "F", "0"}:
        return "N"
    return None


def find_doi_column(df: pd.DataFrame) -> str:
    """Pick the DOI/File column from a DataFrame by header name, with fallbacks."""
    if "File" in df.columns:
        return "File"
    for col in df.columns:
        if normalize_colname(col) == "doi":
            return col
    # Heuristic: column with the highest share of DOI-shaped values
    pat = re.compile(r"10\.\d{4,9}/\S+")
    best_col, best_share = None, 0.0
    for c in df.columns:
        share = df[c].astype(str).str.contains(pat).mean()
        if share > best_share:
            best_col, best_share = c, share
    return best_col if best_col is not None else df.columns[0]


# ===========================================================================
# 3. Metrics — Y/N confusion matrix → accuracy, precision, recall, F1
# ===========================================================================
def _safe_div(n: float, d: float) -> float:
    return n / d if d != 0 else 0.0


def compute_metrics(y_true: pd.Series, y_pred: pd.Series) -> Dict[str, float]:
    """
    Confusion-matrix metrics with Y as the positive class, then also with N
    as positive (so we can macro-average over the two classes).

    Invalid or missing predictions count as evaluated errors: a true Y with
    any non-Y prediction is an FN, and a true N with any non-N prediction is
    an FP.
    """
    y_true = y_true.astype(str).str.upper().str.strip()
    y_pred = y_pred.astype(str).str.upper().str.strip()

    TP = int(((y_true == "Y") & (y_pred == "Y")).sum())
    FN = int(((y_true == "Y") & (y_pred != "Y")).sum())
    FP = int(((y_true == "N") & (y_pred != "N")).sum())
    TN = int(((y_true == "N") & (y_pred == "N")).sum())
    n  = TP + TN + FP + FN

    # Y is positive
    prec_Y = _safe_div(TP, TP + FP)
    rec_Y  = _safe_div(TP, TP + FN)
    f1_Y   = _safe_div(2 * prec_Y * rec_Y, prec_Y + rec_Y)

    # N is positive (swap roles)
    prec_N = _safe_div(TN, TN + FN)
    rec_N  = _safe_div(TN, TN + FP)
    f1_N   = _safe_div(2 * prec_N * rec_N, prec_N + rec_N)

    return {
        "n_eval": n,
        "TP": TP, "FP": FP, "TN": TN, "FN": FN,
        "accuracy":     _safe_div(TP + TN, n),
        "precision_Y":  prec_Y, "recall_Y": rec_Y, "f1_Y": f1_Y,
        "precision_N":  prec_N, "recall_N": rec_N, "f1_N": f1_N,
        "macro_precision": (prec_Y + prec_N) / 2.0,
        "macro_recall":    (rec_Y  + rec_N)  / 2.0,
        "macro_f1":        (f1_Y   + f1_N)   / 2.0,
    }


def plot_confusion_matrix(TP: int, FN: int, FP: int, TN: int, model_name: str) -> None:
    """Render a 2x2 confusion matrix for one model. Requires matplotlib."""
    import matplotlib.pyplot as plt
    cm = [[TP, FN], [FP, TN]]
    fig, ax = plt.subplots()
    im = ax.imshow(cm, cmap="Blues")
    ax.set_title(f"Confusion Matrix — {model_name}")
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Y", "N"]); ax.set_yticklabels(["Y", "N"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i][j], ha="center", va="center", fontsize=12)
    fig.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.show()


# ===========================================================================
# 4. Optional open-source subset audit
#    Reads an xlsx whose 'Downloaded' column == 1 marks the open-access papers,
#    and returns the set of DOIs to use as the evaluation subset.
# ===========================================================================
def _find_exact_download_col(cols) -> Optional[str]:
    norm = {normalize_colname(c): c for c in cols}
    for name in ("donwloaded", "downloaded"):   # tolerate the historical typo
        if name in norm:
            return norm[name]
    return None


def _exact_one_mask(series: pd.Series) -> pd.Series:
    """Rows where the value is exactly 1 (as string or numeric)."""
    s   = series.astype(str).str.strip()
    num = pd.to_numeric(s, errors="coerce")
    return s.eq("1") | num.eq(1)


def audit_open_source_file(
    xlsx_path: str,
    sheet_filter: Optional[List[str]] = None,
) -> Tuple[set, int]:
    """
    Read every sheet; collect the DOIs of rows where 'Downloaded' == 1.
    Returns (unique_doi_set, total_rows_flagged).
    """
    book = pd.read_excel(xlsx_path, sheet_name=None, dtype=object)
    doi_set: set = set()
    raw_rows = 0

    print(f"\nOpen-source workbook sheets: {list(book.keys())}")
    for sheet_name, df in book.items():
        if sheet_filter and sheet_name not in sheet_filter:
            continue
        dl_col = _find_exact_download_col(df.columns)
        if dl_col is None:
            print(f"[{sheet_name}] skipped: no 'Downloaded' column")
            continue

        vc = df[dl_col].astype(str).str.strip().value_counts(dropna=False)
        print(f"[{sheet_name}] download column '{dl_col}' value_counts:\n{vc}\n")

        mask  = _exact_one_mask(df[dl_col])
        raw_rows += int(mask.sum())
        doi_col = find_doi_column(df)
        dois = df[doi_col].apply(norm_doi)
        doi_set.update(dois[mask & dois.notna()].tolist())

    print(f"TOTAL rows flagged: {raw_rows}")
    print(f"TOTAL unique DOIs:  {len(doi_set)}")
    return doi_set, raw_rows


# ===========================================================================
# 5. Main analysis
# ===========================================================================
def run(cfg: RunConfig) -> pd.DataFrame:
    """
    Execute one full Step-1.3 analysis run.
    Returns the metrics DataFrame (also saved to ``cfg.output_file`` if given).
    """
    # --- 5a. Ground truth ---
    print(f"Reading ground truth: {cfg.ground_truth_file}")
    gt_df = pd.read_excel(cfg.ground_truth_file, dtype=object)
    if "Agent_YN" not in gt_df.columns:
        raise RuntimeError("Ground-truth file must contain an 'Agent_YN' column.")
    gt_id_col = find_doi_column(gt_df)
    gt_df["doi_norm"]   = gt_df[gt_id_col].apply(norm_doi)
    gt_df["TrueLabel"]  = gt_df["Agent_YN"].apply(to_yn)
    gt_df = gt_df.dropna(subset=["doi_norm", "TrueLabel"])
    print(f"  {len(gt_df)} ground-truth rows after DOI normalization")

    # --- 5b. Optional: restrict to open-source subset ---
    if cfg.open_source_file:
        print(f"\nOpen-source mode ON: {cfg.open_source_file}")
        subset_doi, _ = audit_open_source_file(cfg.open_source_file, cfg.open_source_sheets)
        gt_df = gt_df[gt_df["doi_norm"].isin(subset_doi)].copy()
        print(f"  Ground-truth rows in subset: {len(gt_df)}")

    # --- 5c. Per-model metrics + join into Full ---
    full_df: Optional[pd.DataFrame] = None
    full_id_col: Optional[str] = None
    if cfg.full_file:
        
        print(f"\nReading Full table: {cfg.full_file}")
        full_df = pd.read_excel(cfg.full_file, dtype=object)
        full_id_col = find_doi_column(full_df)
        full_df[full_id_col] = full_df[full_id_col].astype(str).str.strip()
        full_df["_doi_norm"] = full_df[full_id_col].apply(norm_doi)
        gt_map = dict(zip(gt_df["doi_norm"], gt_df["TrueLabel"]))
        full_df["ground_truth"] = full_df["_doi_norm"].map(gt_map)

    metric_rows: List[Dict[str, object]] = []
    for model_name, pred_file in cfg.predictions.items():
        print(f"\n[{model_name}] reading {pred_file}")
        pred_df = pd.read_excel(pred_file, dtype=object)
        pred_id_col = find_doi_column(pred_df)
        if cfg.pred_column not in pred_df.columns:
            print(f"  WARNING: column '{cfg.pred_column}' missing — skipping {model_name}")
            continue
        pred_df["doi_norm"]  = pred_df[pred_id_col].apply(norm_doi)
        pred_df["PredLabel"] = pred_df[cfg.pred_column].apply(to_yn)
        pred_map = dict(
            zip(
                pred_df.dropna(subset=["doi_norm"])["doi_norm"],
                pred_df.dropna(subset=["doi_norm"])["PredLabel"],
            )
        )

        if full_df is not None:
            full_df[model_name] = full_df["_doi_norm"].map(pred_map)

        merged = gt_df.merge(
            pred_df[["doi_norm", "PredLabel"]].dropna(subset=["doi_norm"]),
            on="doi_norm", how="inner",
        )
        if merged.empty:
            print(f"  no matched rows — skipping metrics for {model_name}")
            continue

        m = compute_metrics(merged["TrueLabel"], merged["PredLabel"])
        m["model"] = model_name
        metric_rows.append(m)
        print(f"  matched {m['n_eval']} rows  acc={m['accuracy']:.4f}  macroF1={m['macro_f1']:.4f}")

        if cfg.plot_confusion:
            plot_confusion_matrix(m["TP"], m["FN"], m["FP"], m["TN"], model_name)

    metrics_df = pd.DataFrame(metric_rows, columns=[
        "model", "n_eval", "accuracy",
        "precision_Y", "recall_Y", "f1_Y",
        "precision_N", "recall_N", "f1_N",
        "macro_precision", "macro_recall", "macro_f1",
        "TP", "FP", "TN", "FN",
    ])
    for c in ["accuracy", "precision_Y", "recall_Y", "f1_Y",
              "precision_N", "recall_N", "f1_N",
              "macro_precision", "macro_recall", "macro_f1"]:
        if c in metrics_df.columns:
            metrics_df[c] = metrics_df[c].astype(float).round(4)

    print("\nMetrics (Y is positive, plus N and macro):")
    print(metrics_df.to_string(index=False))

    # --- 5d. Save ---
    if cfg.output_file:
        print(f"\nWriting {cfg.output_file}")
        with pd.ExcelWriter(cfg.output_file, engine="openpyxl") as writer:
            if full_df is not None:
                full_df.drop(columns=["_doi_norm"], errors="ignore").to_excel(
                    writer, index=False, sheet_name="full_with_predictions",
                )
            metrics_df.to_excel(writer, index=False, sheet_name="metrics")

    return metrics_df


# ===========================================================================
# 6. Command-line interface
# ===========================================================================
def _parse_predictions(raw: List[str]) -> Dict[str, str]:
    """Parse repeated --predictions NAME=FILE flags into an ordered dict."""
    out: Dict[str, str] = {}
    for entry in raw:
        if "=" not in entry:
            raise SystemExit(f"--predictions expects NAME=FILE, got: {entry!r}")
        name, path = entry.split("=", 1)
        name, path = name.strip(), path.strip()
        if not name or not path:
            raise SystemExit(f"--predictions expects NAME=FILE, got: {entry!r}")
        out[name] = path
    return out


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="Step 1.3 — analyse Step-1.1 / 1.2 predictions vs ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Defaults:
    #   FULL_FILE        = "Full.xlsx"
    #   GPT5_FILE        = "Full_gpt-5.xlsx"
    #   GPT4MINI_FILE    = "Full_gpt-4o-mini.xlsx"
    #   GT_FILE          = "mof_pdf_labels_using gpt5 only YN response 478.xlsx"
    #   OPEN_SOURCE_FILE = "ground truth open access 500 around 278 download.xlsx"
    #   OUTPUT_FILE      = "Full_with_gpt5_gpt4omini.xlsx"
    #   OPEN_SOURCE_ONLY = True   (i.e. open-source filter on by default)

    parser.add_argument("--ground-truth",
                        default="mof_pdf_labels_using gpt5 only YN response 478.xlsx",
                        help="Path to ground-truth xlsx with 'File'/'DOI' + 'Agent_YN' "
                             "(default: notebook GT_FILE)")
    parser.add_argument("--predictions", action="append", default=[], metavar="NAME=FILE",
                        help="Model prediction file (repeat for each model). If omitted, "
                             "defaults to the notebook pair: 'gpt-5=Full_gpt-5.xlsx' + "
                             "'gpt-4o-mini=Full_gpt-4o-mini.xlsx'.")
    parser.add_argument("--full", default="Full.xlsx",
                        help="Full.xlsx of paper metadata to join model labels into "
                             "(default: Full.xlsx)")
    parser.add_argument("--output", default="Full_with_gpt5_gpt4omini.xlsx",
                        help="Output xlsx (gets 'full_with_predictions' + 'metrics' sheets) "
                             "(default: Full_with_gpt5_gpt4omini.xlsx)")
    parser.add_argument("--open-source-file",
                        default="ground truth open access 500 around 278 download.xlsx",
                        help="xlsx whose 'Downloaded' column = 1 restricts evaluation "
                             "(default: notebook OPEN_SOURCE_FILE, OPEN_SOURCE_ONLY=True). "
                             "Pass an empty string to disable the open-source filter.")
    parser.add_argument("--open-source-sheets", nargs="*", default=None,
                        help="Limit open-source audit to these sheet names (default: all)")
    parser.add_argument("--pred-column", default="Agent_YN",
                        help="Label column inside each prediction file (default: Agent_YN)")
    parser.add_argument("--plot", action=argparse.BooleanOptionalAction, default=True,
                        help="Render a 2x2 confusion-matrix plot per model (default: on). Pass --no-plot to suppress.")

    args = parser.parse_args()
    if not args.predictions:
        args.predictions = [
            "gpt-5=Full_gpt-5.xlsx",
            "gpt-4o-mini=Full_gpt-4o-mini.xlsx",
        ]
    # Empty string for --open-source-file disables the filter.
    open_source_file = args.open_source_file if args.open_source_file else None

    return RunConfig(
        ground_truth_file=args.ground_truth,
        predictions=_parse_predictions(args.predictions),
        full_file=args.full,
        output_file=args.output,
        open_source_file=open_source_file,
        open_source_sheets=args.open_source_sheets,
        pred_column=args.pred_column,
        plot_confusion=args.plot,
    )


if __name__ == "__main__":
    run(_parse_args())
