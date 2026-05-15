"""
Step 1.1 — Abstract-only Y/N classification
===========================================
What it does
    For each paper in an Excel file of metadata, ask an LLM to read only
    the abstract (plus title + keywords) and answer one yes/no question:

        Y = the abstract describes a TRADITIONAL solution-phase MOF synthesis
            (solvothermal / hydrothermal / room-temperature solution /
             slow diffusion / layering)
        N = otherwise

    The model returns a single character. No PDF is downloaded or read.

Input
    ``<input-name>.xlsx``  — one row per paper. Required columns:
    DOI, Article Title, Source Title, Author Keywords, Keywords Plus, Abstract.

Output
    ``<input-name>_<model>[_<effort>].xlsx``  — same rows plus a new
    ``Agent_YN`` column ('Y' / 'N' / blank).

Resume-safe
    The output is rewritten every ``--save-every`` rows. Rerunning the
    script only re-classifies rows whose ``Agent_YN`` is still blank.

File layout (numbered sections below)
    1. Column names      4. Excel I/O (load / resume / pending rows)
    2. RunConfig         5. Main loop
    3. Prompt builder    6. CLI

The only import from outside this file is the generic OpenAI-call wrapper
in ``utils/`` (``ModelSender`` + ``ModelConfig``).

Usage
-----
  python 1_1_classify_abstract.py [options]

Examples:

  # gpt-4o-mini on Full.xlsx
  python 1_1_classify_abstract.py --input-name Full --model gpt-4o-mini

  # gpt-5 with medium reasoning on Full.xlsx
  python 1_1_classify_abstract.py --input-name Full --model gpt-5 --effort medium

  # gpt-5.1 with high reasoning on a 478-item test set
  python 1_1_classify_abstract.py --input-name Full_478test_only --model gpt-5.1 --effort high

Requirements
------------
  pip install pandas openpyxl openai
  set OPENAI_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
from openai import OpenAI

from utils.base_config import ModelConfig
from utils.model_sender import ModelSender


# ===========================================================================
# 1. Column names — must match the input Excel exactly
# ===========================================================================
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

COL_AGENT_ANSWER = "Agent_YN"   # the column we write: 'Y' / 'N' / empty


# ===========================================================================
# 2. Run configuration — every dial for one classification run
# ===========================================================================
@dataclass
class RunConfig(ModelConfig):
    """
    Extends ``utils.base_config.ModelConfig`` (which carries model/effort/
    timeout/retry/debug dials) with Step-1.1 input/output naming.
    """
    input_name: str = "Full"

    @property
    def input_xlsx(self) -> str:
        return self.input_name + ".xlsx"

    @property
    def output_xlsx(self) -> str:
        if self.reasoning_effort is not None:
            return f"{self.input_name}_{self.model_name}_{self.reasoning_effort}.xlsx"
        return f"{self.input_name}_{self.model_name}.xlsx"


# ===========================================================================
# 3. Prompt — what we ask the model for each row
# ===========================================================================
def build_prompt(
    title: str,
    source: str,
    author_keywords: Optional[str],
    keywords_plus: Optional[str],
    abstract: str,
) -> str:
    """Build the classification prompt from paper metadata fields."""
    title           = title or ""
    source          = source or ""
    author_keywords = author_keywords or ""
    keywords_plus   = keywords_plus or ""
    abstract        = abstract or ""
    return f"""
You are a domain expert in metal–organic frameworks (MOFs).
Given the paper info (title, keywords, abstract), output a SINGLE uppercase letter:

Y = The abstract indicates (explicitly OR implicitly) an experimental synthesis of a MOF via a TRADITIONAL **solution-phase** route (solvothermal, hydrothermal, **ambient/room-temperature**, slow diffusion/layering) in common solvents (water/alcohols/DMF/DEF/DMAc; mixed solvents; acids/bases as modulators). Explicit numeric conditions are **not required** in the abstract if synthesis is clearly stated or strongly implied.

