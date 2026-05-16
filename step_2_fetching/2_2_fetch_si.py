"""
Step 2.2 — Fetch Supporting Information (SI) files from publisher websites
==========================================================================
What it does
    A Tkinter app that walks each row of an Excel paper list and downloads
    the SUPPORTING INFORMATION file (SI) — not the main article — from the
    publisher's website. For each pending row it:

        1. opens ``https://doi.org/<DOI>`` in a fresh incognito Chrome window;
        2. matches the publisher to WILEY / AMER CHEMICAL SOC /
           ROYAL SOC CHEMISTRY / SPRINGER / ELSEVIER (using alias regex —
           e.g. "Springer Nature", "Nature", "RSC" all map correctly);
        3. runs the hand-written SI flow for that publisher (each
           publisher has its own ``<pub>_si_flow`` function below). The
           flows scroll + look for publisher-specific anchor icons,
           navigate to the SI link, and click through to a download.
        4. drives the native Save As dialog to ``./SI downloaded/<doi-safe>_SI.<ext>``
           — the extension is whatever the publisher served (``.pdf``,
           ``.docx``, ``.zip``, ...).
        5. marks the Excel row ``SI Downloaded = '1'`` on success / ``'0'``
           on failure.

    Two operating modes are exposed on the UI:
      - Normal:        process rows whose ``SI Downloaded`` is blank.
      - Double-check:  re-attempt rows currently marked ``'0'``.
    There is also a "Sync from folder -> Excel" block that walks the SI
    folder and back-fills the workbook from filenames already present
    (handy after a manual download batch).

Input
    An ``.xlsx`` with at least ``DOI`` and ``Publisher`` columns; the SI
    download status lives in ``SI Downloaded`` (added if absent). The
    file is selected via the GUI and remembered in ``app_settings_si.json``.

Output
    ``./SI downloaded/<doi-with-_>_SI.<ext>`` — one file per successful row.
    The input Excel is rewritten in place with ``DOI Link`` (hyperlink)
    and ``SI Downloaded`` ('1' / '0' / blank). Resume-safe.

Where data flows
    Default input  : ``<repo>/data/SELECTED 7000 SI.xlsx`` — the curated
                     ~7000-paper subset (filtered from Step 1.1's
                     classification output) for which SI files are
                     wanted. The ``SI Downloaded`` column is added on
                     first run if absent. Override via Browse;
                     last-opened path is remembered in
                     ``app_settings_si.json`` next to this script.
    Default output : ``<excel_folder>/SI downloaded/<doi>_SI.<ext>`` —
                     i.e. ``<repo>/data/SI downloaded/`` if the default
                     input is used. SI files sit alongside the main PDFs
                     produced by Step 2.1, ready to be paired in
                     step_3_mining/.

Calibration (one-time per workstation)
    Open any Save As dialog, hover over the File Name text box, press F8
    then F9. Stored in ``si_downloader_calibration.json`` next to this script.

Hotkeys
    Ctrl+Shift+S  — save progress now
    Ctrl+Shift+X  — STOP NOW

Icon templates
    A folder named ``icon`` next to the Excel file must contain template
    PNG/JPG files matching the names referenced in each ``<pub>_si_flow``
    below — e.g. ``WILEY_SI_1.png``, ``WILEY_SI_3a.png``,
    ``AMER CHEMICAL SOC_SI_1.png``, ``SPRINGER_SI_Accept.png``, etc.

File layout (numbered sections below)
    1. Quick settings (timings, retries, save cadence, journal policy)
    2. Constants (publishers, sample URLs)
    3. Globals + log
    4. Local-only helpers (sleep_check_abort, anti-idle thread)
    5. Per-publisher SI flows  (wiley_si_flow, acs_si_flow, ...)
    6. Tkinter App (Block 1 sync, Block 2 main run)
    7. Boot

Reusable bits live in ``utils/``.

Requirements
    pip install pandas openpyxl pyautogui pyperclip pillow pynput opencv-python
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional, Tuple

import pandas as pd
import pyautogui
from pynput import keyboard as pynput_keyboard

from utils.calibration import capture_f8_f9_points, load_calibration, save_calibration
from utils.chrome import (
    close_all_chrome,
    ensure_chrome_closed,
    go_to_address_bar_and_open,
    open_in_chrome,
)
from utils.desktop import (
    fast_scroll_down,
    move_cursor_top_center,
    press_down_n,
    press_up_n,
    safe_reset_to_desktop,
)
from utils.doi import (
    SUPPORTED_PREFIXES,
    doi_journal_key,
    doi_stem,
    doi_to_link,
    publisher_key,
)
from utils.excel_io import (
    ensure_download_dir,
    load_and_prepare_excel,
    save_progress,
    status_norm,
)
from utils.icons import click_icon, wait_for_image
from utils.save_dialog import fresh_file_ready_any, rename_in_save_dialog


pyautogui.FAILSAFE = False


# ===========================================================================
# 1. Quick settings — adjust to tune timing without touching the loop
# ===========================================================================
BROWSER_OPEN_WAIT                   = 2.0
WAIT_AFTER_NAV                      = 4.0
ICON_CONFIDENCE                     = 0.87
ICON_SEARCH_TICK                    = 0.6

# Wiley scrolling
WILEY_SCROLL_TOTAL_SEC              = 10.0
WILEY_SCROLL_STEP_SEC               = 0.03
WILEY_SCROLL_UP_COUNT               = 5

# Retries
MAX_RETRIES_PER_ROW                 = 2

# Batch Excel saves (counts only rows actually attempted in block 2)
SAVE_EVERY_PENDING                  = 20
DESKTOP_RESET_PAUSE                 = 0.5

# Save-dialog typing cadence
STEP_PAUSE                          = 0.35
ICON_BEFORE_RENAME_WAIT             = 2.0
POST_ENTER_WAIT                     = 0.7

# Cookie-button look-up window
ACCEPT_COOKIE_WAIT                  = 5.0

# Journal policy — fast-skip a journal after too many failures
MAX_JOURNAL_FAILS_BASE              = 5
JOURNAL_SUCCESS_THRESHOLD_FOR_BOOST = 2
JOURNAL_SUCCESS_BOOST_MULTIPLIER    = 2

# Anti-idle (jiggle cursor every N seconds so OS doesn't sleep)
ANTI_IDLE_SECONDS                   = 170
ANTI_IDLE_PIXELS                    = 2

# Workbook + calibration. JSON files pinned next to this script so cwd
# doesn't matter; default Excel resolves to <repo>/data/Full.xlsx so the
# pipeline stays connected end-to-end (see "Where data flows" above).
_SCRIPT_DIR                         = Path(__file__).resolve().parent
_REPO_ROOT                          = _SCRIPT_DIR.parent
DEFAULT_EXCEL_PATH                  = str(_REPO_ROOT / "data" / "SELECTED 7000 SI.xlsx")
APP_SETTINGS                        = str(_SCRIPT_DIR / "app_settings_si.json")
CAL_FILE                            = str(_SCRIPT_DIR / "si_downloader_calibration.json")
DEFAULT_GLOBAL_SAVE_XY              = [425, 393]

# Apply DOI Link hyperlink styling only on final save (slow on big files)
APPLY_HYPERLINKS_ON_FINAL_SAVE      = True


# ===========================================================================
# 2. Constants — sample pages for manual flow testing
# ===========================================================================
SAMPLE_URLS = {
    "WILEY":               "https://advanced.onlinelibrary.wiley.com/doi/10.1002/adfm.202410751",
    "AMER CHEMICAL SOC":   "https://doi.org/10.1021/acs.chemmater.9b02322",
    "ROYAL SOC CHEMISTRY": "https://doi.org/10.1039/D3QI00391D",
    "SPRINGER":            "https://www.nature.com/articles/10.1038/s41467-025-64092-9",
    "ELSEVIER":            "https://www.sciencedirect.com/science/article/pii/S0001868622001348",
}


# ===========================================================================
# 3. Module globals + log
# ===========================================================================
abort_now      = False
save_requested = False


def log(*args) -> None:
    """Timestamped stdout logger used by every block below."""
    ts = time.strftime("[%H:%M:%S]")
    print(ts, *args, flush=True)


def _abort() -> bool:
    """Lambda-friendly accessor so utils.* helpers can poll the abort flag."""
    return abort_now


# ===========================================================================
# 4. Local-only helpers
# ===========================================================================
def _wait_for_image(icon_dir: Path, name: str, timeout: float) -> Optional[Tuple[int, int]]:
    """Thin wrapper baking in this script's confidence + tick + abort flag."""
    return wait_for_image(
        icon_dir, name, timeout,
        confidence=ICON_CONFIDENCE,
        tick=ICON_SEARCH_TICK,
        abort_flag=_abort,
    )


