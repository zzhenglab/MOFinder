"""Interactive ipywidgets batch screener for the MOF P/N classifier.

This is the JupyterLab UI from `step 6 evaluation_reaction PN.ipynb`. Run it
inside a Jupyter cell with `%run eval/run_ui_batch_classifier.py` — it will
render the multi-select panel and a pop-up log window. Headless `python`
runs will execute the import block and then exit without showing the UI.

Cells are marked with `# %%` so JupyterLab "Run Cell" works as before.
"""

# %% [markdown]
# Interactive MOF batch classifier with pop-up log window (Jupyter)
# - Multi-select lists (1..N per field), scroll to view all
# - Builds all combinations and evaluates with concurrency
# - Streams logs into a pop-up style window within the notebook
# - Prints at most about 100 detailed result lines per run
# - Saves two CSVs: latest run and total history
# - Skips combos already evaluated (based on combo_key in history CSV)

# %%
import asyncio
import hashlib
import itertools
import json
import math
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import nest_asyncio
import numpy as np
import pandas as pd

nest_asyncio.apply()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_engine import (  # noqa: E402
    MOF_CLASSIFIER_SYSTEM_PROMPT,
    call_chat_completions,
    ensure_api_key,
    extract_logprobs_for_label_chat,
    get_async_client,
    prob_from_pair,
)

# -----------------------
# Config
# -----------------------
MODEL_ID = "ft:gpt-4.1-2025-04-14:washington-university-in-st-louis-zheng-group:cls-full:CUx5cx8y"

POS_PATH = Path("mof_extraction_1_2_3_4_5_6_7.csv")
NEG_PATH = Path("mof_extraction_failures_enum_1_2_3_4_5_6.csv")

OUT_DIR = Path("out_ui")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LATEST_CSV = OUT_DIR / "mof_ui_batch_results_latest.csv"
ALL_CSV = OUT_DIR / "mof_ui_batch_results_all.csv"

AUTOSAVE_EVERY = 1000

ensure_api_key()
aclient = get_async_client()


# -----------------------
# Source-data helpers
# -----------------------
def to_float_any(x: Any) -> Optional[float]:
    if pd.isna(x):
        return None
    s = str(x)
    m = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not m:
        return None
    try:
        return float(m[0])
    except Exception:
        return None


def parse_ml_ratio(val: Any) -> Optional[float]:
    if pd.isna(val):
        return None
    s = str(val).strip()
    try:
        return float(s)
    except Exception:
        pass
    parts = re.split(r"[:/]", s)
    nums: List[float] = []
    for p in parts:
        n = to_float_any(p)
        if n is None:
            return None
        nums.append(n)
    if len(nums) == 1:
        return nums[0]
    metal, linkers = nums[0], sum(nums[1:])
    if linkers == 0:
        return None
    return metal / linkers


def freq_list(series: pd.Series, top_n: int = 10) -> List[str]:
    s = series.fillna("").map(lambda x: str(x).strip()).replace({"": np.nan}).dropna()
    if s.empty:
        return []
    counts = s.value_counts()
    top = list(counts.head(top_n).index)
    rest = sorted([v for v in counts.index if v not in top])
    return top + rest


def freq_list_numeric(series: pd.Series, parser, top_n: int = 10) -> List[float]:
    vals = series.map(parser).dropna().astype(float)
    if vals.empty:
        return []
    counts = vals.value_counts()
    top = list(counts.head(top_n).index)
    rest = sorted([v for v in counts.index if v not in top])
    return top + rest


def load_sources() -> Optional[pd.DataFrame]:
    dfs = []
    for p in [POS_PATH, NEG_PATH]:
        if p.exists():
            try:
                dfs.append(pd.read_csv(p, low_memory=False))
            except Exception:
                pass
    return pd.concat(dfs, ignore_index=True) if dfs else None


df_src = load_sources()