Treat the following as **strong positive cues** (any one suffices unless an explicit exclusion appears):
  • **Named MOF + synthesis verb** (e.g., "synthesized/prepared/obtained MOF-5/MOF-74/MOF-177/MOF-199/IRMOF-0; UiO/MIL/ZIF/HKUST/PCN/NU/DUT").
  • **Announcement of new MOF(s)** (e.g., "we report the synthesis of MOF-519 and MOF-520").
  • **Structure/porosity readouts on a new MOF** (SCXRD/PXRD of the framework; BET/adsorption measurements), which imply executed synthesis and usually reported conditions.
  • **Direct solution-phase cues**: solvothermal/hydrothermal/diffusion/room-temperature solution, common solvents, modulators, crystal growth/yield.

Weaker positive cues (two or more suffice if no strong cue): mention of **both** a metal source/cluster and a multidentate linker; solvent/modulator/time/temperature words without explicit "synthesized"; references to optimization of synthetic variables.

N = Otherwise, or if any **explicit** exclusion is present:
  mechanochemical/ball-milling/LAG, microwave, sonochemical, electrochemical, vapor-phase CVD/ALD, **ionothermal as primary medium**, microfluidic/flow, plasma, aerosol/spray; film-only growth; computational/review; MOF-derived materials; PSM-only; non-porous 1D/2D coordination polymers; non-MOFs (MOC/MOP/COF/HOF/SOF/PAF/PPN/POF).

Decision protocol (internal, do not output):
  1) If explicit exclusion → N.
  2) If any **strong positive** → Y.
  3) Else if ≥2 weaker positives → Y.
  4) Else → N.

Return ONLY 'Y' or 'N' (one character). No punctuation, words, or explanation.

