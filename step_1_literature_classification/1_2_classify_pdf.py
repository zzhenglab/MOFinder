"""
Step 1.2 — Full-text Y/N classification (ground-truth pass)
===========================================================
What it does
    Same yes/no question as Step 1.1, but the LLM sees the first ~8000
    words of the actual PDF instead of just the abstract. This pass is
    used to build the ground-truth labels that Step 1.1 is evaluated
    against in Step 1.3.

        Y = the paper describes a TRADITIONAL solution-phase MOF synthesis
        N = otherwise

Input
    A folder of PDFs (default: ``./downloaded/*.pdf``).

Output
    ``<output-prefix>_<model>[_<batch-tag>].xlsx`` — one row per PDF. With
    default flags this produces ``mof_pdf_labels_gpt-5_580.xlsx``,
    ``OUTPUT_XLSX = "mof_pdf_labels_" + MODEL_NAME + "_580.xlsx"`` formula
    (the ``_580`` encodes "580-PDF ground-truth batch"; override with
    ``--batch-tag`` or pass an empty tag to drop it). Note ``_<effort>`` is
    deliberately NOT in the filename so if you
    sweep multiple efforts you must distinguish runs via ``--batch-tag``
    (e.g. ``--batch-tag low_580`` vs ``high_580``). Columns: ``File`` (PDF
    path) and ``Agent_YN`` ('Y' / 'N' / blank).

Resume-safe
    The output is rewritten every ``--save-every`` files. Rerunning only
    re-classifies files whose ``Agent_YN`` is still blank; PDFs that
    disappeared from the folder are dropped, new PDFs are appended.

File layout (numbered sections below)
    1. Output columns         5. Excel I/O
    2. RunConfig              6. Main loop
    3. Prompt builder         7. CLI
    4. PDF text extraction (pypdf)

The only import from outside this file is the generic OpenAI-call wrapper
in ``utils/`` (``ModelSender`` + ``ModelConfig``).

Usage
-----
  python 1_2_classify_pdf.py [options]

Examples:

  # Default — gpt-5 with low reasoning effort on the 580-PDF ground-truth batch. MODEL_NAME='gpt-5',
  # GPT5_EFFORT='low' setup exactly. Output: mof_pdf_labels_gpt-5_580.xlsx
  python 1_2_classify_pdf.py

  # Switch model — gpt-4o-mini chat path. Output:
  # mof_pdf_labels_gpt-4o-mini_580.xlsx
  python 1_2_classify_pdf.py --model gpt-4o-mini

  # Sweep efforts: distinguish runs via --batch-tag since effort isn't in
  # the filename. Output: mof_pdf_labels_gpt-5.1_high_580.xlsx
  python 1_2_classify_pdf.py --model gpt-5.1 --effort high --batch-tag high_580

  # Drop the batch tag entirely. Output: mof_pdf_labels_gpt-5.1.xlsx
  python 1_2_classify_pdf.py --model gpt-5.1 --effort medium --batch-tag ""

Requirements
------------
  pip install pandas openpyxl pypdf openai
  set OPENAI_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pypdf import PdfReader
from openai import OpenAI

from utils.base_config import ModelConfig
from utils.model_sender import ModelSender


# ===========================================================================
# 1. Output column names — workbook is keyed by PDF path
# ===========================================================================
COL_FILE         = "File"
COL_AGENT_ANSWER = "Agent_YN"   # 'Y' / 'N' / empty


# ===========================================================================
# 2. Run configuration — every dial for one PDF-classification run
# ===========================================================================
@dataclass
class RunConfig(ModelConfig):
    """
    Extends ``utils.base_config.ModelConfig`` (which carries model/effort/
    timeout/retry/debug dials) with Step-1.2 input/output naming.
    """
    input_folder: str = "downloaded"
    output_prefix: str = "mof_pdf_labels"
    # Batch-size suffix appended to the output filename
    # ``mof_pdf_labels_<model>_580.xlsx`` convention (the "_580"
    # encoded "this is the 580-PDF ground-truth batch"). Pass ``--batch-tag ""``
    # to drop the suffix for a different / unnamed batch.
    batch_tag: str = "580"
    max_words_per_pdf: int = 8000

    # Step 1.2 reads a lot more text per request than 1.1, so keep timeout
    # generous and the default test batch a bit larger.
    request_timeout_seconds: int = 90
    test_n: int = 10

    @property
    def output_xlsx(self) -> str:
        #  Formula: "mof_pdf_labels_" + MODEL_NAME + "_580.xlsx" — no
        # effort segment. Mirrored exactly so default args produce
        # ``mof_pdf_labels_gpt-5_580.xlsx`` (the file the original notebook
        # writes). To disambiguate multiple effort runs against the same
        # model, override --batch-tag (e.g. --batch-tag "low_580").
        tag_suffix = f"_{self.batch_tag}" if self.batch_tag else ""
        return f"{self.output_prefix}_{self.model_name}{tag_suffix}.xlsx"


# ===========================================================================
# 3. Prompt — what we ask the model for each PDF
# ===========================================================================
def build_prompt_from_text(filename: str, text_chunk: str) -> str:
    """Build the classification prompt from a PDF's filename + extracted text."""
    text_chunk = text_chunk or ""
    return f"""
You are a domain expert in metal-organic frameworks.

Task
Return a single uppercase letter:
Y = The paper indicates an experimental synthesis of a MOF via a traditional solution-phase route. This includes solvothermal, hydrothermal, ambient or room-temperature solution, slow diffusion or layering, with common solvents such as water, alcohols, DMF, DEF, DMAc, and optional modulators like acids or bases. Exact numeric conditions are not required if synthesis is clearly stated or strongly implied.
N = Otherwise.

Definition and decision cues
- A MOF is a crystalline, porous framework built from metal nodes or clusters connected by strong bonds
  - A named MOF plus a synthesis verb. Examples: MOF-5, MOF-74, UiO, MIL, ZIF, HKUST, PCN, NU, DUT.
  - Reporting the synthesis or preparation of new MOF materials.
  - Structure or porosity readouts that imply realized synthesis such as PXRD or SCXRD of a framework, or gas sorption or BET on a new MOF.
  - Explicit solution-phase terms such as solvothermal, hydrothermal, diffusion, room-temperature solution, crystal growth, yield, solvent names, modulators.


Return start with Y or N. follow by your explaination within in 20 words.

FILENAME: {filename}
TEXT START:
{text_chunk}
""".strip()


