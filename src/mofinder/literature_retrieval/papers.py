"""Download article PDFs through locally calibrated browser actions.

Run ``python -m mofinder.literature_retrieval.papers --help`` for configuration options.
Desktop dependencies are loaded only when launching the interactive application.
"""

from __future__ import annotations

# Timing defaults; override through the literature retrieval configuration.
BROWSER_OPEN_WAIT       = 2.0   # seconds after opening Chrome before pasting link
WAIT_AFTER_NAV          = 4.0   # seconds after pressing Enter on the address bar
INTER_CLICK_DELAY       = 5.0   # seconds between coordinate-based action steps (track mode)
WAIT_AFTER_PDF          = 5.0   # seconds after the final click before saving (track mode)
STEP_PAUSE              = 0.5   # seconds between actions inside the Save dialog
ICON_ACTION_PAUSE       = 1.0   # seconds between every single action in ICON mode
ICON_WAIT_AFTER_FIRST_CLICK = 6.0  # seconds to wait *after the first icon click* in ICON mode
DESKTOP_RESET_PAUSE     = 0.5   # seconds between Win+D, Enter, and center click
SAVE_EVERY              = 4     # extra periodic save safety
MAX_RETRIES             = 2     # attempts per row

# Icon mode tuning
ICON_CONFIDENCE         = 0.87  # template match confidence
ICON_SEARCH_DELAY       = 0.7   # seconds between icon search tries
MAX_ICON_SEARCH_TIME    = 10.0  # max seconds to search for each icon
ICON_GAP_BEFORE_NEXT    = 5.0   # wait before searching the NEXT icon (when >= 2 steps)
ICON_BEFORE_RENAME_WAIT = 2.0   # wait after the last icon click before rename/save

# Journal fast-skip: after this many fails for the same journal key in one run, skip future rows for that journal
MAX_JOURNAL_FAILS       = 20
# ==========================================================================

# Chrome flags (incognito/private every time)
CHROME_FLAGS = [
    "--disable-session-crashed-bubble",
    "--no-first-run",
    "--incognito",
    "--start-maximized",
    "--start-fullscreen",
]

# Paths are resolved from the configuration at launch.
DEFAULT_EXCEL_PATH = ""
APP_SETTINGS = "app_settings.json"
PAPER_PROCESSING_ICON_DIR = None
DOWNLOAD_DIR = None
CONFIG_SETTINGS = {}

import argparse
import os
import re
import sys
import time
import json
import shutil
import queue
import subprocess
import threading
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, Set

from mofinder.display import display_path, display_paths

if TYPE_CHECKING:
    import pandas as pd

from mofinder.literature_retrieval.common import (
    audit_inventory,
    load_settings,
    prepare_local_inventory,
    publisher_key,
    read_inventory,
    write_inventory,
)

# These dependencies require an interactive desktop and are imported at launch.
tk = filedialog = messagebox = ttk = None
pyautogui = pyperclip = pynput_keyboard = None
HAS_CV2 = False


def load_desktop_dependencies():
    global tk, filedialog, messagebox, ttk
    global pyautogui, pyperclip, pynput_keyboard, HAS_CV2
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import pyautogui
    import pyperclip
    from pynput import keyboard as pynput_keyboard

    try:
        import cv2  # noqa: F401
        HAS_CV2 = True
    except ImportError:
        HAS_CV2 = False
    pyautogui.FAILSAFE = True


IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
IS_LINUX = not IS_MAC and not IS_WIN

SUPPORTED_PREFIXES = [
    "publisher_W", "publisher_A", "publisher_R", "publisher_S", "publisher_E",
]
SAMPLE_URLS = {}
DEFAULT_CAL = {name: {} for name in SUPPORTED_PREFIXES}
DEFAULT_GLOBAL_SAVE_XY = None
CAL_FILE = "doi_downloader_calibration.json"

abort_now = False
save_requested = False

def _stop_on_failsafe(error):
    """Preserve the desktop corner stop through broad automation handlers."""
    global abort_now, save_requested
    gui = globals().get("pyautogui")
    if gui is not None and isinstance(error, gui.FailSafeException):
        abort_now = True
        save_requested = True
        raise SystemExit("Stopped by the pointer corner fail-safe.") from error


def _local_inventory(path):
    """Reopen or create the working inventory for a GUI-selected source."""
    if not CONFIG_SETTINGS:
        raise RuntimeError("Configure literature retrieval settings before selecting an inventory.")
    return prepare_local_inventory({**CONFIG_SETTINGS, "workbook": Path(path)})


def log(*args):
    ts = time.strftime("[%H:%M:%S]")
    print(ts, *(display_paths(str(arg)) for arg in args), flush=True)

# ---------- helpers ----------
def doi_to_link(doi: str) -> str:
    doi = str(doi).strip()
    if not doi or doi.lower() == "nan":
        return ""
    if doi.lower().startswith("http"):
        return doi
    return f"https://doi.org/{doi}"

def doi_to_filename(doi: str) -> str:
    base = str(doi).strip().replace("/", "_")
    base = re.sub(r'[<>:"\\|?*\n\r\t]', "_", base)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base