if df_src is None:
    warnings.warn(
        "Source CSVs not found. Using small fallback lists. Put your CSVs in the "
        "working directory for full lists."
    )
    metal_opts = ["Zn(NO3)2·6H2O", "AlCl3·6H2O", "ZrOCl2·8H2O", "ZrCl4",
                  "Cu(NO3)2·3H2O", "FeCl2·4H2O"]
    linker_opts = ["terephthalic acid", "benzene-1,3,5-tricarboxylic acid",
                   "2-nitroterephthalic acid", "4,4'-azobis(pyridine)"]
    modulator_opts = ["null", "formic acid", "acetic acid", "benzoic acid"]
    solvent_opts = ["dimethylformamide", "water", "ethanol", "N,N-diethylformamide"]
    conc_opts = [50.0, 40.0, 30.0, 20.0]
    mlr_opts = [1.0, 2.0, 0.5]
    temp_opts = [120.0, 25.0, 100.0, 140.0]
    time_opts = [72.0, 0.0, 24.0, 48.0]
else:
    metal_opts = freq_list(df_src.get("metal_1", pd.Series(dtype=str)))
    linker_opts = freq_list(df_src.get("linker_1", pd.Series(dtype=str)), top_n=900)
    mods_raw = freq_list(df_src.get("modulator_1", pd.Series(dtype=str)))
    modulator_opts = ["null"] + [
        v for v in mods_raw if v.lower() not in ("none", "null", "na")
    ]
    solvent_opts = freq_list(df_src.get("solvent_main", pd.Series(dtype=str)))
    # NB: source column names preserved even when misspelled in upstream CSVs.
    conc_opts = freq_list_numeric(
        df_src.get("metel_concnertation", pd.Series(dtype=float)), to_float_any
    )
    mlr_opts = freq_list_numeric(
        df_src.get("M_L_ratio", pd.Series(dtype=str)), parse_ml_ratio
    )
    temp_opts = freq_list_numeric(
        df_src.get("temperature_c", pd.Series(dtype=float)), to_float_any
    )
    time_opts = freq_list_numeric(
        df_src.get("time_h", pd.Series(dtype=float)), to_float_any
    )


# -----------------------
# Widgets and layout
# -----------------------
import ipywidgets as W  # noqa: E402
from IPython.display import display, clear_output  # noqa: E402

style = {"description_width": "140px"}
list_layout = W.Layout(width="360px", height="180px")

metal_w = W.SelectMultiple(options=metal_opts, description="Metal", style=style, layout=list_layout)
linker_w = W.SelectMultiple(options=linker_opts, description="Linker", style=style, layout=list_layout)
mod_w = W.SelectMultiple(options=modulator_opts, description="Modulator", style=style, layout=list_layout)
solv_w = W.SelectMultiple(options=solvent_opts, description="Solvent", style=style, layout=list_layout)

conc_w = W.SelectMultiple(options=conc_opts, description="Conc. (mM)", style=style, layout=list_layout)
mlr_w = W.SelectMultiple(options=mlr_opts, description="M/L ratio", style=style, layout=list_layout)
temp_w = W.SelectMultiple(options=temp_opts, description="Temp (°C)", style=style, layout=list_layout)
time_w = W.SelectMultiple(options=time_opts, description="Time (h)", style=style, layout=list_layout)

test_mode_w = W.Checkbox(value=False, description="Test mode (first 10)")
conc_slider = W.IntSlider(value=50, min=1, max=50, step=1, description="Concurrency", style=style)
start_btn = W.Button(description="Start", button_style="primary")
clear_btn = W.Button(description="Clear log")
expand_toggle = W.ToggleButton(value=False, description="Expand log")
height_slider = W.IntSlider(value=600, min=300, max=1400, step=50, description="Log height (px)")

bar_html = W.HTML()


def chips(values):
    if not values:
        return "-"
    return ", ".join(map(str, values))


def refresh_bar(*args):
    bar_html.value = (
        f"<b>Selected</b><br>"
        f"<b>Metal</b>: {chips(metal_w.value)}<br>"
        f"<b>Linker</b>: {chips(linker_w.value)}<br>"
        f"<b>Modulator</b>: {chips(mod_w.value)}<br>"
        f"<b>Solvent</b>: {chips(solv_w.value)}<br>"
        f"<b>Conc. (mM)</b>: {chips(conc_w.value)}<br>"
        f"<b>M/L ratio</b>: {chips(mlr_w.value)}<br>"
        f"<b>Temp (°C)</b>: {chips(temp_w.value)}<br>"
        f"<b>Time (h)</b>: {chips(time_w.value)}"
    )


