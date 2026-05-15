"""
Step 1.1 — MOF Abstract Classifier
===================================
Reads an Excel file of papers and writes a Y/N label per row in the
Agent_YN column using the OpenAI Responses API.

Usage
-----
  python run.py [options]

Quick examples (matching the original notebooks):

  # 1.1a — gpt-4o-mini on Full.xlsx
  python run.py --input-name Full --model gpt-4o-mini

  # 1.1b — gpt-5 with medium reasoning on Full.xlsx
  python run.py --input-name Full --model gpt-5 --effort medium

  # 1.1c — gpt-5.1 with high reasoning on 478-item test set
  python run.py --input-name Full_478test_only --model gpt-5.1 --effort high

  # 1.1c — gpt-5.1 with no reasoning on 478-item test set
  python run.py --input-name Full_478test_only --model gpt-5.1 --effort none

  # 1.1c — gpt-4o-mini with no reasoning on 478-item test set
  #         (effort "none" included in output filename for comparison runs)
  python run.py --input-name Full_478test_only --model gpt-4o-mini --effort none

Requirements
------------
  pip install pandas openpyxl openai
  export OPENAI_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import time
from typing import Optional

from openai import OpenAI

from config import (
    COL_ABSTRACT,
    COL_AGENT_ANSWER,
    COL_ARTICLE_TITLE,
    COL_AUTHOR_KEYW,
    COL_KEYWORDS_PLUS,
    COL_SOURCE_TITLE,
    RunConfig,
)
from io_utils import load_input_df, load_or_init_output, rows_to_process_indices
from prompt import build_prompt
from senders import ModelSender


def run(cfg: RunConfig, client: Optional[OpenAI] = None) -> None:
    """Execute a full classification run according to cfg."""
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

        ans = sender.call_with_timeout(prompt, row_idx=idx)

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


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="MOF Abstract Classifier — step 1.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input-name", default="Full",
        help="Base name of input xlsx without extension (default: Full)",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="Model: gpt-4o-mini | gpt-5 | gpt-5.1  (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--effort", default=None,
        choices=["none", "low", "medium", "high"],
        help=(
            "Reasoning effort for gpt-5/gpt-5.1 models. "
            "Omit for chat models. "
            "When set, effort is included in the output filename."
        ),
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="Request timeout in seconds (default: 90 for reasoning models, 60 for chat models)",
    )
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
    parser.add_argument("--no-debug-per-row", action="store_true",
                        help="Suppress per-row debug output for skipped rows")

    args = parser.parse_args()

    is_reasoning = args.model.startswith("gpt-5") and args.effort is not None
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
        debug_per_row=not args.no_debug_per_row,
    )


if __name__ == "__main__":
    run(_parse_args())