def doi_journal_key(doi: str) -> str:
    """
    Journal skip key = <everything before '/'> + '/' + first 5 chars after '/'
    Example: '10.1016/j.ica.2018.05.024' -> '10.1016/j.ica'
    """
    if not doi or "/" not in doi:
        return ""
    pfx, sfx = doi.split("/", 1)
    sfx5 = sfx[:5] if len(sfx) >= 5 else sfx
    return f"{pfx}/{sfx5}".lower()

def ensure_download_dir(excel_path: Path) -> Path:
    """Create the configured output directory independently of inventory location."""
    if DOWNLOAD_DIR is None:
        raise RuntimeError("Configure download_dir before starting literature retrieval.")
    out = Path(DOWNLOAD_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out

def fresh_file_ready(path: Path, timeout=90):
    t0 = time.time()
    tmp_exts = [".crdownload", ".part", ".tmp"]
    while time.time() - t0 < timeout:
        if abort_now:
            raise SystemExit("Aborted")
        if path.exists() and path.stat().st_size > 0 and not any(Path(str(path) + e).exists() for e in tmp_exts):
            return True
        time.sleep(0.2)
    return False

def sleep_check_abort(seconds: float):
    t_end = time.time() + seconds
    while time.time() < t_end:
        if abort_now:
            raise SystemExit("Aborted")
        time.sleep(0.1)

def hotkey_address_bar():
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "l")

def hotkey_save():
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "s")