# ===========================================================================
# 4. PDF text extraction
# ===========================================================================
def extract_first_words_from_pdf(
    pdf_path: Path,
    max_words: int,
    debug: bool = True,
) -> str:
    """
    Read up to ``max_words`` words from the start of a PDF.

    Joins hyphen-broken words across line breaks and collapses whitespace so
    the result is a single space-separated string suitable for prompting.
    Returns "" on any read error.
    """
    try:
        reader = PdfReader(str(pdf_path))
        parts: List[str] = []
        word_count = 0
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if not txt:
                continue
            # Normalize whitespace and hyphenation at line breaks
            txt = re.sub(r"-\s*\n\s*", "", txt)   # join hyphen-broken words
            txt = re.sub(r"\s*\n\s*", " ", txt)   # join lines
            tokens = txt.split()
            if not tokens:
                continue
            take = min(len(tokens), max_words - word_count)
            parts.append(" ".join(tokens[:take]))
            word_count += take
            if word_count >= max_words:
                break
        return " ".join(parts).strip()
    except Exception as e:
        if debug:
            print(f"[DEBUG] Failed to read {pdf_path.name}: {e}")
        return ""


# ===========================================================================
# 5. Excel I/O — init/load output (resume-safe), find pending files
# ===========================================================================
def init_or_load_output(xlsx_path: str, files: List[str]) -> pd.DataFrame:
    """
    Load existing output workbook if present (resume mode), or create a fresh one.

    Schema is always [COL_FILE, COL_AGENT_ANSWER]. New PDFs are appended with a
    blank label; rows for files no longer on disk are dropped. The workbook is
    written immediately so it exists for later incremental saves.
    """
    p = Path(xlsx_path)
    df: pd.DataFrame

    if p.exists() and p.is_file():
        try:
            df = pd.read_excel(str(p), engine="openpyxl")
        except Exception:
            bak = str(p) + ".bak"
            os.replace(str(p), bak)
            print(f"[WARN] Existing output unreadable. Backed up to: {bak}")
            df = pd.DataFrame(columns=[COL_FILE, COL_AGENT_ANSWER])
    else:
        df = pd.DataFrame(columns=[COL_FILE, COL_AGENT_ANSWER])

    # Normalize columns
    df = df[[c for c in [COL_FILE, COL_AGENT_ANSWER] if c in df.columns]].copy()
    if COL_FILE not in df.columns:
        df[COL_FILE] = []
    if COL_AGENT_ANSWER not in df.columns:
        df[COL_AGENT_ANSWER] = None

    # Append rows for new files
    existing = set(df[COL_FILE].astype(str).tolist())
    new_rows = [f for f in files if f not in existing]
    if new_rows:
        df = pd.concat(
            [df, pd.DataFrame({COL_FILE: new_rows, COL_AGENT_ANSWER: [None] * len(new_rows)})],
            ignore_index=True,
        )

    # Drop rows for files that no longer exist
    current_set = set(files)
    df = df[df[COL_FILE].astype(str).isin(current_set)].reset_index(drop=True)

    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    return df


def rows_to_process_indices(out_df: pd.DataFrame, existing_files: set) -> List[int]:
    """Return row indices where the label is blank AND the file is still on disk."""
    mask_unlabeled = out_df[COL_AGENT_ANSWER].astype(str).str.strip().isin(["", "nan", "None"])
    mask_exists    = out_df[COL_FILE].astype(str).apply(lambda p: p in existing_files)
    return list(out_df[mask_unlabeled & mask_exists].index)