TITLE: {title}
SOURCE: {source}
AUTHOR KEYWORDS: {author_keywords}
KEYWORDS PLUS: {keywords_plus}
ABSTRACT: {abstract}
""".strip()


# ===========================================================================
# 4. Data I/O — load input, init/load output (resume-safe), find pending rows
# ===========================================================================
def safe_read_excel(path_str: str) -> Optional[pd.DataFrame]:
    """Read an Excel file, backing it up and returning None if unreadable."""
    try:
        return pd.read_excel(path_str, engine="openpyxl")
    except Exception:
        try:
            bak = path_str + ".bak"
            if os.path.exists(path_str):
                os.replace(path_str, bak)
                print(f"[WARN] Existing output file unreadable; backed up to: {bak}")
        finally:
            return None


def load_input_df(path: str) -> pd.DataFrame:
    """Load and validate the input Excel, returning only the required columns."""
    df = pd.read_excel(str(path), engine="openpyxl")
    missing = [c for c in REQUIRED_INPUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in input: {missing}")
    return df[REQUIRED_INPUT_COLS].copy()


def load_or_init_output(input_df: pd.DataFrame, out_path: str) -> pd.DataFrame:
    """
    Load existing output workbook if present (resume mode), or create a fresh one.

    Always syncs metadata columns from ``input_df`` so stale cached data is
    overwritten, and handles row-count mismatch by padding / trimming.
    """
    p        = Path(out_path)
    path_str = str(p)
    out_df   = None

    if p.exists() and p.is_file():
        out_df = safe_read_excel(path_str)

    if out_df is None:
        out_df = input_df.copy()
        out_df[COL_AGENT_ANSWER] = None
        out_df.to_excel(path_str, index=False, engine="openpyxl")
        return out_df

    needed = list(input_df.columns) + [COL_AGENT_ANSWER]
    for c in needed:
        if c not in out_df.columns:
            out_df[c] = None
    out_df = out_df[needed]

    if len(out_df) < len(input_df):
        additional = input_df.iloc[len(out_df):].copy()
        additional[COL_AGENT_ANSWER] = None
        out_df = pd.concat([out_df, additional], ignore_index=True)
    elif len(out_df) > len(input_df):
        out_df = out_df.iloc[: len(input_df)].copy()

    for c in input_df.columns:
        out_df[c] = input_df[c].values

    out_df.to_excel(path_str, index=False, engine="openpyxl")
    return out_df


def rows_to_process_indices(out_df: pd.DataFrame) -> list:
    """Return row indices where ``Agent_YN`` is blank (not yet classified)."""
    mask = out_df[COL_AGENT_ANSWER].astype(str).str.strip().isin(["", "nan", "None"])
    return list(out_df[mask].index)


# ===========================================================================
# 5. Main run loop
# ===========================================================================
def run(cfg: RunConfig, client: Optional[OpenAI] = None) -> None:
    """Execute one full Step-1.1 classification run."""
    client = client or OpenAI()
    sender = ModelSender(cfg, client)

    start_time = time.time()
    input_df   = load_input_df(cfg.input_xlsx)
    out_df     = load_or_init_output(input_df, cfg.output_xlsx)

    all_pending = rows_to_process_indices(out_df)
    pending     = [i for i in all_pending if i < cfg.test_n] if cfg.test_mode else all_pending

    total_pending = len(pending)
    print(f"Model: {cfg.model_name} | Output: {cfg.output_xlsx}")
    if cfg.reasoning_effort is not None:
        print(f"Reasoning effort: {cfg.reasoning_effort}")
    print(f"Rows pending: {total_pending} (of {len(out_df)})")
    if cfg.test_mode:
        print(f"TEST MODE: will process first {cfg.test_n} pending rows.")

    processed_since_save = 0
    for k, idx in enumerate(pending, start=1):
        row    = out_df.loc[idx]
        prompt = build_prompt(
            title=row[COL_ARTICLE_TITLE],
            source=row[COL_SOURCE_TITLE],
            author_keywords=row[COL_AUTHOR_KEYW],
            keywords_plus=row[COL_KEYWORDS_PLUS],
            abstract=row[COL_ABSTRACT],
        )

        ans = sender.call_with_timeout(prompt, item_label=f"row {idx}")

        if ans in ("Y", "N"):
            out_df.at[idx, COL_AGENT_ANSWER] = ans
        else:
            print(f"Skipped row {idx}: model returned neither 'Y' nor 'N'.")

        processed_since_save += 1
        if processed_since_save >= cfg.save_every or k == total_pending:
            out_df.to_excel(cfg.output_xlsx, index=False, engine="openpyxl")
            elapsed   = time.time() - start_time
            remaining = (
                out_df[COL_AGENT_ANSWER].astype(str).str.strip()
                .isin(["", "nan", "None"]).sum()
            )
            print(
                f"Saved after {processed_since_save} rows | "
                f"Elapsed: {elapsed:.1f}s | Remaining overall: {remaining}"
            )
            processed_since_save = 0

    print(f"Done. Total elapsed: {time.time() - start_time:.1f}s")


# ===========================================================================
# 6. Command-line interface
# ===========================================================================
def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="Step 1.1 — MOF abstract classifier (Excel in → Excel out)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input-name", default="Full",
                        help="Base name of input xlsx without extension (default: Full)")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="Model: gpt-4o-mini | gpt-5 | gpt-5.1  (default: gpt-4o-mini)")
    parser.add_argument("--effort", default=None, choices=["none", "low", "medium", "high"],
                        help="Reasoning effort for gpt-5/gpt-5.1; omit for chat models.")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Request timeout in seconds (default: 90 for reasoning, 60 for chat)")
    parser.add_argument("--max-tries", type=int, default=2,
                        help="Retries per row (default: 2)")
    parser.add_argument("--save-every", type=int, default=10,
                        help="Save output every N rows (default: 10)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: process only the first --test-n pending rows")
    parser.add_argument("--test-n", type=int, default=5,
                        help="Number of rows to process in test mode (default: 5)")
    parser.add_argument("--debug-dump", action="store_true",
                        help="Print full raw API response once for debugging")
    parser.add_argument("--no-debug-per-item", action="store_true",
                        help="Suppress per-row debug output for skipped rows")

    args = parser.parse_args()
    is_reasoning   = args.model.startswith("gpt-5") and args.effort is not None
    default_timeout = 90 if is_reasoning else 60

    return RunConfig(
        input_name=args.input_name,
        model_name=args.model,
        reasoning_effort=args.effort,
        request_timeout_seconds=args.timeout if args.timeout is not None else default_timeout,
        max_tries=args.max_tries,
        save_every=args.save_every,
        test_mode=args.test,
        test_n=args.test_n,
        debug_one_time_dump=args.debug_dump,
        debug_per_item=not args.no_debug_per_item,
    )


if __name__ == "__main__":
    run(_parse_args())