def close_all_chrome():
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", "chrome.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif IS_MAC:
            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.6)
            subprocess.run(["pkill", "-x", "Google Chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            for cmd in (["pkill", "-x", "google-chrome"], ["pkill", "-x", "chrome"], ["pkill", "chrome"]):
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
    except Exception as e:
        log("close_all_chrome error:", e)
    time.sleep(1.2)

def reset_to_desktop(include_enter=True):
    if abort_now:
        raise SystemExit("Aborted")
    if IS_WIN:
        log("Reset to desktop")
        pyautogui.hotkey("winleft", "d"); time.sleep(DESKTOP_RESET_PAUSE)
        if include_enter:
            pyautogui.press("enter"); time.sleep(DESKTOP_RESET_PAUSE)
        w, h = pyautogui.size()
        pyautogui.click(w // 2, h // 2); time.sleep(DESKTOP_RESET_PAUSE)

# ---------- calibration ----------
def load_calibration() -> dict:
    data = {}
    if os.path.exists(CAL_FILE):
        with open(CAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    changed = False
    for name, sub in DEFAULT_CAL.items():
        data.setdefault(name, {})
        if "pdf_xy" not in data[name] and "pdf_xy" in sub:
            data[name]["pdf_xy"] = sub["pdf_xy"]; changed = True
    data.setdefault("GLOBAL_SAVE", {})
    if "save_xy" not in data["GLOBAL_SAVE"]:
        data["GLOBAL_SAVE"]["save_xy"] = DEFAULT_GLOBAL_SAVE_XY; changed = True
    data.setdefault("ICON_MODE", {k: False for k in SUPPORTED_PREFIXES})
    if changed:
        save_calibration(data)
    return data

def save_calibration(data: dict):
    Path(CAL_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(CAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------- inventory ----------
def load_and_prepare_excel(path: Path) -> pd.DataFrame:
    log("Loading inventory:", path)
    df = read_inventory(path)
    if "DOI" not in df.columns:
        raise ValueError("Missing column: DOI")
    if "Publisher" not in df.columns:
        raise ValueError("Missing column: Publisher")
    df["DOI Link"] = df["DOI"].apply(doi_to_link)
    if "Downloaded" not in df.columns:
        df["Downloaded"] = ""
    write_inventory(df, path, hyperlinks=True)
    log("Inventory prepared. Rows:", len(df))
    return df

def save_progress(df: pd.DataFrame, path: Path):
    write_inventory(df, path, hyperlinks=True)
    log("Saved inventory:", path)

# ---------- icons ----------
ICON_EXTS = (".png", ".jpg", ".jpeg", ".bmp")

def list_icon_sequence(publisher: str, icon_dir: Path):
    if not icon_dir or not icon_dir.exists():
        return []
    cands = []
    for p in icon_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in ICON_EXTS:
            continue
        m = re.match(rf"^{re.escape(publisher)}_(\d+)$", p.stem, flags=re.IGNORECASE)
        if m:
            cands.append((int(m.group(1)), p))
    cands.sort(key=lambda x: x[0])
    seq = [p for _, p in cands]
    log(f"Icon steps for {publisher}: {[p.name for p in seq]}")
    return seq

def locate_center_on_screen(image_path: Path, confidence: float):
    try:
        box = pyautogui.locateCenterOnScreen(str(image_path), confidence=confidence) if HAS_CV2 else pyautogui.locateCenterOnScreen(str(image_path))
        return (int(box.x), int(box.y)) if box else None
    except Exception as e:
        _stop_on_failsafe(e)
        log("locate err", image_path, e); return None

# ---------- browser ----------
def _chrome_candidates():
    if IS_WIN:
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif IS_MAC:
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        names = ["google-chrome", "chrome", "chromium-browser", "chromium"]
        return [shutil.which(n) for n in names if shutil.which(n)]

def open_in_chrome(url: str, new_window=False):
    exe_list = _chrome_candidates()
    args_flags = list(CHROME_FLAGS)
    if new_window:
        args_flags.append("--new-window")

    for exe in exe_list:
        if not exe:
            continue
        try:
            log("Launching Chrome:", exe, "flags:", " ".join(args_flags), "url:", url)
            subprocess.Popen([exe, *args_flags, url])

            # Set fullscreen/maximized state after launch.
            time.sleep(BROWSER_OPEN_WAIT)
            try:
                if IS_MAC:
                    # macOS Chrome fullscreen
                    pyautogui.hotkey("command", "ctrl", "f")
                elif IS_WIN:
                    # Maximize the window, then request fullscreen with F11.
                    pyautogui.hotkey("winleft", "up")
                    time.sleep(0.2)
                    pyautogui.press("f11")
                else:
                    # Linux
                    pyautogui.press("f11")
            except Exception as e:
                _stop_on_failsafe(e)
                log("Fullscreen hotkey error:", e)
            return
        except Exception as e:
            _stop_on_failsafe(e)
            log("Chrome launch failed with", exe, e)
            continue

    # Fallback: system webbrowser
    try:
        log("webbrowser fallback:", url)
        br = webbrowser.get("chrome")
        br.open_new(url) if new_window else br.open(url)
    except Exception:
        log("open_new_tab fallback:", url)
        webbrowser.open_new_tab(url)

    # Request fullscreen after the fallback browser launch.
    time.sleep(BROWSER_OPEN_WAIT)
    try:
        if IS_MAC:
            pyautogui.hotkey("command", "ctrl", "f")
        elif IS_WIN:
            pyautogui.hotkey("winleft", "up")
            time.sleep(0.2)
            pyautogui.press("f11")
        else:
            pyautogui.press("f11")
    except Exception as e:
        _stop_on_failsafe(e)
        log("Fullscreen hotkey error:", e)


def go_to_address_bar_and_open(link: str):
    if abort_now:
        raise SystemExit("Aborted")
    log("Navigating:", link)
    hotkey_address_bar(); time.sleep(0.2)
    pyperclip.copy(link); pyautogui.hotkey("command" if IS_MAC else "ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); sleep_check_abort(WAIT_AFTER_NAV)
    log("Navigation done")

# ---------- finalize ----------
def finalize_save_and_reset_track(target_path: Path) -> bool:
    log("Finalize (track): Enter x2 -> desktop reset -> quick check")
    pyautogui.press("enter"); time.sleep(STEP_PAUSE)
    pyautogui.press("enter")
    reset_to_desktop(include_enter=True)
    ok2 = fresh_file_ready(target_path, timeout=5)
    log("Quick file check:", ok2)
    return ok2

# ---------- automation ----------
def run_actions_then_save(actions, target_path: Path, coords_save_xy) -> bool:
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
            pyautogui.click(); sleep_check_abort(step.get("wait", INTER_CLICK_DELAY))
    log("TRACK wait then Ctrl+S:", WAIT_AFTER_PDF, "s")
    sleep_check_abort(WAIT_AFTER_PDF)
    sx, sy = coords_save_xy
    log("TRACK rename at", (sx, sy), "->", target_path.name)
    hotkey_save(); time.sleep(STEP_PAUSE)
    pyautogui.moveTo(int(sx), int(sy), duration=0.2); time.sleep(STEP_PAUSE)
    pyautogui.click();               time.sleep(STEP_PAUSE)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a"); time.sleep(STEP_PAUSE)
    pyautogui.press("delete");       time.sleep(STEP_PAUSE)
    pyperclip.copy(str(target_path)); pyautogui.hotkey("command" if IS_MAC else "ctrl", "v"); time.sleep(STEP_PAUSE)
    ok = fresh_file_ready(target_path, timeout=90) if finalize_save_and_reset_track(target_path) else False
    log("TRACK result:", ok); return ok

def run_icons_then_save(icon_images, target_path: Path, coords_save_xy) -> bool:
    log("ICON steps:", [p.name for p in icon_images])
    if abort_now:
        raise SystemExit("Aborted")
    micro = ICON_ACTION_PAUSE
    attempts_per_icon = max(1, int(MAX_ICON_SEARCH_TIME / ICON_SEARCH_DELAY))

    for idx, img in enumerate(icon_images):
        if idx > 0:
            log(f"ICON gap before next: {ICON_GAP_BEFORE_NEXT}s"); sleep_check_abort(ICON_GAP_BEFORE_NEXT)
        found = None
        for attempt in range(1, attempts_per_icon + 1):
            found = locate_center_on_screen(img, ICON_CONFIDENCE)
            if found:
                log(f"ICON found {img.name} at {found} (attempt {attempt})"); break
            if attempt % int(max(1, 2/ICON_SEARCH_DELAY)) == 0:
                log(f"ICON searching {img.name}... attempt {attempt}")
            time.sleep(ICON_SEARCH_DELAY)
        if not found:
            log("ICON NOT found:", img.name); return False
        pyautogui.moveTo(found[0], found[1], duration=0.25); time.sleep(micro)
        pyautogui.click(); time.sleep(micro)
        if idx == 0 and ICON_WAIT_AFTER_FIRST_CLICK > 0:
            log(f"ICON wait after FIRST click: {ICON_WAIT_AFTER_FIRST_CLICK}s")
            sleep_check_abort(ICON_WAIT_AFTER_FIRST_CLICK)

    log("ICON wait before rename:", ICON_BEFORE_RENAME_WAIT, "s")
    sleep_check_abort(ICON_BEFORE_RENAME_WAIT)

    sx, sy = coords_save_xy
    log("ICON rename at", (sx, sy), "->", target_path.name)
    pyautogui.moveTo(int(sx), int(sy), duration=0.2); time.sleep(micro)
    pyautogui.click(); time.sleep(micro)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a"); time.sleep(micro)
    pyautogui.press("delete"); time.sleep(micro)
    pyperclip.copy(str(target_path)); pyautogui.hotkey("command" if IS_MAC else "ctrl", "v"); time.sleep(micro)
    pyautogui.press("enter"); time.sleep(micro)
    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2); time.sleep(micro)
    pyautogui.press("enter"); time.sleep(micro)

    if IS_WIN:
        log("ICON desktop reset")
        pyautogui.hotkey("winleft", "d"); time.sleep(micro)
        pyautogui.press("enter"); time.sleep(micro)
        pyautogui.click(w // 2, h // 2); time.sleep(micro)

    ok = fresh_file_ready(target_path, timeout=90)
    log("ICON result:", ok); return ok

# ------------------------- App (only empties are processed) -------------------------

class App:
    def __init__(self, root, workbook_path=None):
        self.root = root
        self.root.title("Article downloader")

        self.ui_queue = queue.Queue()
        self.excel_path_var = tk.StringVar(value=str(workbook_path or self._load_last_excel() or DEFAULT_EXCEL_PATH))
        self.status_var = tk.StringVar(value="Ready")
        self.stats_var = tk.StringVar(value="Left: 0  Success: 0  Fail: 0  ETA: 00:00")
        self.cal_data = load_calibration()

        self.icon_counts = {k: 0 for k in SUPPORTED_PREFIXES}
        self.pub_info_vars = {k: tk.StringVar(value=self.pub_info_text(k)) for k in SUPPORTED_PREFIXES}
        self.icon_mode_vars = {k: tk.BooleanVar(value=self.cal_data.get("ICON_MODE", {}).get(k, False)) for k in SUPPORTED_PREFIXES}
        self.icon_mode_widgets = {}
        self.save_box_var = tk.StringVar(value=self.save_box_text())

        # Journal fail tracking (in-memory, reset each run) using JOURNAL KEY rule
        self.journal_fail_counts: Dict[str, int] = {}
        self.skip_journal_keys: Set[str] = set()

        pad = 6
        frm = ttk.Frame(root, padding=pad); frm.pack(fill="both", expand=True)

        row_file = ttk.Frame(frm); row_file.pack(fill="x", pady=(pad, 0))
        ttk.Label(row_file, text="Inventory file:").pack(side="left")
        ttk.Entry(row_file, textvariable=self.excel_path_var, width=90).pack(side="left", padx=(pad, pad))
        ttk.Button(row_file, text="Browse", command=self.pick_file).pack(side="left")

        ttk.Label(frm, text="Publishers").pack(anchor="w", pady=(pad, 0))
        self.rows = {}
        for name in SUPPORTED_PREFIXES:
            r = ttk.Frame(frm); r.pack(fill="x", pady=2); self.rows[name] = r
            ttk.Label(r, text=name, width=18).grid(row=0, column=0, sticky="w")
            cb = ttk.Checkbutton(r, text="Icon mode", variable=self.icon_mode_vars[name], command=lambda n=name: self.toggle_icon_mode(n))
            cb.grid(row=0, column=1, sticky="w", padx=4); self.icon_mode_widgets[name] = cb
            ttk.Label(r, textvariable=self.pub_info_vars[name], width=70, anchor="w").grid(row=0, column=2, sticky="w")
            ttk.Button(r, text="Record actions (F8 add, F9 finish)", command=lambda n=name: self.capture_actions(n)).grid(row=0, column=3, padx=4, sticky="w")
            ttk.Button(r, text="Open sample page", command=lambda n=name: self.open_sample(n)).grid(row=0, column=4, padx=4)

        ttk.Label(frm, text="Save dialog filename box").pack(anchor="w", pady=(pad, 0))
        row_save = ttk.Frame(frm); row_save.pack(fill="x", pady=2)
        ttk.Label(row_save, textvariable=self.save_box_var, width=40, anchor="w").pack(side="left")
        ttk.Button(row_save, text="Set FILE NAME box XY (F8)", command=self.capture_global_save_xy).pack(side="left", padx=6)

        ctrl = ttk.Frame(frm); ctrl.pack(fill="x", pady=(pad, 0))
        ttk.Button(ctrl, text="Start", command=self.start).pack(side="left", padx=(0, pad))
        ttk.Button(ctrl, text="STOP now", command=self.stop_now).pack(side="left")

        ttk.Label(frm, textvariable=self.stats_var).pack(fill="x", pady=(pad, 0))
        ttk.Label(frm, textvariable=self.status_var).pack(fill="x", pady=(pad, 0))

        tracker = ttk.Frame(frm); tracker.pack(fill="x", pady=(pad, 0))
        self.mouse_xy_var = tk.StringVar(value="Mouse XY: ...")
        self.track_mouse = tk.BooleanVar(value=False)
        ttk.Checkbutton(tracker, text="Track mouse XY", variable=self.track_mouse, command=self.update_mouse_tracker).pack(side="left")
        ttk.Label(tracker, textvariable=self.mouse_xy_var).pack(side="left", padx=8)

        ttk.Label(frm, text="Hotkeys: Ctrl+Shift+S save now, Ctrl+Shift+X STOP now.").pack(fill="x", pady=(pad, 0))
        ttk.Label(frm, text="Closes Chrome windows during literature retrieval.").pack(fill="x", pady=(pad, 0))

        self.start_hotkeys()
        self.root.after(150, self.poll_ui)
        self.root.after(120, self.update_mouse_tracker)

        self.refresh_icon_availability()

    # persistence
    def _load_last_excel(self) -> Optional[str]:
        try:
            if os.path.exists(APP_SETTINGS):
                with open(APP_SETTINGS, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                value = cfg.get("last_excel")
                return value if value and Path(value).is_file() else None
        except Exception:
            return None
        return None

    def _save_last_excel(self, path: str):
        try:
            Path(APP_SETTINGS).parent.mkdir(parents=True, exist_ok=True)
            with open(APP_SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"last_excel": path}, f, indent=2)
        except Exception:
            pass

    # icon prescreen
    def get_paper_processing_icon_dir(self) -> Optional[Path]:
        return Path(PAPER_PROCESSING_ICON_DIR) if PAPER_PROCESSING_ICON_DIR is not None else None

    def refresh_icon_availability(self):
        icon_dir = self.get_paper_processing_icon_dir()
        for name in SUPPORTED_PREFIXES:
            count = 0; available = False
            if icon_dir and icon_dir.exists():
                imgs = list_icon_sequence(name, icon_dir)
                count = len(imgs); available = count > 0
            self.icon_counts[name] = count
            widget = self.icon_mode_widgets.get(name)
            if widget:
                if available: widget.state(["!disabled"])
                else:
                    widget.state(["disabled"])
                    self.icon_mode_vars[name].set(False)
                    self.cal_data.setdefault("ICON_MODE", {}); self.cal_data["ICON_MODE"][name] = False
            self.update_pub_info_label(name)
        save_calibration(self.cal_data)

    # misc UI
    def update_mouse_tracker(self):
        if self.track_mouse.get():
            p = pyautogui.position(); self.mouse_xy_var.set(f"Mouse XY: ({p.x}, {p.y})")
            self.root.after(120, self.update_mouse_tracker)

    def pub_info_text(self, name):
        d = self.cal_data.get(name, {})
        icon_mode = self.cal_data.get("ICON_MODE", {}).get(name, False)
        mode = "ICON" if icon_mode else "ACTIONS"
        icon_steps = self.icon_counts.get(name, 0)
        act_count = 0
        if "actions" in d and d["actions"]: act_count = len(d["actions"])
        elif "click_path" in d and d["click_path"]: act_count = len(d["click_path"])
        pdf = tuple(d.get("pdf_xy")) if d.get("pdf_xy") else None
        fallback = f"Fallback XY: {pdf}" if pdf else "Fallback XY: None"
        return f"{mode} | Icon steps: {icon_steps} | Actions: {act_count} | {fallback}"

    def save_box_text(self):
        g = self.cal_data.get("GLOBAL_SAVE", {})
        sav = tuple(g.get("save_xy")) if g.get("save_xy") else None
        return f"FILE NAME BOX XY: {sav}"

    def update_pub_info_label(self, name): self.pub_info_vars[name].set(self.pub_info_text(name))
    def update_save_box_label(self): self.save_box_var.set(self.save_box_text())

    def toggle_icon_mode(self, name):
        self.cal_data.setdefault("ICON_MODE", {}); self.cal_data["ICON_MODE"][name] = bool(self.icon_mode_vars[name].get())
        save_calibration(self.cal_data); self.update_pub_info_label(name)

    def pick_file(self):
        path = filedialog.askopenfilename(title="Pick inventory file", filetypes=[("Inventory", "*.csv *.xlsx"), ("CSV", "*.csv"), ("Excel", "*.xlsx")])
        if path:
            try:
                working = _local_inventory(path)
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Inventory", display_paths(str(exc))); return
            self.excel_path_var.set(str(working)); self._save_last_excel(str(working)); self.refresh_icon_availability()

    # samples + calibration
    def open_sample(self, name):
        url = SAMPLE_URLS.get(name)
        if not url:
            try:
                inventory = read_inventory(Path(self.excel_path_var.get().strip()))
                matches = inventory[inventory["Publisher"].map(publisher_key) == name]
                links = [doi_to_link(value) for value in matches["DOI"]]
                url = next((link for link in links if link), None)
            except Exception as exc:
                messagebox.showerror("Sample page", display_paths(str(exc))); return
        if not url:
            messagebox.showwarning("Sample page", f"No sample URL or inventory DOI is available for {name}."); return
        open_in_chrome("about:blank", new_window=True); time.sleep(BROWSER_OPEN_WAIT)
        go_to_address_bar_and_open(url)

    def _capture_f8_f9_points(self, label_update_fn):
        points = []; done_flag = {"done": False}
        def on_press(key):
            try:
                if key == pynput_keyboard.Key.f8:
                    p = pyautogui.position(); points.append((p.x, p.y))
                    self.root.after(0, lambda: label_update_fn(len(points)))
                elif key == pynput_keyboard.Key.f9:
                    done_flag["done"] = True; return False
            except Exception as exc:
                _stop_on_failsafe(exc)
                return False
        listener = pynput_keyboard.Listener(on_press=on_press); listener.start()
        while listener.is_alive():
            if done_flag["done"]: break
            self.root.update(); time.sleep(0.05)
        return points

    def capture_actions(self, name):
        win = tk.Toplevel(self.root); win.title(f"Record actions: {name}")
        win.geometry("660x240+100+60"); win.attributes("-topmost", True)
        info = (f"{name}\n\n"
                "1) Click Open sample page if needed.\n"
                "2) Move to each clickable target.\n"
                "3) Press F8 to add each step, press F9 to finish.")
        ttk.Label(win, text=info, justify="left", wraplength=630).pack(padx=10, pady=8, fill="x")
        count_var = tk.StringVar(value="Captured steps: 0"); ttk.Label(win, textvariable=count_var).pack(pady=(0, 6))
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)
        def upd(n): count_var.set(f"Captured steps: {n}")
        points = self._capture_f8_f9_points(upd); win.destroy()
        if not points: messagebox.showwarning("Actions", "No steps captured."); return
        actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY} for (x, y) in points]
        self.cal_data.setdefault(name, {})["actions"] = actions
        self.cal_data[name]["click_path"] = [list(p) for p in points]
        save_calibration(self.cal_data); self.update_pub_info_label(name)
        messagebox.showinfo("Saved", f"{name} actions saved with {len(actions)} step(s).")

    def capture_global_save_xy(self):
        messagebox.showinfo("Save-box capture", "Open any Save dialog. Hover FILE NAME box, press F8. Press F9 to finish.")
        def upd(n): pass
        points = self._capture_f8_f9_points(upd)
        if not points: messagebox.showwarning("Save-box", "No position captured."); return
        pos = points[-1]
        self.cal_data.setdefault("GLOBAL_SAVE", {})["save_xy"] = [int(pos[0]), int(pos[1])]
        save_calibration(self.cal_data); self.update_save_box_label()
        messagebox.showinfo("Saved", f"FILE NAME BOX XY saved at {pos}")

    # run
    def start(self):
        global abort_now, save_requested
        abort_now = False; save_requested = False
        p = self.excel_path_var.get().strip()
        if not p: messagebox.showerror("Error", "Pick an inventory file first."); return
        excel_path = Path(p)
        if not excel_path.exists(): messagebox.showerror("Error", f"File not found:\n{display_path(excel_path)}"); return
        if not self.cal_data.get("GLOBAL_SAVE", {}).get("save_xy"):
            messagebox.showerror("Calibration", "Set the Save dialog filename box position before starting."); return
        try:
            excel_path = _local_inventory(excel_path)
            self.excel_path_var.set(str(excel_path))
            self._save_last_excel(str(excel_path))
            df = load_and_prepare_excel(excel_path)
        except Exception as e:
            _stop_on_failsafe(e)
            messagebox.showerror("Error", display_paths(str(e))); return

        self.refresh_icon_availability()

        # Strict pending mask: only empties count as work
        col_raw = df["Downloaded"]
        pending_mask = col_raw.isna() | (col_raw.astype(str).str.strip() == "")
        pending_indices = df.index[pending_mask].tolist()
        self.pending_set = set(pending_indices)

        succ = (col_raw.astype(str).str.strip() == "1").sum()
        fail = (col_raw.astype(str).str.strip() == "0").sum()

        self.initial_done = succ + fail
        self.start_time = time.time()
        self.ui_queue.put(("stats", {"left": len(self.pending_set), "succ": succ, "fail": fail, "eta_secs": 0}))
        self.ui_queue.put(("status", "Running."))
        log("Start run. Pending rows:", len(self.pending_set))

        self.root.update(); self.root.geometry("320x120+0+0"); self.root.iconify()

        def worker():
            try:
                self.process_rows(df, excel_path, pending_indices)
                self.ui_queue.put(("status", "Done.")); self.ui_queue.put(("restore", None))
            except SystemExit:
                self.ui_queue.put(("status", "Stopped.")); self.ui_queue.put(("restore", None))
            except Exception as e:
                log("Worker error:", e)
                self.ui_queue.put(("status", f"Error: {e}")); self.ui_queue.put(("restore", None))
        self.worker = threading.Thread(target=worker, daemon=True); self.worker.start()

    def stop_now(self):
        global abort_now
        abort_now = True; self.ui_queue.put(("status", "STOP now requested.")); log("STOP requested")

    def start_hotkeys(self):
        def on_save():
            global save_requested
            save_requested = True; log("Hotkey save requested")
        def on_stop_now():
            global abort_now
            abort_now = True; log("Hotkey STOP now")
        combos = {"<ctrl>+<shift>+s": on_save, "<ctrl>+<shift>+x": on_stop_now,
                  "<cmd>+<shift>+s": on_save, "<cmd>+<shift>+x": on_stop_now}
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys(combos); self.hotkey_listener.start()

    def poll_ui(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status": self.status_var.set(payload)
                elif kind == "stats":
                    left = payload.get("left", 0); succ = payload.get("succ", 0); fail = payload.get("fail", 0)
                    h, m = divmod((payload.get("eta_secs", 0) // 60), 60)
                    self.stats_var.set(f"Left: {left}  Success: {succ}  Fail: {fail}  ETA: {h:02d}:{m:02d}")
                elif kind == "restore":
                    try: self.root.deiconify(); self.root.lift()
                    except Exception: pass
        except queue.Empty: pass
        self.root.after(150, self.poll_ui)

    # Journal skip helpers (per-run, in-memory)
    def _bump_journal_fail(self, journal_key: str):
        if not journal_key:
            return
        cnt = self.journal_fail_counts.get(journal_key, 0) + 1
        self.journal_fail_counts[journal_key] = cnt
        log(f"Journal key '{journal_key}' fail count -> {cnt}/{MAX_JOURNAL_FAILS}")
        if cnt >= MAX_JOURNAL_FAILS:
            self.skip_journal_keys.add(journal_key)
            log(f"Journal key '{journal_key}' reached max fails. Will skip further rows for this journal this run.")

    def process_rows(self, df: pd.DataFrame, excel_path: Path, indices):
        global save_requested
        ensure_download_dir(excel_path)
        processed_since_save = 0; start_ts = time.time(); processed_since_start = 0
        coords_save = self.cal_data.get("GLOBAL_SAVE", {}).get("save_xy")
        if not coords_save: raise SystemExit("Global FILE NAME BOX XY not set.")
        icon_dir = self.get_paper_processing_icon_dir()

        for idx in indices:
            if abort_now: raise SystemExit("Aborted")
            if idx not in self.pending_set:
                continue

            row = df.iloc[idx]
            doi = str(row.get("DOI", "")).strip()
            pub_key = publisher_key(row.get("Publisher", ""))

            # compute journal key for fast-skip rule
            jkey = doi_journal_key(doi)
            if jkey and jkey in self.skip_journal_keys:
                log(f"Row {idx} skipped due to journal key '{jkey}' reached max fails")
                # Skip the row without changing its download status.
                self.pending_set.discard(idx)
                self._update_stats(df, start_ts, processed_since_start)
                continue

            log(f"Row {idx} start. DOI='{doi}' Publisher='{pub_key}' JournalKey='{jkey}'")

            if not doi or not pub_key:
                df.at[idx, "Downloaded"] = "0"; save_progress(df, excel_path)
                self._bump_journal_fail(jkey)
                self.pending_set.discard(idx)
                processed_since_start += 1; self._update_stats(df, start_ts, processed_since_start)
                continue

            target_path = (ensure_download_dir(excel_path) / doi_to_filename(doi)).resolve()
            if target_path.exists() and target_path.stat().st_size > 0:
                log(f"Row {idx} file already exists -> mark 1 (no actions)")
                df.at[idx, "Downloaded"] = "1"; save_progress(df, excel_path)
                self.pending_set.discard(idx)
                processed_since_start += 1; self._update_stats(df, start_ts, processed_since_start)
                continue

            link = doi_to_link(doi); df.at[idx, "DOI Link"] = link

            icon_images = list_icon_sequence(pub_key, icon_dir) if (self.cal_data.get("ICON_MODE", {}).get(pub_key, False) and icon_dir and icon_dir.exists()) else []

            dcal = self.cal_data.get(pub_key, {})
            actions = None
            if not icon_images:
                if "actions" in dcal and dcal["actions"]:
                    actions = dcal["actions"]
                elif "click_path" in dcal and dcal["click_path"]:
                    actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY} for (x, y) in dcal["click_path"]]
                elif "pdf_xy" in dcal and dcal["pdf_xy"]:
                    x, y = dcal["pdf_xy"]; actions = [{"type": "click", "x": int(x), "y": int(y), "wait": INTER_CLICK_DELAY}]
                else:
                    log(f"Row {idx} no actions/icons -> mark 0")
                    df.at[idx, "Downloaded"] = "0"; save_progress(df, excel_path)
                    self._bump_journal_fail(jkey)
                    self.pending_set.discard(idx)
                    processed_since_start += 1; self._update_stats(df, start_ts, processed_since_start)
                    continue

            ok = False
            did_attempt = False
            for attempt in range(1, MAX_RETRIES + 1):
                if abort_now: raise SystemExit("Aborted")
                did_attempt = True
                log(f"Row {idx} attempt {attempt}/{MAX_RETRIES} launching Chrome")
                try:
                    reset_to_desktop(include_enter=True)
                    open_in_chrome("about:blank", new_window=True); time.sleep(BROWSER_OPEN_WAIT)
                    go_to_address_bar_and_open(link)
                    if icon_images:
                        ok = run_icons_then_save(icon_images, target_path, coords_save)
                    else:
                        ok = run_actions_then_save(actions, target_path, coords_save)
                except SystemExit:
                    close_all_chrome(); raise
                except Exception as e:
                    _stop_on_failsafe(e)
                    log(f"Row {idx} attempt {attempt} error:", e); ok = False
                finally:
                    close_all_chrome(); reset_to_desktop(include_enter=True)
                log(f"Row {idx} attempt {attempt} result:", ok)
                if ok: break

            if ok and target_path.exists():
                df.at[idx, "Downloaded"] = "1"
            else:
                df.at[idx, "Downloaded"] = "0"
                self._bump_journal_fail(jkey)

            save_progress(df, excel_path)
            self.pending_set.discard(idx)

            processed_since_save += 1; processed_since_start += 1
            if save_requested or processed_since_save >= SAVE_EVERY:
                log("Periodic save"); save_progress(df, excel_path)
                processed_since_save = 0; save_requested = False

            self._update_stats(df, start_ts, processed_since_start)
            if did_attempt:
                reset_to_desktop(include_enter=True)

        save_progress(df, excel_path)
        self._update_stats(df, start_ts, processed_since_start)
        log("All done")

    def _update_stats(self, df, start_ts, processed_since_start):
        col = df["Downloaded"].astype(str).str.strip()
        succ = (col == "1").sum(); fail = (col == "0").sum()
        left = len(self.pending_set)
        eta_secs = int(left * max(time.time() - start_ts, 1) / processed_since_start) if processed_since_start > 0 else 0
        self.ui_queue.put(("stats", {"left": left, "succ": succ, "fail": fail, "eta_secs": eta_secs}))
        log(f"Stats -> left:{left} succ:{succ} fail:{fail} eta:{eta_secs}s")

# ---------- configuration and entry point ----------
TUNING_KEYS = (
    "BROWSER_OPEN_WAIT", "WAIT_AFTER_NAV", "INTER_CLICK_DELAY", "WAIT_AFTER_PDF",
    "STEP_PAUSE", "ICON_ACTION_PAUSE", "ICON_WAIT_AFTER_FIRST_CLICK",
    "DESKTOP_RESET_PAUSE", "SAVE_EVERY", "MAX_RETRIES", "ICON_CONFIDENCE",
    "ICON_SEARCH_DELAY", "MAX_ICON_SEARCH_TIME", "ICON_GAP_BEFORE_NEXT",
    "ICON_BEFORE_RENAME_WAIT", "MAX_JOURNAL_FAILS",
)


def configure(settings: dict):
    """Apply resolved paths and optional timing overrides without opening a desktop."""
    global DEFAULT_EXCEL_PATH, APP_SETTINGS, CAL_FILE, PAPER_PROCESSING_ICON_DIR, DOWNLOAD_DIR, SAMPLE_URLS, CONFIG_SETTINGS
    CONFIG_SETTINGS = dict(settings)
    DEFAULT_EXCEL_PATH = str(settings["workbook"])
    APP_SETTINGS = Path(settings["app_settings_file"])
    CAL_FILE = Path(settings["calibration_file"])
    PAPER_PROCESSING_ICON_DIR = Path(settings["paper_processing_icon_dir"])
    DOWNLOAD_DIR = Path(settings["download_dir"])
    SAMPLE_URLS = dict(settings.get("sample_urls", {}))
    for name, value in settings.get("tuning", {}).items():
        if name not in TUNING_KEYS:
            raise ValueError(f"Unknown article literature retrieval setting: {name}")
        globals()[name] = value


def launch(settings: dict):
    """Launch the local calibration interface and downloader."""
    global abort_now, save_requested
    configure(settings)
    load_desktop_dependencies()
    workbook = prepare_local_inventory(settings)
    abort_now = False
    save_requested = False
    root = tk.Tk()
    app = App(root, workbook_path=workbook)
    try:
        root.mainloop()
    finally:
        abort_now = True
        app.hotkey_listener.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/literature_retrieval.json", help="Literature retrieval configuration JSON.")
    parser.add_argument("--workbook", type=Path, help="Override the configured inventory CSV or XLSX.")
    parser.add_argument("--validate", action="store_true", help="Audit inventory and icons without opening a browser or changing files.")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config, "papers")
        if args.workbook is not None:
            settings["workbook"] = args.workbook.expanduser().resolve()
        if args.validate:
            report = audit_inventory(settings["workbook"], "papers", icon_dir=settings["paper_processing_icon_dir"])
            print(json.dumps(display_paths(report), indent=2, ensure_ascii=False))
            return 0
        launch(settings)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Article literature retrieval: {display_paths(str(exc))}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