def _click_icon(icon_dir: Path, name: str, timeout: float, post_wait: float = 0.0) -> bool:
    """Thin wrapper baking in this script's confidence + tick + abort flag."""
    return click_icon(
        icon_dir, name, timeout, post_wait=post_wait,
        confidence=ICON_CONFIDENCE,
        tick=ICON_SEARCH_TICK,
        abort_flag=_abort,
    )


def _rename_in_save_dialog(target_base_path: Path, coords_save_xy: Tuple[int, int]) -> Optional[Path]:
    """Thin wrapper baking in this script's save-dialog timings."""
    return rename_in_save_dialog(
        target_base_path,
        coords_save_xy,
        before_rename_wait=ICON_BEFORE_RENAME_WAIT,
        step_pause=STEP_PAUSE,
        post_enter_wait=POST_ENTER_WAIT,
        abort_flag=_abort,
    )


def _load_cal_with_defaults() -> dict:
    """Calibration JSON for SI mode keeps only GLOBAL_SAVE.save_xy."""
    return load_calibration(
        CAL_FILE,
        defaults={"GLOBAL_SAVE": {"save_xy": list(DEFAULT_GLOBAL_SAVE_XY)}},
    )


# ===========================================================================
# 5. Per-publisher SI flows
#    Each returns: True (saved), False (failed), or "SKIP" (anchor never
#    appeared — leave row blank, don't burn a retry).
# ===========================================================================
def wiley_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path):
    """
    WILEY:
        1. wait 5 s, fast-scroll down 10 s, look 3 s for WILEY_SI_1 (logo at
           page bottom = anchor we reached the SI section);
        2. retry the scroll once if not found, else SKIP;
        3. nudge up a few presses, find WILEY_SI_2 (the "Supporting Info"
           bar) within 9 tries, click it;
        4. wait 2 s, then try WILEY_SI_3a / 3aa (.docx link) -> WILEY_SI_4
           -> rename + save; or WILEY_SI_3b / 3bb (alt link) -> rename + save.
    """
    time.sleep(5.0)
    fast_scroll_down(WILEY_SCROLL_TOTAL_SEC, step_sec=WILEY_SCROLL_STEP_SEC, abort_flag=_abort)
    if not _wait_for_image(icon_dir, "WILEY_SI_1", timeout=3.0):
        fast_scroll_down(WILEY_SCROLL_TOTAL_SEC, step_sec=WILEY_SCROLL_STEP_SEC, abort_flag=_abort)
        if not _wait_for_image(icon_dir, "WILEY_SI_1", timeout=3.0):
            return "SKIP"
    press_up_n(WILEY_SCROLL_UP_COUNT, interval=0.02)
    for _ in range(9):
        pos = _wait_for_image(icon_dir, "WILEY_SI_2", timeout=2.0)
        if pos:
            pyautogui.moveTo(pos[0], pos[1], duration=0.2); pyautogui.click()
            break
        press_up_n(WILEY_SCROLL_UP_COUNT, interval=0.02)
    else:
        return False
    time.sleep(2.0)
    if _click_icon(icon_dir, "WILEY_SI_3a", timeout=2.0) or _click_icon(icon_dir, "WILEY_SI_3aa", timeout=2.0):
        time.sleep(3.0)
        if not _click_icon(icon_dir, "WILEY_SI_4", timeout=7.0, post_wait=0.8):
            return False
        return bool(_rename_in_save_dialog(target_base, coords_save_xy))
    if _click_icon(icon_dir, "WILEY_SI_3b", timeout=2.0, post_wait=1.0) \
       or _click_icon(icon_dir, "WILEY_SI_3bb", timeout=3.0, post_wait=1.0):
        return bool(_rename_in_save_dialog(target_base, coords_save_xy))
    return False