# ===========================================================================
# 6. Main run loop
# ===========================================================================
def run(cfg: RunConfig, client: Optional[OpenAI] = None) -> None:
    """Execute one full Step-1.2 PDF classification run."""
    client = client or OpenAI()
    sender = ModelSender(cfg, client)

    start_time = time.time()

    folder = Path(cfg.input_folder)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {cfg.input_folder}")

    pdf_paths = sorted([str(p) for p in folder.glob("*.pdf")])
    print(f"Found {len(pdf_paths)} PDFs in {cfg.input_folder}")

    out_df = init_or_load_output(cfg.output_xlsx, pdf_paths)
    existing_files_set = set(pdf_paths)

    pending = rows_to_process_indices(out_df, existing_files_set)
    if cfg.test_mode:
        pending = pending[: cfg.test_n]

    total_pending = len(pending)
    print(f"Model: {cfg.model_name} | Output: {cfg.output_xlsx}")
    if cfg.reasoning_effort is not None:
        print(f"Reasoning effort: {cfg.reasoning_effort}")
    print(f"Files pending: {total_pending} of {len(out_df)}")
    if cfg.test_mode:
        print(f"TEST MODE: will process first {cfg.test_n} pending files.")

    processed_since_save = 0
    for k, idx in enumerate(pending, start=1):
        file_path = out_df.at[idx, COL_FILE]
        fname     = Path(file_path).name

        text_chunk = extract_first_words_from_pdf(
            Path(file_path),
            cfg.max_words_per_pdf,
            debug=cfg.debug_per_item,
        )
        if not text_chunk:
            print(f"Skipped file {fname}: no extractable text.")
            out_df.at[idx, COL_AGENT_ANSWER] = ""
        else:
            prompt = build_prompt_from_text(filename=fname, text_chunk=text_chunk)
            ans    = sender.call_with_timeout(prompt, item_label=fname)
            if ans in ("Y", "N"):
                out_df.at[idx, COL_AGENT_ANSWER] = ans
            else:
                print(f"Skipped file {fname}: model returned neither 'Y' nor 'N'.")

        processed_since_save += 1
        if processed_since_save >= cfg.save_every or k == total_pending:
            out_df.to_excel(cfg.output_xlsx, index=False, engine="openpyxl")
            elapsed   = time.time() - start_time
            remaining = (
                out_df[COL_AGENT_ANSWER].astype(str).str.strip()
                .isin(["", "nan", "None"]).sum()
            )
            print(
                f"Saved after {processed_since_save} files | "
                f"Elapsed: {elapsed:.1f}s | Remaining overall: {remaining}"
            )
            processed_since_save = 0

    print(f"Done. Total elapsed: {time.time() - start_time:.1f}s")


# ===========================================================================
# 7. Command-line interface
# ===========================================================================
def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="Step 1.2 — MOF PDF classifier (folder of PDFs → Excel)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input-folder", default="downloaded",
                        help="Folder containing PDFs to classify (default: downloaded)")
    parser.add_argument("--output-prefix", default="mof_pdf_labels",
                        help="Prefix for the output xlsx (default: mof_pdf_labels)")
    parser.add_argument("--batch-tag", default="580",
                        help="Batch-size suffix appended after model/effort, mirroring the "
                             "'_580' convention (default: 580). Pass an empty "
                             "string to drop the suffix.")
    parser.add_argument("--max-words", type=int, default=8000,
                        help="Max words extracted per PDF (default: 8000)")
    parser.add_argument("--model", default="gpt-5",
                        help="Model: gpt-4o-mini | gpt-5 | gpt-5.1  (default: gpt-5, "
                             "ground-truth pass)")
    parser.add_argument("--effort", default="low", choices=["none", "low", "medium", "high"],
                        help="Reasoning effort for gpt-5/gpt-5.1 (default: low, matching the "
                             "GPT5_EFFORT='low'). Pass --effort none for "
                             "no-reasoning mode; for chat models like gpt-4o-mini the value "
                             "is included in the filename but has no API effect.")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Request timeout in seconds (default: 90)")
    parser.add_argument("--max-tries", type=int, default=2,
                        help="Retries per file (default: 2)")
    parser.add_argument("--save-every", type=int, default=10,
                        help="Save output every N files (default: 10)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: process only the first --test-n pending files")
    parser.add_argument("--test-n", type=int, default=10,
                        help="Number of files to process in test mode (default: 10)")
    parser.add_argument("--debug-dump", action="store_true",
                        help="Print full raw API response once for debugging")
    parser.add_argument("--no-debug-per-item", action="store_true",
                        help="Suppress per-file debug output for skipped files")

    args = parser.parse_args()

    return RunConfig(
        input_folder=args.input_folder,
        output_prefix=args.output_prefix,
        batch_tag=args.batch_tag,
        max_words_per_pdf=args.max_words,
        model_name=args.model,
        reasoning_effort=args.effort,
        request_timeout_seconds=args.timeout if args.timeout is not None else 90,
        max_tries=args.max_tries,
        save_every=args.save_every,
        test_mode=args.test,
        test_n=args.test_n,
        debug_one_time_dump=args.debug_dump,
        debug_per_item=not args.no_debug_per_item,
    )


if __name__ == "__main__":
    run(_parse_args())
