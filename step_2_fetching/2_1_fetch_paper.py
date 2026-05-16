"""
Step 2.1 — Fetch main-article PDFs from publisher websites
==========================================================
What it does
    A Tkinter app that walks each row of an Excel paper list and downloads
    the main-article PDF from the publisher's website by automating Chrome
    via PyAutoGUI. For each pending row it:

        1. opens ``https://doi.org/<DOI>`` in a fresh incognito Chrome window;
        2. matches the publisher to one of WILEY / AMER CHEMICAL SOC /
           ROYAL SOC CHEMISTRY / SPRINGER / ELSEVIER;
        3. runs the recorded click sequence for that publisher OR (if the
           "ICON" toggle is on) finds publisher icons on screen and clicks
           them in order;
        4. drives the native Save As dialog to write the PDF to
           ``./downloaded/<doi-safe>.pdf``;
        5. marks the Excel row ``Downloaded = '1'`` on success, ``'0'`` on
           failure, and saves the workbook every ``SAVE_EVERY`` rows.

Input
    An ``.xlsx`` with at least the columns ``DOI`` and ``Publisher``. The
    file is selected through the GUI; the path is remembered across
    sessions in ``app_settings.json``.

Output
    ``./downloaded/<doi-with-_>.pdf``  — one PDF per successful row.
    The input Excel is rewritten in place with two columns added /
    refreshed: ``DOI Link`` (hyperlink) and ``Downloaded`` ('1' / '0' /
    blank). Rows are resume-safe — rerunning only attempts rows whose
    ``Downloaded`` is still blank.

Where data flows
    Default input  : ``<repo>/data/ground truth open access 500.xlsx`` —
                     the ~500-paper open-access subset originally used
                     for the ground-truth labeling campaign. Override
                     via Browse; the last-opened path is remembered in
                     ``app_settings.json`` next to this script.
    Default output : ``<excel_folder>/downloaded/<doi>.pdf`` — i.e.
                     ``<repo>/data/downloaded/`` if the default input is
                     used. This is exactly the folder
                     ``step_1_literature_classification/1_2_classify_pdf.py``
                     reads (``--input-folder downloaded`` relative to a
                     ``cwd=data/``), so Step 2.1's output feeds straight
                     into Step 1.2's input.

Calibration (one-time per workstation)
    Two things must be calibrated before the first run:
      - Per-publisher click sequence: open a sample page for the
        publisher and press F8 at each click target, then F9 to finish.
        Stored in ``doi_downloader_calibration.json`` next to this script.
      - Save dialog filename box: open any Save As dialog, hover over the
        File Name text box, press F8 then F9.

Hotkeys
    Ctrl+Shift+S  — save progress now
    Ctrl+Shift+X  — STOP NOW (raises SystemExit in the worker thread)

File layout (numbered sections below)
    1. Quick settings (timeouts, retries, save cadence)
    2. Constants (publishers, sample URLs, default coords)
    3. Globals + log
    4. Local-only helpers (sleep_check_abort, finalize)
    5. Per-row automation (run_actions_then_save, run_icons_then_save)
    6. Tkinter App
    7. Boot

Reusable bits live in ``utils/`` — DOI helpers, Chrome control, on-screen
icon matching, the Save-As dialog driver, Excel I/O, and the JSON
calibration store.

Requirements
    pip install pandas openpyxl pyautogui pyperclip pillow pynput opencv-python
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional, Set

import pandas as pd
import pyautogui
from pynput import keyboard as pynput_keyboard

from utils.calibration import capture_f8_f9_points, load_calibration, save_calibration
from utils.chrome import (
    IS_MAC,
    IS_WIN,
    close_all_chrome,
    go_to_address_bar_and_open,
    hotkey_save,
    open_in_chrome,
)
from utils.desktop import reset_to_desktop
from utils.doi import (
    SUPPORTED_PREFIXES,
    doi_journal_key,
    doi_to_filename,
    doi_to_link,
    publisher_key,
)
from utils.excel_io import (
    apply_hyperlinks,
    ensure_download_dir,
    load_and_prepare_excel,
    save_progress,
)
from utils.icons import list_icon_sequence, locate_center_on_screen
from utils.save_dialog import fresh_file_ready

import pyperclip  # noqa: F401 — used indirectly via utils.chrome; explicit import keeps deps obvious


pyautogui.FAILSAFE = True


# ===========================================================================
# 1. Quick settings — adjust these to tune timing without touching the loop
# ===========================================================================
BROWSER_OPEN_WAIT             = 2.0   # seconds after opening Chrome before pasting link
WAIT_AFTER_NAV                = 4.0   # seconds after pressing Enter on the address bar
INTER_CLICK_DELAY             = 5.0   # seconds between coordinate-based action steps (track mode)
WAIT_AFTER_PDF                = 5.0   # seconds after the final click before saving (track mode)
STEP_PAUSE                    = 0.5   # seconds between actions inside the Save dialog
ICON_ACTION_PAUSE             = 1.0   # seconds between every single action in ICON mode
ICON_WAIT_AFTER_FIRST_CLICK   = 6.0   # seconds to wait *after the first icon click* in ICON mode
DESKTOP_RESET_PAUSE           = 0.5   # seconds between Win+D, Enter, and center click
SAVE_EVERY                    = 4     # extra periodic save safety
MAX_RETRIES                   = 2     # attempts per row

# Icon mode tuning
ICON_CONFIDENCE               = 0.87  # template match confidence
ICON_SEARCH_DELAY             = 0.7   # seconds between icon search tries
MAX_ICON_SEARCH_TIME          = 10.0  # max seconds to search for each icon
ICON_GAP_BEFORE_NEXT          = 5.0   # wait before searching the NEXT icon (when >= 2 steps)
ICON_BEFORE_RENAME_WAIT       = 2.0   # wait after the last icon click before rename/save

# Journal fast-skip
MAX_JOURNAL_FAILS             = 20    # after N fails on a journal key, skip more rows for it this run


# ===========================================================================
# 2. Constants — supported publishers, sample URLs, fallback coordinates
# ===========================================================================
SAMPLE_URLS = {
    "WILEY":               "https://advanced.onlinelibrary.wiley.com/doi/10.1002/adfm.202410751",
    "AMER CHEMICAL SOC":   "https://doi.org/10.1021/acs.chemmater.9b02322",
    "ROYAL SOC CHEMISTRY": "https://doi.org/10.1039/D3QI00391D",
    "SPRINGER":            "https://www.nature.com/articles/s41467-025-64092-9",
    "ELSEVIER":            "https://www.sciencedirect.com/science/article/pii/S0001868622001348",
}

# Fallback single-click coordinates per publisher (used only if the user has
# not recorded a click path AND ICON mode is off / unavailable).
DEFAULT_CAL = {
    "WILEY":               {"pdf_xy": [918, 830]},
    "AMER CHEMICAL SOC":   {"pdf_xy": [325, 582]},
    "ROYAL SOC CHEMISTRY": {"pdf_xy": [1297, 329]},
    "SPRINGER":            {"pdf_xy": [1328, 452]},
    "ELSEVIER":            {"pdf_xy": [687, 218]},
}

DEFAULT_GLOBAL_SAVE_XY = [425, 393]   # fallback FILE NAME BOX coordinates

# Both JSON files live next to this script so cwd doesn't matter.
_SCRIPT_DIR  = Path(__file__).resolve().parent
CAL_FILE     = str(_SCRIPT_DIR / "doi_downloader_calibration.json")
APP_SETTINGS = str(_SCRIPT_DIR / "app_settings.json")

# Default input Excel = the curated ~500-paper open-access subset used in
# the ground-truth labeling campaign. Lives under <repo>/data/; the
# downloads land in <excel_folder>/downloaded/ — i.e. <repo>/data/downloaded/
# — which is exactly where Step 1.2 looks ("--input-folder downloaded" from
# cwd=data/). Override via the Browse button if you keep the list elsewhere.
_REPO_ROOT         = _SCRIPT_DIR.parent
DEFAULT_EXCEL_PATH = str(_REPO_ROOT / "data" / "ground truth open access 500.xlsx")


# ===========================================================================
# 3. Module globals + log
# ===========================================================================
abort_now      = False    # set by STOP NOW hotkey / button; checked in tight loops
save_requested = False    # set by "save now" hotkey; flushes the workbook ASAP


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
def sleep_check_abort(seconds: float) -> None:
    """time.sleep(seconds) but raise SystemExit immediately if abort_now is set."""
    t_end = time.time() + seconds
    while time.time() < t_end:
        if abort_now:
            raise SystemExit("Aborted")
        time.sleep(0.1)


def finalize_save_and_reset_track(target_path: Path) -> bool:
    """
    After typing the filename into the Save dialog, press Enter twice and
    reset to desktop. Returns True if the file appeared within 5 seconds.
    """
    log("Finalize (track): Enter x2 -> desktop reset -> quick check")
    pyautogui.press("enter"); time.sleep(STEP_PAUSE)
    pyautogui.press("enter")
    reset_to_desktop(include_enter=True, pause=DESKTOP_RESET_PAUSE)
    ok2 = fresh_file_ready(target_path, timeout=5, abort_flag=_abort)
    log("Quick file check:", ok2)
    return ok2


def _load_cal_with_defaults() -> dict:
    """Load calibration JSON, seeding any missing publisher/global keys from defaults."""
    defaults = {name: dict(sub) for name, sub in DEFAULT_CAL.items()}
    defaults["GLOBAL_SAVE"] = {"save_xy": list(DEFAULT_GLOBAL_SAVE_XY)}
    defaults["ICON_MODE"]   = {k: False for k in SUPPORTED_PREFIXES}
    return load_calibration(CAL_FILE, defaults=defaults)


# ===========================================================================
# 5. Per-row automation — TRACK mode (recorded clicks) and ICON mode
# ===========================================================================
def run_actions_then_save(actions, target_path: Path, coords_save_xy) -> bool:
    """
    Execute a list of recorded click steps, then drive the Save dialog.

    ``actions`` is a list of ``{"type": "click", "x": int, "y": int, "wait": float}``
    dicts captured during calibration. Returns True iff the PDF lands on disk.
    """
    log("TRACK steps:", len(actions))
    if abort_now:
        raise SystemExit("Aborted")

    for i, step in enumerate(actions, 1):
        if abort_now:
            raise SystemExit("Aborted")
        if step.get("type") == "click":
            x, y = step.get("x"), step.get("y")
            log(f"TRACK click {i}/{len(actions)} at ({x},{y})")
            pyautogui.moveTo(int(x), int(y), duration=0.25); time.sleep(0.15)
            pyautogui.click()
            sleep_check_abort(step.get("wait", INTER_CLICK_DELAY))

    log("TRACK wait then Ctrl+S:", WAIT_AFTER_PDF, "s")
    sleep_check_abort(WAIT_AFTER_PDF)

    sx, sy = coords_save_xy
    log("TRACK rename at", (sx, sy), "->", target_path.name)
    hotkey_save();                                                 time.sleep(STEP_PAUSE)
    pyautogui.moveTo(int(sx), int(sy), duration=0.2);              time.sleep(STEP_PAUSE)
    pyautogui.click();                                             time.sleep(STEP_PAUSE)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a");        time.sleep(STEP_PAUSE)
    pyautogui.press("delete");                                     time.sleep(STEP_PAUSE)
    pyperclip.copy(str(target_path))
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v");        time.sleep(STEP_PAUSE)

    ok = fresh_file_ready(target_path, timeout=90, abort_flag=_abort) \
        if finalize_save_and_reset_track(target_path) else False
    log("TRACK result:", ok)
    return ok


def run_icons_then_save(icon_images, target_path: Path, coords_save_xy) -> bool:
    """
    Find each icon image on screen in order, click it, then rename + save.

    Used when ICON mode is enabled for a publisher and the icon folder
    next to the Excel file has matching template files.
    """
    log("ICON steps:", [p.name for p in icon_images])
    if abort_now:
        raise SystemExit("Aborted")

    micro = ICON_ACTION_PAUSE
    attempts_per_icon = max(1, int(MAX_ICON_SEARCH_TIME / ICON_SEARCH_DELAY))

    for idx, img in enumerate(icon_images):
        if idx > 0:
            log(f"ICON gap before next: {ICON_GAP_BEFORE_NEXT}s")
            sleep_check_abort(ICON_GAP_BEFORE_NEXT)

        found = None
        for attempt in range(1, attempts_per_icon + 1):
            found = locate_center_on_screen(img, ICON_CONFIDENCE, log=log)
            if found:
                log(f"ICON found {img.name} at {found} (attempt {attempt})")
                break
            if attempt % int(max(1, 2 / ICON_SEARCH_DELAY)) == 0:
                log(f"ICON searching {img.name}... attempt {attempt}")
            time.sleep(ICON_SEARCH_DELAY)

        if not found:
            log("ICON NOT found:", img.name)
            return False
        pyautogui.moveTo(found[0], found[1], duration=0.25); time.sleep(micro)
        pyautogui.click(); time.sleep(micro)
        if idx == 0 and ICON_WAIT_AFTER_FIRST_CLICK > 0:
            log(f"ICON wait after FIRST click: {ICON_WAIT_AFTER_FIRST_CLICK}s")
            sleep_check_abort(ICON_WAIT_AFTER_FIRST_CLICK)

    log("ICON wait before rename:", ICON_BEFORE_RENAME_WAIT, "s")
    sleep_check_abort(ICON_BEFORE_RENAME_WAIT)

    sx, sy = coords_save_xy
    log("ICON rename at", (sx, sy), "->", target_path.name)
    pyautogui.moveTo(int(sx), int(sy), duration=0.2);             time.sleep(micro)
    pyautogui.click();                                            time.sleep(micro)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a");       time.sleep(micro)
    pyautogui.press("delete");                                    time.sleep(micro)
    pyperclip.copy(str(target_path))
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v");       time.sleep(micro)
    pyautogui.press("enter");                                     time.sleep(micro)
    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2);                              time.sleep(micro)
    pyautogui.press("enter");                                     time.sleep(micro)

    if IS_WIN:
        log("ICON desktop reset")
        pyautogui.hotkey("winleft", "d");                         time.sleep(micro)
        pyautogui.press("enter");                                 time.sleep(micro)
        pyautogui.click(w // 2, h // 2);                          time.sleep(micro)

    ok = fresh_file_ready(target_path, timeout=90, abort_flag=_abort)
    log("ICON result:", ok)
    return ok


# ===========================================================================
# 6. Tkinter App — UI, calibration capture, worker thread
# ===========================================================================
class App:
    """
    Full UI: file picker, per-publisher row (record/sample/ICON toggle),
    global Save-box capture, Start/Stop, live stats, mouse tracker.

    The download loop runs on a worker thread; the UI thread updates from
    ``ui_queue``. ``abort_now`` and ``save_requested`` are module globals
    so the hotkey listener can flip them from anywhere.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("DOI auto downloader")

        self.ui_queue       = queue.Queue()
        self.excel_path_var = tk.StringVar(value=self._load_last_excel() or DEFAULT_EXCEL_PATH)
        self.status_var     = tk.StringVar(value="Ready")
        self.stats_var      = tk.StringVar(value="Left: 0  Success: 0  Fail: 0  ETA: 00:00")
        self.cal_data       = _load_cal_with_defaults()

        self.icon_counts        = {k: 0 for k in SUPPORTED_PREFIXES}
        self.pub_info_vars      = {k: tk.StringVar(value=self.pub_info_text(k)) for k in SUPPORTED_PREFIXES}
        self.icon_mode_vars     = {k: tk.BooleanVar(value=self.cal_data.get("ICON_MODE", {}).get(k, False)) for k in SUPPORTED_PREFIXES}
        self.icon_mode_widgets: Dict[str, ttk.Checkbutton] = {}
        self.save_box_var       = tk.StringVar(value=self.save_box_text())

        # Journal fail tracking (in-memory, reset each run).
        self.journal_fail_counts: Dict[str, int] = {}
        self.skip_journal_keys: Set[str]         = set()

        # ---- layout ----
        pad = 6
        frm = ttk.Frame(root, padding=pad); frm.pack(fill="both", expand=True)

        row_file = ttk.Frame(frm); row_file.pack(fill="x", pady=(pad, 0))
        ttk.Label(row_file, text="Excel file:").pack(side="left")
        ttk.Entry(row_file, textvariable=self.excel_path_var, width=90).pack(side="left", padx=(pad, pad))
        ttk.Button(row_file, text="Browse", command=self.pick_file).pack(side="left")

        ttk.Label(frm, text="Publishers").pack(anchor="w", pady=(pad, 0))
        self.rows = {}
        for name in SUPPORTED_PREFIXES:
            r = ttk.Frame(frm); r.pack(fill="x", pady=2); self.rows[name] = r
            ttk.Label(r, text=name, width=18).grid(row=0, column=0, sticky="w")
            cb = ttk.Checkbutton(
                r, text="Icon mode",
                variable=self.icon_mode_vars[name],
                command=lambda n=name: self.toggle_icon_mode(n),
            )
            cb.grid(row=0, column=1, sticky="w", padx=4)
            self.icon_mode_widgets[name] = cb
            ttk.Label(r, textvariable=self.pub_info_vars[name], width=70, anchor="w").grid(row=0, column=2, sticky="w")
            ttk.Button(r, text="Record actions (F8 add, F9 finish)",
                       command=lambda n=name: self.capture_actions(n)).grid(row=0, column=3, padx=4, sticky="w")
            ttk.Button(r, text="Open sample page",
                       command=lambda n=name: self.open_sample(n)).grid(row=0, column=4, padx=4)

        ttk.Label(frm, text="Save dialog filename box").pack(anchor="w", pady=(pad, 0))
        row_save = ttk.Frame(frm); row_save.pack(fill="x", pady=2)
        ttk.Label(row_save, textvariable=self.save_box_var, width=40, anchor="w").pack(side="left")
        ttk.Button(row_save, text="Set FILE NAME box XY (F8)", command=self.capture_global_save_xy).pack(side="left", padx=6)

        ctrl = ttk.Frame(frm); ctrl.pack(fill="x", pady=(pad, 0))
        ttk.Button(ctrl, text="Start",    command=self.start).pack(side="left", padx=(0, pad))
        ttk.Button(ctrl, text="STOP now", command=self.stop_now).pack(side="left")

        ttk.Label(frm, textvariable=self.stats_var).pack(fill="x", pady=(pad, 0))
        ttk.Label(frm, textvariable=self.status_var).pack(fill="x", pady=(pad, 0))

        tracker = ttk.Frame(frm); tracker.pack(fill="x", pady=(pad, 0))
        self.mouse_xy_var = tk.StringVar(value="Mouse XY: ...")
        self.track_mouse  = tk.BooleanVar(value=False)
        ttk.Checkbutton(tracker, text="Track mouse XY", variable=self.track_mouse,
                        command=self.update_mouse_tracker).pack(side="left")
        ttk.Label(tracker, textvariable=self.mouse_xy_var).pack(side="left", padx=8)

        ttk.Label(frm, text="Hotkeys: Ctrl+Shift+S save now, Ctrl+Shift+X STOP now.").pack(fill="x", pady=(pad, 0))

        self.start_hotkeys()
        self.root.after(150, self.poll_ui)
        self.root.after(120, self.update_mouse_tracker)

        self.refresh_icon_availability()

    # ---- persistence of the last-opened Excel path ----
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

    # ---- icon-folder availability ----
    def get_icon_dir(self) -> Optional[Path]:
        excel_path = self.excel_path_var.get().strip()
        if excel_path:
            return Path(excel_path).parent / "icon"
        return None

    def refresh_icon_availability(self) -> None:
        icon_dir = self.get_icon_dir()
        for name in SUPPORTED_PREFIXES:
            count, available = 0, False
            if icon_dir and icon_dir.exists():
                imgs = list_icon_sequence(name, icon_dir, log=log)
                count, available = len(imgs), len(imgs) > 0
            self.icon_counts[name] = count
            widget = self.icon_mode_widgets.get(name)
            if widget:
                if available:
                    widget.state(["!disabled"])
                else:
                    widget.state(["disabled"])
                    self.icon_mode_vars[name].set(False)
                    self.cal_data.setdefault("ICON_MODE", {})[name] = False
            self.update_pub_info_label(name)
        save_calibration(CAL_FILE, self.cal_data)

    # ---- UI labels ----
    def update_mouse_tracker(self) -> None:
        if self.track_mouse.get():
            p = pyautogui.position()
            self.mouse_xy_var.set(f"Mouse XY: ({p.x}, {p.y})")
            self.root.after(120, self.update_mouse_tracker)

    def pub_info_text(self, name: str) -> str:
        d         = self.cal_data.get(name, {})
        icon_mode = self.cal_data.get("ICON_MODE", {}).get(name, False)
        mode      = "ICON" if icon_mode else "ACTIONS"
        icon_steps = self.icon_counts.get(name, 0)
        if "actions" in d and d["actions"]:
            act_count = len(d["actions"])
        elif "click_path" in d and d["click_path"]:
            act_count = len(d["click_path"])
        else:
            act_count = 0
        pdf      = tuple(d.get("pdf_xy")) if d.get("pdf_xy") else None
        fallback = f"Fallback XY: {pdf}" if pdf else "Fallback XY: None"
        return f"{mode} | Icon steps: {icon_steps} | Actions: {act_count} | {fallback}"

    def save_box_text(self) -> str:
        g   = self.cal_data.get("GLOBAL_SAVE", {})
        sav = tuple(g.get("save_xy")) if g.get("save_xy") else None
        return f"FILE NAME BOX XY: {sav}"

    def update_pub_info_label(self, name: str) -> None:
        self.pub_info_vars[name].set(self.pub_info_text(name))

    def update_save_box_label(self) -> None:
        self.save_box_var.set(self.save_box_text())

    # ---- toggles + pickers ----
    def toggle_icon_mode(self, name: str) -> None:
        self.cal_data.setdefault("ICON_MODE", {})[name] = bool(self.icon_mode_vars[name].get())
        save_calibration(CAL_FILE, self.cal_data)
        self.update_pub_info_label(name)

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(title="Pick Excel file", filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            self.excel_path_var.set(path)
            self._save_last_excel(path)
            self.refresh_icon_availability()

    # ---- sample + calibration capture ----
    def open_sample(self, name: str) -> None:
        url = SAMPLE_URLS.get(name, "about:blank")
        open_in_chrome("about:blank", new_window=True, browser_open_wait=BROWSER_OPEN_WAIT, log=log)
        time.sleep(BROWSER_OPEN_WAIT)
        go_to_address_bar_and_open(url, wait_after_nav=WAIT_AFTER_NAV, abort_flag=_abort, log=log)

    def capture_actions(self, name: str) -> None:
        win = tk.Toplevel(self.root); win.title(f"Record actions: {name}")
        win.geometry("660x240+100+60"); win.attributes("-topmost", True)
        info = (
            f"{name}\n\n"
            "1) Click Open sample page if needed.\n"
            "2) Move to each clickable target.\n"
            "3) Press F8 to add each step, press F9 to finish."
        )
        ttk.Label(win, text=info, justify="left", wraplength=630).pack(padx=10, pady=8, fill="x")
        count_var = tk.StringVar(value="Captured steps: 0")
        ttk.Label(win, textvariable=count_var).pack(pady=(0, 6))
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)

        points = capture_f8_f9_points(
            pump_ui=self.root.update,
            on_each=lambda n: count_var.set(f"Captured steps: {n}"),
        )
        win.destroy()
        if not points:
            messagebox.showwarning("Actions", "No steps captured."); return
        actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY} for (x, y) in points]
        self.cal_data.setdefault(name, {})["actions"]    = actions
        self.cal_data[name]["click_path"]                = [list(p) for p in points]
        save_calibration(CAL_FILE, self.cal_data)
        self.update_pub_info_label(name)
        messagebox.showinfo("Saved", f"{name} actions saved with {len(actions)} step(s).")

    def capture_global_save_xy(self) -> None:
        messagebox.showinfo("Save-box capture", "Open any Save dialog. Hover FILE NAME box, press F8. Press F9 to finish.")
        points = capture_f8_f9_points(pump_ui=self.root.update)
        if not points:
            messagebox.showwarning("Save-box", "No position captured."); return
        pos = points[-1]
        self.cal_data.setdefault("GLOBAL_SAVE", {})["save_xy"] = [int(pos[0]), int(pos[1])]
        save_calibration(CAL_FILE, self.cal_data)
        self.update_save_box_label()
        messagebox.showinfo("Saved", f"FILE NAME BOX XY saved at {pos}")

    # ---- run control ----
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

        try:
            df = load_and_prepare_excel(
                excel_path,
                status_column="Downloaded",
                write_back=True,
                apply_links=True,
                normalize_status=False,
                log=log,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e)); return

        self.refresh_icon_availability()

        # Pending = anything not exactly '1' / '0'.
        col_raw      = df["Downloaded"]
        pending_mask = col_raw.isna() | (col_raw.astype(str).str.strip() == "")
        pending_indices = df.index[pending_mask].tolist()
        self.pending_set = set(pending_indices)

        succ = (col_raw.astype(str).str.strip() == "1").sum()
        fail = (col_raw.astype(str).str.strip() == "0").sum()

        self.initial_done = succ + fail
        self.start_time   = time.time()
        self.ui_queue.put(("stats", {"left": len(self.pending_set), "succ": succ, "fail": fail, "eta_secs": 0}))
        self.ui_queue.put(("status", "Running."))
        log("Start run. Pending rows:", len(self.pending_set))

        self.root.update(); self.root.geometry("320x120+0+0"); self.root.iconify()

        def worker():
            try:
                self.process_rows(df, excel_path, pending_indices)
                self.ui_queue.put(("status", "Done."));    self.ui_queue.put(("restore", None))
            except SystemExit:
                self.ui_queue.put(("status", "Stopped.")); self.ui_queue.put(("restore", None))
            except Exception as e:
                log("Worker error:", e)
                self.ui_queue.put(("status", f"Error: {e}")); self.ui_queue.put(("restore", None))

        self.worker = threading.Thread(target=worker, daemon=True); self.worker.start()

    def stop_now(self) -> None:
        global abort_now
        abort_now = True
        self.ui_queue.put(("status", "STOP now requested."))
        log("STOP requested")

    def start_hotkeys(self) -> None:
        def on_save():
            global save_requested
            save_requested = True
            log("Hotkey save requested")
        def on_stop_now():
            global abort_now
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
                    h, m = divmod((payload.get("eta_secs", 0) // 60), 60)
                    self.stats_var.set(f"Left: {left}  Success: {succ}  Fail: {fail}  ETA: {h:02d}:{m:02d}")
                elif kind == "restore":
                    try:
                        self.root.deiconify(); self.root.lift()
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.root.after(150, self.poll_ui)

    # ---- journal-fail tracking ----
    def _bump_journal_fail(self, journal_key: str) -> None:
        if not journal_key:
            return
        cnt = self.journal_fail_counts.get(journal_key, 0) + 1
        self.journal_fail_counts[journal_key] = cnt
        log(f"Journal key '{journal_key}' fail count -> {cnt}/{MAX_JOURNAL_FAILS}")
        if cnt >= MAX_JOURNAL_FAILS:
            self.skip_journal_keys.add(journal_key)
            log(f"Journal key '{journal_key}' reached max fails. Will skip further rows for this journal this run.")

    # ---- main worker ----
    def process_rows(self, df: pd.DataFrame, excel_path: Path, indices) -> None:
        global save_requested

        ensure_download_dir(excel_path, name="downloaded")
        processed_since_save  = 0
        start_ts              = time.time()
        processed_since_start = 0

        coords_save = self.cal_data.get("GLOBAL_SAVE", {}).get("save_xy")
        if not coords_save:
            raise SystemExit("Global FILE NAME BOX XY not set.")
        icon_dir = self.get_icon_dir()

        for idx in indices:
            if abort_now:
                raise SystemExit("Aborted")
            if idx not in self.pending_set:
                continue

            row     = df.iloc[idx]
            doi     = str(row.get("DOI", "")).strip()
            pub_key = publisher_key(row.get("Publisher", ""))
            jkey    = doi_journal_key(doi)

            # Journal-wide fast skip
            if jkey and jkey in self.skip_journal_keys:
                log(f"Row {idx} skipped due to journal key '{jkey}' reached max fails")
                self.pending_set.discard(idx)
                self._update_stats(df, start_ts, processed_since_start)
                continue

            log(f"Row {idx} start. DOI='{doi}' Publisher='{pub_key}' JournalKey='{jkey}'")

            # Bad DOI / unknown publisher -> mark 0 and move on
            if not doi or not pub_key:
                df.at[idx, "Downloaded"] = "0"
                save_progress(df, excel_path, apply_links=True, log=log)
                self._bump_journal_fail(jkey)
                self.pending_set.discard(idx)
                processed_since_start += 1
                self._update_stats(df, start_ts, processed_since_start)
                continue

            # Already on disk -> mark 1, no automation needed
            target_path = (excel_path.parent / "downloaded" / doi_to_filename(doi)).resolve()
            if target_path.exists() and target_path.stat().st_size > 0:
                log(f"Row {idx} file already exists -> mark 1 (no actions)")
                df.at[idx, "Downloaded"] = "1"
                save_progress(df, excel_path, apply_links=True, log=log)
                self.pending_set.discard(idx)
                processed_since_start += 1
                self._update_stats(df, start_ts, processed_since_start)
                continue

            link = doi_to_link(doi)
            df.at[idx, "DOI Link"] = link

            # Pick ICON sequence if available + enabled, else fall back to recorded clicks.
            icon_images = (
                list_icon_sequence(pub_key, icon_dir, log=log)
                if (self.cal_data.get("ICON_MODE", {}).get(pub_key, False) and icon_dir and icon_dir.exists())
                else []
            )

            dcal   = self.cal_data.get(pub_key, {})
            actions = None
            if not icon_images:
                if "actions" in dcal and dcal["actions"]:
                    actions = dcal["actions"]
                elif "click_path" in dcal and dcal["click_path"]:
                    actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY}
                               for (x, y) in dcal["click_path"]]
                elif "pdf_xy" in dcal and dcal["pdf_xy"]:
                    x, y = dcal["pdf_xy"]
                    actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY}]
                else:
                    log(f"Row {idx} no actions/icons -> mark 0")
                    df.at[idx, "Downloaded"] = "0"
                    save_progress(df, excel_path, apply_links=True, log=log)
                    self._bump_journal_fail(jkey)
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    self._update_stats(df, start_ts, processed_since_start)
                    continue

            # Retry loop
            ok = False
            did_attempt = False
            for attempt in range(1, MAX_RETRIES + 1):
                if abort_now:
                    raise SystemExit("Aborted")
                did_attempt = True
                log(f"Row {idx} attempt {attempt}/{MAX_RETRIES} launching Chrome")
                try:
                    reset_to_desktop(include_enter=True, pause=DESKTOP_RESET_PAUSE)
                    open_in_chrome("about:blank", new_window=True, browser_open_wait=BROWSER_OPEN_WAIT, log=log)
                    time.sleep(BROWSER_OPEN_WAIT)
                    go_to_address_bar_and_open(link, wait_after_nav=WAIT_AFTER_NAV, abort_flag=_abort, log=log)
                    if icon_images:
                        ok = run_icons_then_save(icon_images, target_path, coords_save)
                    else:
                        ok = run_actions_then_save(actions, target_path, coords_save)
                except SystemExit:
                    close_all_chrome(log=log); raise
                except Exception as e:
                    log(f"Row {idx} attempt {attempt} error:", e); ok = False
                finally:
                    close_all_chrome(log=log)
                    reset_to_desktop(include_enter=True, pause=DESKTOP_RESET_PAUSE)
                log(f"Row {idx} attempt {attempt} result:", ok)
                if ok:
                    break

            # Update workbook
            if ok and target_path.exists():
                df.at[idx, "Downloaded"] = "1"
            else:
                df.at[idx, "Downloaded"] = "0"
                self._bump_journal_fail(jkey)

            save_progress(df, excel_path, apply_links=True, log=log)
            self.pending_set.discard(idx)

            processed_since_save  += 1
            processed_since_start += 1
            if save_requested or processed_since_save >= SAVE_EVERY:
                log("Periodic save")
                save_progress(df, excel_path, apply_links=True, log=log)
                processed_since_save = 0
                save_requested = False

            self._update_stats(df, start_ts, processed_since_start)
            if did_attempt:
                reset_to_desktop(include_enter=True, pause=DESKTOP_RESET_PAUSE)

        save_progress(df, excel_path, apply_links=True, log=log)
        self._update_stats(df, start_ts, processed_since_start)
        log("All done")

    def _update_stats(self, df, start_ts, processed_since_start) -> None:
        col  = df["Downloaded"].astype(str).str.strip()
        succ = (col == "1").sum(); fail = (col == "0").sum()
        left = len(self.pending_set)
        eta_secs = int(left * max(time.time() - start_ts, 1) / processed_since_start) if processed_since_start > 0 else 0
        self.ui_queue.put(("stats", {"left": left, "succ": succ, "fail": fail, "eta_secs": eta_secs}))
        log(f"Stats -> left:{left} succ:{succ} fail:{fail} eta:{eta_secs}s")


# ===========================================================================
# 7. Boot
# ===========================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app  = App(root)
    root.mainloop()