def acs_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    """
    AMER CHEMICAL SOC:
        1. look for AMER CHEMICAL SOC_SI_1 / 1b / 1c (SI section header);
        2. if found click it, wait 2 s, then try _2a/_2aa/_2b (PDF buttons)
           -> _3 (download) -> rename; OR _2c/_2d (.docx direct link) -> rename.
        3. else scroll down in chunks of 10 and re-try the same _2x icons.
    """
    pos_hdr = _wait_for_image(icon_dir, "AMER CHEMICAL SOC_SI_1", timeout=8.0) \
              or _wait_for_image(icon_dir, "AMER CHEMICAL SOC_SI_1b", timeout=5.0) \
              or _wait_for_image(icon_dir, "AMER CHEMICAL SOC_SI_1c", timeout=3.0)
    if pos_hdr:
        pyautogui.moveTo(pos_hdr[0], pos_hdr[1], duration=0.2); pyautogui.click()
        time.sleep(2.0)
        if _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2a",  timeout=2.0) \
           or _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2aa", timeout=2.0) \
           or _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2b",  timeout=4.0):
            time.sleep(3.0)
            if not _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_3", timeout=6.0, post_wait=0.8):
                return False
            return bool(_rename_in_save_dialog(target_base, coords_save_xy))
        if _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2c", timeout=3.0) \
           or _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2d", timeout=5.0):
            return bool(_rename_in_save_dialog(target_base, coords_save_xy))
        return False

    for _ in range(5):
        press_down_n(10, interval=0.02)
        if _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2a", timeout=5.0) \
           or _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2b", timeout=5.0):
            time.sleep(4.0)
            if not _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_3", timeout=6.0, post_wait=0.8):
                return False
            return bool(_rename_in_save_dialog(target_base, coords_save_xy))
        if _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2c", timeout=5.0) \
           or _click_icon(icon_dir, "AMER CHEMICAL SOC_SI_2d", timeout=5.0):
            return bool(_rename_in_save_dialog(target_base, coords_save_xy))
    return False


def rsc_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    """
    ROYAL SOC CHEMISTRY:
        1. look for ROYAL SOC CHEMISTRY_SI_1 (SI bar in right panel); if not
           found press Down 10 times and retry, up to 4 rounds;
        2. wait 5 s, click _2 (download), rename + save.
    """
    for _ in range(4):
        if _click_icon(icon_dir, "ROYAL SOC CHEMISTRY_SI_1", timeout=5.0):
            break
        press_down_n(10, interval=0.02); time.sleep(2.0)
    else:
        return False
    time.sleep(5.0)
    if not _click_icon(icon_dir, "ROYAL SOC CHEMISTRY_SI_2", timeout=6.0, post_wait=0.8):
        return False
    return bool(_rename_in_save_dialog(target_base, coords_save_xy))