for w in [metal_w, linker_w, mod_w, solv_w, conc_w, mlr_w, temp_w, time_w]:
    w.observe(refresh_bar, names="value")
refresh_bar()

ui_left = W.VBox([metal_w, linker_w, mod_w, solv_w])
ui_right = W.VBox([conc_w, mlr_w, temp_w, time_w])
ui_ctrls = W.HBox([test_mode_w, conc_slider, start_btn, clear_btn, expand_toggle, height_slider])

modal_out = W.Output(layout=W.Layout(
    position="fixed", top="5%", left="5%", width="90%", height="85%",
    overflow="auto", border="2px solid #444", background_color="white",
    padding="10px", display="none", z_index=9999,
))
modal_header = W.HBox([W.HTML("<b>Batch run log</b>"),
                       W.Button(description="Close", button_style="", icon="times")])
modal_box = W.VBox([modal_header, modal_out])


def _apply_modal_layout():
    if expand_toggle.value:
        modal_out.layout.top = "2%"
        modal_out.layout.left = "1%"
        modal_out.layout.width = "98%"
        modal_out.layout.height = f"{min(95, int(height_slider.value / 7))}%"
    else:
        modal_out.layout.top = "5%"
        modal_out.layout.left = "5%"
        modal_out.layout.width = "90%"
        modal_out.layout.height = f"{height_slider.value}px"


def open_modal():
    _apply_modal_layout()
    modal_out.layout.display = "block"


def close_modal(_=None):
    modal_out.layout.display = "none"


def on_expand_change(_):
    _apply_modal_layout()


def on_height_change(_):
    _apply_modal_layout()


expand_toggle.observe(on_expand_change, names="value")
height_slider.observe(on_height_change, names="value")
modal_header.children[1].on_click(close_modal)

display(W.HBox([ui_left, ui_right, W.VBox([bar_html])]), ui_ctrls, modal_box)


# -----------------------
# Combo-build and eval helpers
# -----------------------
def build_user_json(d: Dict[str, Any]) -> str:
    mod = None if str(d["modulator"]).strip().lower() == "null" else d["modulator"]
    return json.dumps({
        "metal_precursor": d["metal_precursor"],
        "organic_linker": d["organic_linker"],
        "modulator": mod,
        "solvent": d["solvent"],
        "metal_concentration_mM": float(d["metal_concentration_mM"]),
        "M_L_ratio": float(d["M_L_ratio"]),
        "temperature_C": float(d["temperature_C"]),
        "time_h": float(d["time_h"]),
    }, ensure_ascii=False)


def build_messages_from_combo(d: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": MOF_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_json(d)},
    ]