def springer_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    """
    SPRINGER:
        1. try to dismiss cookie banners (SPRINGER_SI_Accept / Accept2);
        2. fast-scroll down 10 s to materialize SI section;
        3. up to 10 rounds: press Up 10 times, then try SPRINGER_SI_1 / _2 /
           _2b / _2c; on a hit, wait 5 s, look for _3b first (direct file)
           -> rename, else click _3 (download) -> rename.
    """
    _click_icon(icon_dir, "SPRINGER_SI_Accept",  timeout=ACCEPT_COOKIE_WAIT, post_wait=0.5)
    _click_icon(icon_dir, "SPRINGER_SI_Accept2", timeout=ACCEPT_COOKIE_WAIT, post_wait=0.5)

    def click_any_2_then_save() -> bool:
        if _click_icon(icon_dir, "SPRINGER_SI_1",  timeout=2.0) \
           or _click_icon(icon_dir, "SPRINGER_SI_2",  timeout=1.0) \
           or _click_icon(icon_dir, "SPRINGER_SI_2b", timeout=1.0) \
           or _click_icon(icon_dir, "SPRINGER_SI_2c", timeout=1.0):
            time.sleep(5.0)
            if _wait_for_image(icon_dir, "SPRINGER_SI_3b", timeout=3.0):
                return bool(_rename_in_save_dialog(target_base, coords_save_xy))
            if _click_icon(icon_dir, "SPRINGER_SI_3", timeout=6.0, post_wait=0.8):
                return bool(_rename_in_save_dialog(target_base, coords_save_xy))
        return False

    fast_scroll_down(10.0, step_sec=WILEY_SCROLL_STEP_SEC, abort_flag=_abort)
    for _ in range(10):
        press_up_n(10, interval=0.02)
        if click_any_2_then_save():
            return True
    return False


def elsevier_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    """
    ELSEVIER:
        1. dismiss up to three cookie banners (Accept / Accept2 / Accept3);
        2. click optional SI_1 / _1b (side bar);
        3. up to 8 rounds: try _2 or _2b; on hit, wait 3 s, click _3 (icon
           on download bar), then rename + save.
    """
    _click_icon(icon_dir, "ELSEVIER_SI_Accept",  timeout=1.0, post_wait=0.5)
    _click_icon(icon_dir, "ELSEVIER_SI_Accept2", timeout=1.0, post_wait=0.5)
    _click_icon(icon_dir, "ELSEVIER_SI_Accept3", timeout=1.0, post_wait=0.5)
    _click_icon(icon_dir, "ELSEVIER_SI_1",  timeout=1.0)
    _click_icon(icon_dir, "ELSEVIER_SI_1b", timeout=1.0)
    for _ in range(8):
        if _click_icon(icon_dir, "ELSEVIER_SI_2",  timeout=1.0):
            break
        if _click_icon(icon_dir, "ELSEVIER_SI_2b", timeout=1.0):
            break
        press_down_n(20, interval=0.02); time.sleep(0.5)
    else:
        return False
    time.sleep(3.0)
    _click_icon(icon_dir, "ELSEVIER_SI_3", timeout=2.0, post_wait=0.5)
    return bool(_rename_in_save_dialog(target_base, coords_save_xy))


PUBLISHER_FLOW = {
    "WILEY":               wiley_si_flow,
    "AMER CHEMICAL SOC":   acs_si_flow,
    "ROYAL SOC CHEMISTRY": rsc_si_flow,
    "SPRINGER":            springer_si_flow,
    "ELSEVIER":            elsevier_si_flow,
}


# ===========================================================================
# 6. Tkinter App
# ===========================================================================
class App:
    """
    Two-block UI:

      - Block 1 (Sync from folder -> Excel) walks the ``SI downloaded``
        folder and back-fills ``SI Downloaded = '1'`` for any row whose
        target stem already exists on disk (useful after manual batches).
      - Block 2 (Start) iterates pending rows and runs the publisher flow
        for each.

    Plus the standard goodies: F8/F9 capture for the save-box, mouse
    tracker, Ctrl+Shift+S / X hotkeys, and an anti-idle cursor jiggle.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("SI downloader")

        self.ui_queue       = queue.Queue()
        self.excel_path_var = tk.StringVar(value=self._load_last_excel() or DEFAULT_EXCEL_PATH)
        self.status_var     = tk.StringVar(value="Ready")
        self.stats_var      = tk.StringVar(value="Left: 0  Success: 0  Fail: 0  ETA: 00:00")
        self.cal_data       = _load_cal_with_defaults()

        self.test_mode_var    = tk.BooleanVar(value=False)
        self.double_check_var = tk.BooleanVar(value=False)

        self.succ_count = 0
        self.fail_count = 0

        self.anti_idle_stop:   Optional[threading.Event]  = None
        self.anti_idle_thread: Optional[threading.Thread] = None

        # ---- layout ----
        pad = 6
        frm = ttk.Frame(root, padding=pad); frm.pack(fill="both", expand=True)

        row_file = ttk.Frame(frm); row_file.pack(fill="x", pady=(pad, 0))
        ttk.Label(row_file, text="Excel file:").pack(side="left")
        ttk.Entry(row_file, textvariable=self.excel_path_var, width=80).pack(side="left", padx=(pad, pad))
        ttk.Button(row_file, text="Browse", command=self.pick_file).pack(side="left")
        ttk.Checkbutton(row_file, text="Test mode (5 rows)",          variable=self.test_mode_var).pack(side="left", padx=8)
        ttk.Checkbutton(row_file, text="Double check mode (only 0s)", variable=self.double_check_var).pack(side="left", padx=8)

        row_sync = ttk.Frame(frm); row_sync.pack(fill="x", pady=(pad, 0))
        ttk.Button(row_sync, text="Sync from folder -> Excel (block 1)", command=self.block1_sync).pack(side="left")

        ttk.Label(frm, text="Publishers").pack(anchor="w", pady=(pad, 0))
        pub_row = ttk.Frame(frm); pub_row.pack(fill="x", pady=2)
        for name in SUPPORTED_PREFIXES:
            ttk.Button(pub_row, text=f"Open sample: {name}",
                       command=lambda n=name: self.open_sample(n)).pack(side="left", padx=3)

        ttk.Label(frm, text="Save dialog - FILE NAME box XY").pack(anchor="w", pady=(pad, 0))
        self.save_box_var = tk.StringVar(value=self.save_box_text())
        row_save = ttk.Frame(frm); row_save.pack(fill="x", pady=2)
        ttk.Label(row_save, textvariable=self.save_box_var, width=40, anchor="w").pack(side="left")
        ttk.Button(row_save, text="Set FILE NAME box XY (F8, then F9)", command=self.capture_global_save_xy).pack(side="left", padx=6)

        ctrl = ttk.Frame(frm); ctrl.pack(fill="x", pady=(pad, 0))
        ttk.Button(ctrl, text="Start (block 2)", command=self.start).pack(side="left", padx=(0, pad))
        ttk.Button(ctrl, text="STOP now",        command=self.stop_now).pack(side="left")

        ttk.Label(frm, textvariable=self.stats_var).pack(fill="x", pady=(pad, 0))
        ttk.Label(frm, textvariable=self.status_var).pack(fill="x", pady=(pad, 0))

        tracker = ttk.Frame(frm); tracker.pack(fill="x", pady=(pad, 0))
        self.mouse_xy_var = tk.StringVar(value="Mouse XY: ...")
        self.track_mouse  = tk.BooleanVar(value=False)
        ttk.Checkbutton(tracker, text="Track mouse XY", variable=self.track_mouse,
                        command=self.update_mouse_tracker).pack(side="left")
        ttk.Label(tracker, textvariable=self.mouse_xy_var).pack(side="left", padx=8)

        ttk.Label(frm, text="Hotkeys: Ctrl+Shift+S save now, Ctrl+Shift+X STOP now.").pack(fill="x", pady=(pad, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_hotkeys()
        self.root.after(150, self.poll_ui)
        self.root.after(120, self.update_mouse_tracker)

    # ---- window close ----
    def on_close(self) -> None:
        self.stop_now()
        def _wait_then_close():
            if hasattr(self, "worker") and getattr(self.worker, "is_alive", lambda: False)():
                self.root.after(200, _wait_then_close)
            else:
                try: self.stop_anti_idle()
                except Exception: pass
                ensure_chrome_closed(log=log)
                self.root.destroy()
        _wait_then_close()

    # ---- persistence ----
    def _load_last_excel(self) -> Optional[str]:
        try:
            if os.path.exists(APP_SETTINGS):
                with open(APP_SETTINGS, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return cfg.get("last_excel")
        except Exception:
            return None
        return None

    def _save_last_excel(self, path: str) -> None:
        try:
            with open(APP_SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"last_excel": path}, f, indent=2)
        except Exception:
            pass

    # ---- UI labels ----
    def save_box_text(self) -> str:
        g   = load_calibration(CAL_FILE).get("GLOBAL_SAVE", {})
        sav = tuple(g.get("save_xy")) if g.get("save_xy") else None
        return f"FILE NAME BOX XY: {sav}"

    def update_mouse_tracker(self) -> None:
        if self.track_mouse.get():
            p = pyautogui.position()
            self.mouse_xy_var.set(f"Mouse XY: ({p.x}, {p.y})")
            self.root.after(120, self.update_mouse_tracker)

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(title="Pick Excel file", filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            self.excel_path_var.set(path)
            self._save_last_excel(path)

    def open_sample(self, name: str) -> None:
        url = SAMPLE_URLS.get(name, "about:blank")
        ensure_chrome_closed(log=log)
        open_in_chrome("about:blank", new_window=True, browser_open_wait=BROWSER_OPEN_WAIT, log=log)
        time.sleep(BROWSER_OPEN_WAIT)
        go_to_address_bar_and_open(url, wait_after_nav=WAIT_AFTER_NAV, abort_flag=_abort, log=log)

    def capture_global_save_xy(self) -> None:
        messagebox.showinfo("Save-box capture", "Open any Save dialog. Hover FILE NAME box, press F8. Press F9 to finish.")
        points = capture_f8_f9_points(pump_ui=self.root.update)
        if not points:
            messagebox.showwarning("Save-box", "No position captured."); return
        pos = points[-1]
        cal = load_calibration(CAL_FILE)
        cal.setdefault("GLOBAL_SAVE", {})["save_xy"] = [int(pos[0]), int(pos[1])]
        save_calibration(CAL_FILE, cal)
        self.save_box_var.set(self.save_box_text())
        messagebox.showinfo("Saved", f"FILE NAME BOX XY saved at {pos}")

    # ---- hotkeys + ui pump ----
    def start_hotkeys(self) -> None:
        def on_save():
            global save_requested
            save_requested = True
            log("Hotkey save requested")
        def on_stop_now():
            global abort_now, save_requested
            save_requested = True
            abort_now = True
            log("Hotkey STOP now")
        combos = {
            "<ctrl>+<shift>+s": on_save,
            "<ctrl>+<shift>+x": on_stop_now,
            "<cmd>+<shift>+s":  on_save,
            "<cmd>+<shift>+x":  on_stop_now,
        }
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys(combos)
        self.hotkey_listener.start()

    def poll_ui(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "stats":
                    left = payload.get("left", 0); succ = payload.get("succ", 0); fail = payload.get("fail", 0)
                    m_total = payload.get("eta_secs", 0) // 60
                    h, m = divmod(m_total, 60)
                    self.stats_var.set(f"Left: {left}  Success: {succ}  Fail: {fail}  ETA: {h:02d}:{m:02d}")
                elif kind == "restore":
                    try:
                        self.root.deiconify(); self.root.lift()
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.root.after(150, self.poll_ui)

    # ---- anti-idle ----
    def start_anti_idle(self) -> None:
        if getattr(self, "anti_idle_thread", None) and self.anti_idle_thread.is_alive():
            return
        self.anti_idle_stop = threading.Event()
        def runner():
            while not self.anti_idle_stop.wait(ANTI_IDLE_SECONDS):
                try:
                    x, y = pyautogui.position()
                    pyautogui.moveTo(x, max(1, y - ANTI_IDLE_PIXELS), duration=0.05)
                    pyautogui.moveTo(x, y, duration=0.05)
                except Exception:
                    pass
        self.anti_idle_thread = threading.Thread(target=runner, daemon=True)
        self.anti_idle_thread.start()
        log("Anti-idle thread started")

    def stop_anti_idle(self) -> None:
        if getattr(self, "anti_idle_stop", None):
            self.anti_idle_stop.set()
            log("Anti-idle thread stop requested")

    # ===================================================================
    # Block 1 — sync from folder -> Excel
    # ===================================================================
    def block1_sync(self) -> None:
        """
        Walk the ``SI downloaded`` folder and mark any DOI whose
        ``<doi>_SI.*`` is already on disk as ``SI Downloaded = '1'``.
        """
        p = self.excel_path_var.get().strip()
        if not p:
            messagebox.showerror("Error", "Pick an Excel file first."); return
        excel_path = Path(p)
        if not excel_path.exists():
            messagebox.showerror("Error", f"File not found:\n{excel_path}"); return

        df = load_and_prepare_excel(
            excel_path,
            status_column="SI Downloaded",
            write_back=True,
            apply_links=False,
            normalize_status=True,
            log=log,
        )
        si_dir = ensure_download_dir(excel_path, name="SI downloaded")

        df["SI Downloaded"] = df["SI Downloaded"].apply(status_norm)

        col_before        = df["SI Downloaded"]
        cnt_1_before      = int((col_before == "1").sum())
        cnt_0_before      = int((col_before == "0").sum())
        cnt_empty_before  = int((col_before == "").sum())

        folder_files = [f for f in si_dir.iterdir() if f.is_file()]
        stems        = {f.stem for f in folder_files}
        in_folder    = len(folder_files)

        target_stems = df["DOI"].astype(str).map(doi_stem)

        to_update_mask  = (col_before == "") & (target_stems.isin(stems))
        updated_stems   = set(target_stems[to_update_mask].tolist())
        df.loc[to_update_mask, "SI Downloaded"] = "1"
        updates_applied = int(to_update_mask.sum())

        already_one_stems   = set(target_stems[col_before == "1"].tolist())
        unmatched_in_folder = stems - updated_stems - already_one_stems

        save_progress(df, excel_path, apply_links=APPLY_HYPERLINKS_ON_FINAL_SAVE, log=log)

        col_after       = df["SI Downloaded"].apply(status_norm)
        cnt_1_after     = int((col_after == "1").sum())
        cnt_0_after     = int((col_after == "0").sum())
        cnt_empty_after = int((col_after == "").sum())

        log(f"[Block 1] Folder files: {in_folder}")
        log(f"[Block 1] Excel before  -> 1:{cnt_1_before}  0:{cnt_0_before}  empty:{cnt_empty_before}")
        log(f"[Block 1] Updates applied: {updates_applied}")
        log(f"[Block 1] Excel after   -> 1:{cnt_1_after}  0:{cnt_0_after}  empty:{cnt_empty_after}")

        if unmatched_in_folder:
            preview = list(sorted(unmatched_in_folder))[:50]
            log(f"[Block 1] In folder not applied (count={len(unmatched_in_folder)}). Examples:")
            for s in preview:
                log("   ", s)

        messagebox.showinfo(
            "Sync done",
            f"Folder files: {in_folder}\n"
            f"Excel before  -> 1:{cnt_1_before}  0:{cnt_0_before}  empty:{cnt_empty_before}\n"
            f"Updated to 1: {updates_applied}\n"
            f"Excel after   -> 1:{cnt_1_after}  0:{cnt_0_after}  empty:{cnt_empty_after}\n"
            f"Not applied in this pass: {len(unmatched_in_folder)} (see console).",
        )

    # ===================================================================
    # Block 2 — main run
    # ===================================================================
    def start(self) -> None:
        global abort_now, save_requested
        abort_now = False
        save_requested = False

        p = self.excel_path_var.get().strip()
        if not p:
            messagebox.showerror("Error", "Pick an Excel file first."); return
        excel_path = Path(p)
        if not excel_path.exists():
            messagebox.showerror("Error", f"File not found:\n{excel_path}"); return

        df_main = load_and_prepare_excel(
            excel_path,
            status_column="SI Downloaded",
            write_back=True,
            apply_links=False,
            normalize_status=True,
            log=log,
        )

        work = df_main[["DOI", "DOI Link", "SI Downloaded"]].copy()
        work["DOI"]            = work["DOI"].astype(str).str.strip()
        work["SI Downloaded"]  = work["SI Downloaded"].apply(status_norm)
        work["TargetStem"]     = work["DOI"].apply(doi_stem)

        s_col = work["SI Downloaded"]
        self.succ_count = int((s_col == "1").sum())
        self.fail_count = int((s_col == "0").sum())

        self.start_anti_idle()

        self.root.update(); self.root.geometry("320x120+0+0"); self.root.iconify()

        def worker():
            try:
                self.process_rows(df_main, work, excel_path, self.double_check_var.get())
                self.ui_queue.put(("status", "Done."));    self.ui_queue.put(("restore", None))
            except SystemExit:
                self.ui_queue.put(("status", "Stopped.")); self.ui_queue.put(("restore", None))
            except Exception as e:
                log("Worker error:", e)
                self.ui_queue.put(("status", f"Error: {e}")); self.ui_queue.put(("restore", None))
            finally:
                try:
                    self.stop_anti_idle()
                except Exception:
                    pass
                ensure_chrome_closed(log=log)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def stop_now(self) -> None:
        global abort_now, save_requested
        save_requested = True
        abort_now = True
        self.ui_queue.put(("status", "STOP now requested."))
        log("STOP requested")

    def process_rows(self, df_main: pd.DataFrame, work: pd.DataFrame, excel_path: Path, double_check_mode: bool) -> None:
        global save_requested

        si_dir       = ensure_download_dir(excel_path, name="SI downloaded")
        coords_save  = tuple(load_calibration(CAL_FILE).get("GLOBAL_SAVE", {}).get("save_xy") or [])
        if not coords_save or len(coords_save) != 2:
            raise SystemExit("Global FILE NAME BOX XY not set.")

        icon_dir = excel_path.parent / "icon"
        if not icon_dir.exists():
            raise SystemExit(f"Icon folder not found:\n{icon_dir}\nPut SI icons in this folder.")

        col_raw = work["SI Downloaded"]
        if double_check_mode:
            pending_mask   = (col_raw == "0")
            total_to_check = int(pending_mask.sum())
            log(f"[Block 2] Double check mode: total rows with 0 = {total_to_check}")
        else:
            pending_mask   = ~(col_raw.isin(["0", "1"]))
            total_to_check = int(pending_mask.sum())
            log(f"[Block 2] Normal mode: total pending empties = {total_to_check}")

        pending_indices = work.index[pending_mask].tolist()
        self.pending_set = set(pending_indices)
        self.start_time  = time.time()
        processed_pending_since_save = 0
        processed_since_start        = 0

        # Per-journal counters
        j_fail_counts:    Dict[str, int] = {}
        j_success_counts: Dict[str, int] = {}

        def record_fail(jkey: str) -> None:
            if jkey:
                j_fail_counts[jkey] = j_fail_counts.get(jkey, 0) + 1

        def record_success(jkey: str) -> None:
            if jkey:
                j_success_counts[jkey] = j_success_counts.get(jkey, 0) + 1

        def allowed_fail_limit(jkey: str) -> int:
            base = MAX_JOURNAL_FAILS_BASE
            succ = j_success_counts.get(jkey, 0)
            return base * (JOURNAL_SUCCESS_BOOST_MULTIPLIER if succ > JOURNAL_SUCCESS_THRESHOLD_FOR_BOOST else 1)

        def flush(force: bool = False) -> None:
            nonlocal processed_pending_since_save
            global save_requested
            if processed_pending_since_save >= SAVE_EVERY_PENDING or save_requested or force:
                df_out = df_main.copy()
                df_out["SI Downloaded"] = work["SI Downloaded"]
                save_progress(df_out, excel_path, apply_links=(APPLY_HYPERLINKS_ON_FINAL_SAVE and force), log=log)
                log("[Block 2] Saved workbook (batch)")
                processed_pending_since_save = 0
                save_requested = False

        def update_stats() -> None:
            left    = len(self.pending_set)
            elapsed = max(time.time() - self.start_time, 1.0)
            done    = max(processed_since_start, 1)
            eta_secs = int(left * elapsed / done)
            self.ui_queue.put(("stats", {
                "left": left, "succ": self.succ_count, "fail": self.fail_count, "eta_secs": eta_secs
            }))

        update_stats()

        try:
            for idx in pending_indices:
                if abort_now:
                    raise SystemExit("Aborted")
                if idx not in self.pending_set:
                    continue

                doi        = work.at[idx, "DOI"]
                pub_key    = publisher_key(df_main.at[idx, "Publisher"], use_aliases=True)
                jkey       = doi_journal_key(doi)
                initial_si = work.at[idx, "SI Downloaded"]

                log(f"[Row {idx}] start DOI='{doi}' Pub='{pub_key}' JKey='{jkey}'")

                if jkey:
                    allowed = allowed_fail_limit(jkey)
                    if j_fail_counts.get(jkey, 0) >= allowed:
                        log(f"[Row {idx}] skip journal threshold (fails={j_fail_counts.get(jkey, 0)} allowed={allowed})")
                        self.pending_set.discard(idx); update_stats()
                        continue

                target_base = (si_dir / work.at[idx, "TargetStem"]).resolve()
                link        = doi_to_link(doi)
                work.at[idx, "DOI Link"] = link

                # File already on disk?
                existing = fresh_file_ready_any(target_base, timeout=0.3, abort_flag=_abort)
                if existing:
                    work.at[idx, "SI Downloaded"] = "1"
                    self.succ_count += 1; record_success(jkey)
                    log(f"[Row {idx}] already saved -> mark 1 ({existing.name})")
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    processed_pending_since_save += 1
                    flush()
                    update_stats()
                    ensure_chrome_closed(log=log)
                    continue

                ok            = False
                skip_row      = False
                attempted_flow = False

                for attempt in range(1, MAX_RETRIES_PER_ROW + 1):
                    if abort_now:
                        raise SystemExit("Aborted")
                    log(f"[Row {idx}] attempt {attempt}/{MAX_RETRIES_PER_ROW}")
                    try:
                        ensure_chrome_closed(log=log)
                        safe_reset_to_desktop(include_enter=True, log=log)
                        open_in_chrome("about:blank", new_window=True, browser_open_wait=BROWSER_OPEN_WAIT, log=log)
                        time.sleep(BROWSER_OPEN_WAIT)
                        go_to_address_bar_and_open(link, wait_after_nav=WAIT_AFTER_NAV, abort_flag=_abort, log=log)
                        move_cursor_top_center()
                        flow = PUBLISHER_FLOW.get(pub_key) if pub_key else None
                        if not flow:
                            ok = False
                        else:
                            attempted_flow = True
                            res = flow(icon_dir, coords_save, target_base)
                            if res == "SKIP":
                                log(f"[Row {idx}] anchor not found -> SKIP (keep empty)")
                                skip_row = True; ok = False
                            else:
                                ok = bool(res)
                    except Exception as e:
                        log(f"[Row {idx}] error: {e}")
                        ok = False
                    finally:
                        ensure_chrome_closed(log=log)
                        safe_reset_to_desktop(include_enter=True, log=log)
                        move_cursor_top_center()
                    log(f"[Row {idx}] result attempt {attempt}: {ok}{' (SKIP)' if skip_row else ''}")
                    if skip_row or ok:
                        break

                if skip_row:
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    update_stats()
                    ensure_chrome_closed(log=log)
                    continue

                if ok and fresh_file_ready_any(target_base, timeout=1.0, abort_flag=_abort):
                    work.at[idx, "SI Downloaded"] = "1"
                    self.succ_count += 1; record_success(jkey)
                    log(f"[Row {idx}] mark 1")
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    processed_pending_since_save += 1
                    flush()
                    update_stats()
                    ensure_chrome_closed(log=log)
                    continue

                if attempted_flow:
                    work.at[idx, "SI Downloaded"] = "0"
                    self.fail_count += 1; record_fail(jkey)
                    log(f"[Row {idx}] mark 0 (flow tried and failed)")
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    processed_pending_since_save += 1
                    flush()
                    update_stats()
                    ensure_chrome_closed(log=log)
                    continue

                log(f"[Row {idx}] no flow attempted -> keep as '{initial_si}'")
                self.pending_set.discard(idx)
                processed_since_start += 1
                update_stats()
                ensure_chrome_closed(log=log)

        finally:
            flush(force=True)
            update_stats()
            ensure_chrome_closed(log=log)
            log("[Block 2] All done")


# ===========================================================================
# 7. Boot
# ===========================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app  = App(root)
    root.mainloop()