def combo_key(d: Dict[str, Any]) -> str:
    s = json.dumps({
        "metal_precursor": d["metal_precursor"],
        "organic_linker": d["organic_linker"],
        "modulator": d["modulator"],
        "solvent": d["solvent"],
        "metal_concentration_mM": float(d["metal_concentration_mM"]),
        "M_L_ratio": float(d["M_L_ratio"]),
        "temperature_C": float(d["temperature_C"]),
        "time_h": float(d["time_h"]),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def parse_pred_label(txt: str) -> str:
    m = re.search(r"[PN]", (txt or "").upper())
    return m.group(0) if m else ""


def running_stats(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    preds = [r.get("pred_label") for r in rows if r.get("pred_label") in ("P", "N")]
    if not preds:
        return {"count": 0, "p_rate": 0.0, "avg_latency": 0.0}
    p_rate = sum(1 for x in preds if x == "P") / len(preds)
    lat = float(np.mean([r.get("latency_s", 0.0) for r in rows]))
    return {"count": len(preds), "p_rate": float(p_rate), "avg_latency": lat}


# -----------------------
# Button actions and run guard
# -----------------------
_is_running = False


def set_running(state: bool):
    global _is_running
    _is_running = state
    start_btn.disabled = state
    start_btn.description = "Running..." if state else "Start"


def validate_selections():
    fields = [
        ("Metal", metal_w.value, 999),
        ("Linker", linker_w.value, 999),
        ("Modulator", mod_w.value, 999),
        ("Solvent", solv_w.value, 999),
        ("Conc. (mM)", conc_w.value, 999),
        ("M/L ratio", mlr_w.value, 999),
        ("Temp (°C)", temp_w.value, 999),
        ("Time (h)", time_w.value, 999),
    ]
    for name, vals, max_allowed in fields:
        n = len(vals)
        if not (1 <= n <= max_allowed):
            return f"{name} must have between 1 and {max_allowed} selections (got {n})."
    return None


def build_combos():
    metals = list(metal_w.value)
    linkers = list(linker_w.value)
    modulators = list(mod_w.value)
    solvents = list(solv_w.value)
    concs = list(conc_w.value)
    mlrs = list(mlr_w.value)
    temps = list(temp_w.value)
    times = list(time_w.value)
    combos = []
    for (m, l, md, s, c, r, tC, th) in itertools.product(
        metals, linkers, modulators, solvents, concs, mlrs, temps, times
    ):
        combos.append({
            "metal_precursor": m,
            "organic_linker": l,
            "modulator": md,
            "solvent": s,
            "metal_concentration_mM": float(c),
            "M_L_ratio": float(r),
            "temperature_C": float(tC),
            "time_h": float(th),
        })
    return combos


def append_log(msg: str):
    modal_out.append_stdout(msg + "\n")


# -----------------------
# Main eval loop with autosave
# -----------------------
async def run_eval(pending: List[Tuple[str, Dict[str, Any]]], concurrency: int):
    semaphore = asyncio.Semaphore(concurrency)
    rows: List[Dict[str, Any]] = []

    async def worker(k_d):
        k, d = k_d
        msgs = build_messages_from_combo(d)
        t0 = time.time()
        text, choice = await call_chat_completions(aclient, MODEL_ID, msgs)
        lat = time.time() - t0

        pred = parse_pred_label(text)
        lp_P = lp_N = None
        prob_P = prob_N = None
        chosen_is_argmax = None
        if choice and pred in ("P", "N"):
            lp_P, lp_N, chosen_is_argmax = extract_logprobs_for_label_chat(
                choice, pred, label_pair=("P", "N"),
            )
            prob_P, prob_N = prob_from_pair(lp_P, lp_N)

        return {
            "combo_key": k,
            "metal_precursor": d["metal_precursor"],
            "organic_linker": d["organic_linker"],
            "modulator": d["modulator"],
            "solvent": d["solvent"],
            "metal_concentration_mM": d["metal_concentration_mM"],
            "M_L_ratio": d["M_L_ratio"],
            "temperature_C": d["temperature_C"],
            "time_h": d["time_h"],
            "json_input": build_user_json(d),
            "model_output": text,
            "pred_label": pred,
            "logprob_P": lp_P,
            "logprob_N": lp_N,
            "prob_P": prob_P,
            "prob_N": prob_N,
            "chosen_is_argmax": chosen_is_argmax,
            "latency_s": lat,
        }

    async def guarded(k_d):
        async with semaphore:
            return await worker(k_d)

    tasks = [asyncio.create_task(guarded(item)) for item in pending]

    start_t = time.time()
    processed = 0
    n_total = len(tasks)
    log_every = 1 if n_total <= 100 else max(1, math.ceil(n_total / 100))

    for coro in asyncio.as_completed(tasks):
        row = await coro
        rows.append(row)
        processed += 1

        if AUTOSAVE_EVERY and (processed % AUTOSAVE_EVERY == 0):
            df_partial = pd.DataFrame(rows)
            df_partial.to_csv(LATEST_CSV, index=False)
            if ALL_CSV.exists():
                try:
                    df_all = pd.read_csv(ALL_CSV)
                except Exception:
                    df_all = pd.DataFrame(columns=df_partial.columns)
                merged = pd.concat([df_all, df_partial], ignore_index=True)
                merged = merged.drop_duplicates(subset=["combo_key"], keep="first")
                merged.to_csv(ALL_CSV, index=False)
            else:
                df_partial.drop_duplicates(subset=["combo_key"], keep="first").to_csv(
                    ALL_CSV, index=False
                )
            append_log(f"[Autosave] Saved {processed} rows to {LATEST_CSV} and updated {ALL_CSV}")

        if (processed % log_every == 0) or (processed == n_total):
            append_log(
                f"[{processed}/{n_total}] {row['json_input']} -> {row['pred_label']} "
                f"(logP={row['logprob_P']}, logN={row['logprob_N']}, "
                f"pP={None if row['prob_P'] is None else round(row['prob_P'], 4)}, "
                f"pN={None if row['prob_N'] is None else round(row['prob_N'], 4)}, "
                f"argmax={row['chosen_is_argmax']})"
            )
            elapsed = time.time() - start_t
            avg = elapsed / processed
            eta = avg * (n_total - processed)
            stats = running_stats(rows)
            append_log(
                f"   progress: elapsed {int(elapsed)} s  eta {int(eta)} s  "
                f"count {stats['count']}  P-rate {stats['p_rate']:.3f}  "
                f"avg_latency {stats['avg_latency']:.2f} s"
            )

    df_run = pd.DataFrame(rows)
    df_run.to_csv(LATEST_CSV, index=False)
    if ALL_CSV.exists():
        try:
            df_all = pd.read_csv(ALL_CSV)
        except Exception:
            df_all = pd.DataFrame(columns=df_run.columns)
        merged = pd.concat([df_all, df_run], ignore_index=True)
        merged = merged.drop_duplicates(subset=["combo_key"], keep="first")
        merged.to_csv(ALL_CSV, index=False, encoding="utf-8-sig")
    else:
        df_run.drop_duplicates(subset=["combo_key"], keep="first").to_csv(
            ALL_CSV, index=False, encoding="utf-8-sig"
        )

    append_log(f"\nLatest CSV written: {LATEST_CSV}")
    append_log(f"History CSV updated: {ALL_CSV}")
    display(df_run.tail(10))


def on_clear(_):
    with modal_out:
        clear_output(wait=True)


clear_btn.on_click(on_clear)


def on_start(_):
    if _is_running:
        open_modal()
        append_log("[Info] A run is already in progress. Ignoring click.")
        return

    err = validate_selections()
    if err:
        open_modal()
        append_log(f"[Error] {err}")
        return

    combos = build_combos()
    total = len(combos)
    if test_mode_w.value:
        combos = combos[:10]

    seen: set = set()
    if ALL_CSV.exists():
        try:
            prev_all = pd.read_csv(ALL_CSV)
            if "combo_key" in prev_all.columns:
                seen = set(prev_all["combo_key"].astype(str).tolist())
        except Exception:
            pass

    pending: List[Tuple[str, Dict[str, Any]]] = []
    for d in combos:
        k = combo_key(d)
        if k not in seen:
            pending.append((k, d))

    open_modal()
    with modal_out:
        clear_output(wait=True)
    append_log(
        f"Total combinations constructed: {len(combos)}"
        + (f" (from {total})" if test_mode_w.value else "")
    )
    if seen:
        append_log(f"Skipping {len(seen)} combos already in history (dedup by combo_key).")
    if not pending:
        append_log("No new combos to evaluate.")
        return

    concurrency = max(1, min(int(conc_slider.value), 50))
    append_log(f"Starting run with concurrency={concurrency}...\n")

    async def runner():
        try:
            await run_eval(pending, concurrency)
            append_log("\nDone.")
        finally:
            set_running(False)

    set_running(True)
    try:
        asyncio.get_running_loop()
        asyncio.create_task(runner())
    except RuntimeError:
        asyncio.run(runner())


start_btn.on_click(on_start)

# If widgets do not appear in Jupyter, run:
#   pip install ipywidgets
#   jupyter nbextension enable --py widgetsnbextension
# In JupyterLab:
#   pip install jupyterlab_widgets
