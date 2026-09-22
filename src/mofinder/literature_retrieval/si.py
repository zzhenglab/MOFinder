"""Desktop supporting-information literature retrieval using calibrated publisher profiles.

Publisher profiles are supplied as neutral identifiers in the input inventory.
The desktop workflow retains the original navigation, image matching, retries,
and status updates. GUI dependencies load only when the application is launched.
"""
from __future__ import annotations

# Timing defaults; override through the literature retrieval configuration.
BROWSER_OPEN_WAIT              = 2.0
WAIT_AFTER_NAV                 = 4.0
ICON_CONFIDENCE                = 0.87
ICON_SEARCH_TICK               = 0.6

# Profile W scrolling
PUBLISHER_W_SCROLL_TOTAL_SEC         = 10.0
PUBLISHER_W_SCROLL_STEP_SEC          = 0.03
PUBLISHER_W_SCROLL_UP_COUNT          = 5

# Retries
MAX_RETRIES_PER_ROW            = 2

# Save after this many attempted rows in block 2.
SAVE_EVERY_PENDING             = 20
DESKTOP_RESET_PAUSE            = 0.5

# Save dialog typing cadence
STEP_PAUSE                     = 0.35
ICON_BEFORE_RENAME_WAIT        = 2.0
POST_ENTER_WAIT                = 0.7

# Cookie buttons presence windows
ACCEPT_COOKIE_WAIT             = 5.0

# Journal policy
MAX_JOURNAL_FAILS_BASE         = 5
JOURNAL_SUCCESS_THRESHOLD_FOR_BOOST = 2
JOURNAL_SUCCESS_BOOST_MULTIPLIER    = 2

# Anti-idle
ANTI_IDLE_SECONDS              = 170
ANTI_IDLE_PIXELS               = 2

# Excel and calibration
DEFAULT_EXCEL_PATH             = "data/local/literature_retrieval/si_inventory.csv"
APP_SETTINGS                   = "data/local/literature_retrieval/app_settings_si.json"
CAL_FILE                       = "data/local/literature_retrieval/si_downloader_calibration.json"
DEFAULT_GLOBAL_SAVE_XY         = None

# Hyperlink policy
APPLY_HYPERLINKS_ON_FINAL_SAVE = True
# ==========================================================================

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
from typing import TYPE_CHECKING, Optional, Dict, Tuple, List

from mofinder.display import display_path, display_paths

if TYPE_CHECKING:
    import pandas as pd
from .common import (
    audit_inventory,
    load_settings,
    prepare_local_inventory,
    publisher_key,
    read_inventory,
    write_inventory,
)

# Desktop dependencies load when the GUI is launched.
HAS_CV2 = False
ICON_DIR = Path("data/literature_retrieval_assets/icons")
DOWNLOAD_DIR = Path("data/raw/si")
SETTINGS = {}


def _load_gui_dependencies():
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
    # Moving the pointer to a screen corner provides an additional stop action.
    pyautogui.FAILSAFE = True


IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
IS_LINUX = not IS_MAC and not IS_WIN

SUPPORTED_PREFIXES = ["publisher_W", "publisher_A", "publisher_R", "publisher_S", "publisher_E"]

# Configure a representative URL for each profile on the local machine.
SAMPLE_URLS = {}

CANDIDATE_SI_EXTS = [".pdf", ".docx", ".doc", ".zip", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".txt", ".rar", ".gz", ".7z"]

abort_now = False
save_requested = False


def _stop_on_failsafe(error):
    """Preserve the desktop corner stop through broad image-search handlers."""
    global abort_now, save_requested
    gui = globals().get("pyautogui")
    if gui is not None and isinstance(error, gui.FailSafeException):
        abort_now = True
        save_requested = True
        raise SystemExit("Stopped by the pointer corner fail-safe.") from error


def log(*args):
    ts = time.strftime("[%H:%M:%S]")
    print(ts, *(display_paths(str(arg)) for arg in args), flush=True)

# ---------- helpers ----------
def doi_to_link(doi: str) -> str:
    doi = str(doi).strip()
    if not doi or doi.lower() == "nan": return ""
    if doi.lower().startswith("http"): return doi
    return f"https://doi.org/{doi}"

def doi_to_base(doi: str) -> str:
    base = str(doi).strip().replace("/", "_")
    base = re.sub(r'[<>:"\\|?*\n\r\t]', "_", base)
    return base

def doi_stem(doi: str) -> str:
    return doi_to_base(doi) + "_SI"

def doi_journal_key(doi: str) -> str:
    if not doi or "/" not in doi: return ""
    pfx, sfx = doi.split("/", 1)
    sfx5 = sfx[:5] if len(sfx) >= 5 else sfx
    return f"{pfx}/{sfx5}".lower()

def ensure_si_download_dir(excel_path: Path) -> Path:
    out = Path(DOWNLOAD_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out

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

CHROME_FLAGS = [
    "--disable-session-crashed-bubble",
    "--no-first-run",
    "--incognito",
    "--start-maximized",
    "--start-fullscreen",
]

def open_in_chrome(url: str, new_window=False):
    exe_list = _chrome_candidates()
    args_flags = list(CHROME_FLAGS)
    if new_window: args_flags.append("--new-window")
    for exe in exe_list:
        if not exe: continue
        try:
            log("Launching Chrome:", exe)
            subprocess.Popen([exe, *args_flags, url])
            time.sleep(BROWSER_OPEN_WAIT)
            try:
                if IS_MAC: pyautogui.hotkey("command", "ctrl", "f")
                elif IS_WIN: pyautogui.hotkey("winleft", "up"); time.sleep(0.2); pyautogui.press("f11")
                else: pyautogui.press("f11")
            except Exception as error:
                _stop_on_failsafe(error)
                pass
            return
        except Exception as error:
            _stop_on_failsafe(error)
            continue
    try:
        webbrowser.open_new_tab(url)
        time.sleep(BROWSER_OPEN_WAIT)
        if IS_WIN: pyautogui.hotkey("winleft", "up"); time.sleep(0.2); pyautogui.press("f11")
        elif IS_MAC: pyautogui.hotkey("command", "ctrl", "f")
        else: pyautogui.press("f11")
    except Exception as error:
        _stop_on_failsafe(error)
        pass

def hotkey_address_bar():
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "l")

def go_to_address_bar_and_open(link: str):
    hotkey_address_bar(); time.sleep(0.2)
    pyperclip.copy(link); pyautogui.hotkey("command" if IS_MAC else "ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); time.sleep(WAIT_AFTER_NAV)

# ---------- calibration ----------
def load_calibration() -> dict:
    data = {}
    if os.path.exists(CAL_FILE):
        try:
            with open(CAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as error:
            _stop_on_failsafe(error)
            data = {}
    data.setdefault("GLOBAL_SAVE", {})
    data["GLOBAL_SAVE"].setdefault("save_xy", DEFAULT_GLOBAL_SAVE_XY)
    return data

def save_calibration(data: dict):
    try:
        Path(CAL_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(CAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as error:
        _stop_on_failsafe(error)
        pass

# ---------- SI normalization ----------
def si_norm(val) -> str:
    s = str(val).strip().lower()
    if s in ("1", "1.0", "true", "yes", "y"): return "1"
    if s in ("0", "0.0", "false", "no", "n"): return "0"
    return ""

# ---------- Excel I/O ----------
def _apply_hyperlinks(path: Path, df: pd.DataFrame):
    write_inventory(df, path, hyperlinks=True)

def load_and_prepare_excel(path: Path) -> pd.DataFrame:
    log("Loading inventory:", path)
    df = read_inventory(path)
    if "DOI" not in df.columns: raise ValueError("Missing column: DOI")
    if "Publisher" not in df.columns: raise ValueError("Missing column: Publisher")
    df["DOI"] = df["DOI"].astype(str)
    df["DOI Link"] = df["DOI"].apply(doi_to_link)
    if "SI Downloaded" not in df.columns: df["SI Downloaded"] = ""
    df["SI Downloaded"] = df["SI Downloaded"].apply(si_norm)
    write_inventory(df, path, hyperlinks=False)
    log("Inventory prepared. Rows:", len(df))
    return df

def save_progress(df: pd.DataFrame, path: Path, *, apply_links: bool = False):
    if apply_links:
        _apply_hyperlinks(path, df)
    else:
        write_inventory(df, path, hyperlinks=False)
    log("Saved inventory:", path)

# ---------- icon search ----------
ICON_EXTS = (".png", ".jpg", ".jpeg", ".bmp")

def icon_path(icon_dir: Path, name: str) -> Optional[Path]:
    for ext in ICON_EXTS:
        p = icon_dir / f"{name}{ext}"
        if p.exists(): return p
    return None

def locate_center_on_screen(image_path: Path, confidence: float) -> Optional[Tuple[int, int]]:
    try:
        box = pyautogui.locateCenterOnScreen(str(image_path), confidence=confidence) if HAS_CV2 else pyautogui.locateCenterOnScreen(str(image_path))
        return (int(box.x), int(box.y)) if box else None
    except Exception as error:
        _stop_on_failsafe(error)
        return None

def wait_for_image(icon_dir: Path, name: str, timeout: float) -> Optional[Tuple[int, int]]:
    img = icon_path(icon_dir, name)
    if not img:
        return None
    t0 = time.time()
    while time.time() - t0 < timeout:
        if abort_now: raise SystemExit("Aborted")
        pos = locate_center_on_screen(img, ICON_CONFIDENCE)
        if pos: return pos
        time.sleep(ICON_SEARCH_TICK)
    return None

def click_icon(icon_dir: Path, name: str, timeout: float, post_wait: float = 0.0) -> bool:
    pos = wait_for_image(icon_dir, name, timeout)
    if not pos: return False
    pyautogui.moveTo(pos[0], pos[1], duration=0.20); time.sleep(0.05)
    pyautogui.click()
    if post_wait > 0: time.sleep(post_wait)
    return True

# ---------- scrolling ----------
def fast_scroll_down(seconds: float):
    t_end = time.time() + seconds
    while time.time() < t_end:
        if abort_now: raise SystemExit("Aborted")
        pyautogui.press("pagedown")
        time.sleep(PUBLISHER_W_SCROLL_STEP_SEC)

def press_down_n(n: int, interval: float = 0.03):
    for _ in range(n):
        pyautogui.press("down"); time.sleep(interval)

def press_up_n(n: int, interval: float = 0.03):
    for _ in range(n):
        pyautogui.press("up"); time.sleep(interval)
# ---------- desktop helpers ----------

def move_cursor_top_center(margin_y: int = 8):
    w, h = pyautogui.size()
    pyautogui.moveTo(w // 2, max(1, margin_y), duration=0.2)


def reset_to_desktop(include_enter=True):
    if IS_WIN:
        pyautogui.hotkey("winleft", "d"); time.sleep(DESKTOP_RESET_PAUSE)
        if include_enter: pyautogui.press("enter"); time.sleep(DESKTOP_RESET_PAUSE)
        w, h = pyautogui.size()
        pyautogui.click(w // 2, h // 2); time.sleep(DESKTOP_RESET_PAUSE)

def safe_reset_to_desktop(include_enter=True):
    try:
        reset_to_desktop(include_enter)
    except Exception as e:
        _stop_on_failsafe(e)
        log("safe_reset_to_desktop error:", e)

def close_all_chrome():
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", "chrome.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif IS_MAC:
            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            subprocess.run(["pkill", "-x", "Google Chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            for cmd in (["pkill", "-x", "google-chrome"], ["pkill", "-x", "chrome"], ["pkill", "chrome"]):
                try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as error:
                    _stop_on_failsafe(error)
                    pass
    except Exception as e:
        _stop_on_failsafe(e)
        log("close_all_chrome error:", e)
    time.sleep(0.4)

def ensure_chrome_closed(retries: int = 2):
    for _ in range(retries):
        close_all_chrome()
        time.sleep(0.2)

# ---------- save dialog ----------
def fresh_file_ready_any(target_base_path: Path, timeout: float = 90.0) -> Optional[Path]:
    tmp_exts = [".crdownload", ".part", ".tmp"]
    folder = target_base_path.parent
    stem = target_base_path.name
    t0 = time.time()
    while time.time() - t0 < timeout:
        if abort_now: raise SystemExit("Aborted")
        p0 = folder / stem
        if p0.exists() and p0.stat().st_size > 0 and not any(Path(str(p0) + e).exists() for e in tmp_exts):
            return p0
        for ext in CANDIDATE_SI_EXTS:
            p = folder / (stem + ext)
            if p.exists() and p.stat().st_size > 0 and not any(Path(str(p) + e).exists() for e in tmp_exts):
                return p
        time.sleep(0.25)
    return None

def rename_in_save_dialog(target_base_path: Path, coords_save_xy: Tuple[int, int]) -> Optional[Path]:
    sx, sy = coords_save_xy
    time.sleep(ICON_BEFORE_RENAME_WAIT)
    pyautogui.moveTo(int(sx), int(sy), duration=0.2); time.sleep(0.05)
    pyautogui.click(); time.sleep(STEP_PAUSE)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a"); time.sleep(STEP_PAUSE)
    pyautogui.press("delete"); time.sleep(STEP_PAUSE)
    pyperclip.copy(str(target_base_path))
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v"); time.sleep(STEP_PAUSE)
    pyautogui.press("enter"); time.sleep(POST_ENTER_WAIT)
    pyautogui.press("enter"); time.sleep(0.3)
    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2)
    return fresh_file_ready_any(target_base_path, timeout=90)

# ---------- publisher flows ----------
def publisher_w_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path):
    time.sleep(5.0)
    fast_scroll_down(PUBLISHER_W_SCROLL_TOTAL_SEC)
    if not wait_for_image(icon_dir, "publisher_W_SI_1", timeout=3.0):
        fast_scroll_down(PUBLISHER_W_SCROLL_TOTAL_SEC)
        if not wait_for_image(icon_dir, "publisher_W_SI_1", timeout=3.0):
            return "SKIP"
    press_up_n(PUBLISHER_W_SCROLL_UP_COUNT, interval=0.02)
    for _ in range(9):
        pos = wait_for_image(icon_dir, "publisher_W_SI_2", timeout=2.0)
        if pos:
            pyautogui.moveTo(pos[0], pos[1], duration=0.2); pyautogui.click()
            break
        press_up_n(PUBLISHER_W_SCROLL_UP_COUNT, interval=0.02)
    else:
        return False
    time.sleep(2.0)
    if click_icon(icon_dir, "publisher_W_SI_3a", timeout=2.0) or click_icon(icon_dir, "publisher_W_SI_3aa", timeout=2.0):
        time.sleep(3.0)
        if not click_icon(icon_dir, "publisher_W_SI_4", timeout=7.0, post_wait=0.8):
            return False
        return bool(rename_in_save_dialog(target_base, coords_save_xy))
    if click_icon(icon_dir, "publisher_W_SI_3b", timeout=2.0, post_wait=1.0) or click_icon(icon_dir, "publisher_W_SI_3bb", timeout=3.0, post_wait=1.0):
        return bool(rename_in_save_dialog(target_base, coords_save_xy))
    return False

def publisher_a_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    pos_hdr = wait_for_image(icon_dir, "publisher_A_SI_1", timeout=8.0)
    if not pos_hdr:
        pos_hdr = wait_for_image(icon_dir, "publisher_A_SI_1b", timeout=5.0)
    if not pos_hdr:
        pos_hdr = wait_for_image(icon_dir, "publisher_A_SI_1c", timeout=3.0)
    if pos_hdr:
        pyautogui.moveTo(pos_hdr[0], pos_hdr[1], duration=0.2); pyautogui.click()
        time.sleep(2.0)
        if click_icon(icon_dir, "publisher_A_SI_2a", timeout=2.0) or click_icon(icon_dir, "publisher_A_SI_2aa", timeout=2.0) or click_icon(icon_dir, "publisher_A_SI_2b", timeout=4.0):
            time.sleep(3.0)
            if not click_icon(icon_dir, "publisher_A_SI_3", timeout=6.0, post_wait=0.8): return False
            return bool(rename_in_save_dialog(target_base, coords_save_xy))
        if click_icon(icon_dir, "publisher_A_SI_2c", timeout=3.0) or click_icon(icon_dir, "publisher_A_SI_2d", timeout=5.0):
            return bool(rename_in_save_dialog(target_base, coords_save_xy))
        return False
    for _ in range(5):
        press_down_n(10, interval=0.02)
        if click_icon(icon_dir, "publisher_A_SI_2a", timeout=5.0) or click_icon(icon_dir, "publisher_A_SI_2b", timeout=5.0):
            time.sleep(4.0)
            if not click_icon(icon_dir, "publisher_A_SI_3", timeout=6.0, post_wait=0.8): return False
            return bool(rename_in_save_dialog(target_base, coords_save_xy))
        if click_icon(icon_dir, "publisher_A_SI_2c", timeout=5.0) or click_icon(icon_dir, "publisher_A_SI_2d", timeout=5.0):
            return bool(rename_in_save_dialog(target_base, coords_save_xy))
    return False

def publisher_r_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    for _ in range(4):
        if click_icon(icon_dir, "publisher_R_SI_1", timeout=5.0): break
        press_down_n(10, interval=0.02); time.sleep(2.0)
    else: return False
    time.sleep(5.0)
    if not click_icon(icon_dir, "publisher_R_SI_2", timeout=6.0, post_wait=0.8): return False
    return bool(rename_in_save_dialog(target_base, coords_save_xy))

def publisher_s_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    click_icon(icon_dir, "publisher_S_SI_Accept", timeout=ACCEPT_COOKIE_WAIT, post_wait=0.5)
    click_icon(icon_dir, "publisher_S_SI_Accept2", timeout=ACCEPT_COOKIE_WAIT, post_wait=0.5)
    def click_any_2_then_save():
        if click_icon(icon_dir, "publisher_S_SI_1", timeout=2.0) or \
            click_icon(icon_dir, "publisher_S_SI_2", timeout=1.0) or \
           click_icon(icon_dir, "publisher_S_SI_2b", timeout=1.0) or \
           click_icon(icon_dir, "publisher_S_SI_2c", timeout=1.0):
            time.sleep(5.0)


            if wait_for_image(icon_dir,"publisher_S_SI_3b", timeout=3.0):
                return bool(rename_in_save_dialog(target_base, coords_save_xy))
            if click_icon(icon_dir, "publisher_S_SI_3", timeout=6.0, post_wait=0.8):
                return bool(rename_in_save_dialog(target_base, coords_save_xy))
        return False
    fast_scroll_down(10.0)
    for _ in range(10):
        press_up_n(10, interval=0.02)
        if click_any_2_then_save():
            return True
    return False

def publisher_e_si_flow(icon_dir: Path, coords_save_xy: Tuple[int, int], target_base: Path) -> bool:
    click_icon(icon_dir, "publisher_E_SI_Accept", timeout=1, post_wait=0.5)
    click_icon(icon_dir, "publisher_E_SI_Accept2", timeout=1, post_wait=0.5)
    click_icon(icon_dir, "publisher_E_SI_Accept3", timeout=1, post_wait=0.5)
    click_icon(icon_dir, "publisher_E_SI_1", timeout=1.0)
    click_icon(icon_dir, "publisher_E_SI_1b", timeout=1.0)
    for _ in range(8):
        if click_icon(icon_dir, "publisher_E_SI_2", timeout=1.0): break
        elif click_icon(icon_dir, "publisher_E_SI_2b", timeout=1.0): break
        press_down_n(20, interval=0.02); time.sleep(0.5)
    else: return False

    time.sleep(3.0)
    click_icon(icon_dir, "publisher_E_SI_3", timeout=2, post_wait=0.5)
    return bool(rename_in_save_dialog(target_base, coords_save_xy))

PUBLISHER_FLOW = {
    "publisher_W": publisher_w_si_flow,
    "publisher_A": publisher_a_si_flow,
    "publisher_R": publisher_r_si_flow,
    "publisher_S": publisher_s_si_flow,
    "publisher_E": publisher_e_si_flow,
}

# ---------- app with two blocks ----------
class App:
    def __init__(self, root, workbook_path=None):
        self.root = root
        self.root.title("SI downloader")

        self.ui_queue = queue.Queue()
        self.excel_path_var = tk.StringVar(value=str(workbook_path) if workbook_path is not None else (self._load_last_excel() or DEFAULT_EXCEL_PATH))
        self.status_var = tk.StringVar(value="Ready")
        self.stats_var = tk.StringVar(value="Left: 0  Success: 0  Fail: 0  ETA: 00:00")
        self.cal_data = load_calibration()

        self.test_mode_var = tk.BooleanVar(value=False)
        self.double_check_var = tk.BooleanVar(value=False)

        self.succ_count = 0
        self.fail_count = 0

        self.anti_idle_stop = None
        self.anti_idle_thread = None

        pad = 6
        frm = ttk.Frame(root, padding=pad); frm.pack(fill="both", expand=True)

        row_file = ttk.Frame(frm); row_file.pack(fill="x", pady=(pad, 0))
        ttk.Label(row_file, text="Inventory file:").pack(side="left")
        ttk.Entry(row_file, textvariable=self.excel_path_var, width=80).pack(side="left", padx=(pad, pad))
        ttk.Button(row_file, text="Browse", command=self.pick_file).pack(side="left")
        ttk.Checkbutton(row_file, text="Test mode (5 rows)", variable=self.test_mode_var).pack(side="left", padx=8)
        ttk.Checkbutton(row_file, text="Double check mode (only 0s)", variable=self.double_check_var).pack(side="left", padx=8)

        row_sync = ttk.Frame(frm); row_sync.pack(fill="x", pady=(pad, 0))
        ttk.Button(row_sync, text="Sync from folder → inventory (block 1)", command=self.block1_sync).pack(side="left")

        ttk.Label(frm, text="Publishers").pack(anchor="w", pady=(pad, 0))
        pub_row = ttk.Frame(frm); pub_row.pack(fill="x", pady=2)
        for name in SUPPORTED_PREFIXES:
            ttk.Button(pub_row, text=f"Open sample: {name}", command=lambda n=name: self.open_sample(n)).pack(side="left", padx=3)

        ttk.Label(frm, text="Save dialog - FILE NAME box XY").pack(anchor="w", pady=(pad, 0))
        self.save_box_var = tk.StringVar(value=self.save_box_text())
        row_save = ttk.Frame(frm); row_save.pack(fill="x", pady=2)
        ttk.Label(row_save, textvariable=self.save_box_var, width=40, anchor="w").pack(side="left")
        ttk.Button(row_save, text="Set FILE NAME box XY (F8, then F9)", command=self.capture_global_save_xy).pack(side="left", padx=6)

        ctrl = ttk.Frame(frm); ctrl.pack(fill="x", pady=(pad, 0))
        ttk.Button(ctrl, text="Start (block 2)", command=self.start).pack(side="left", padx=(0, pad))
        ttk.Button(ctrl, text="STOP now", command=self.stop_now).pack(side="left")

        ttk.Label(frm, textvariable=self.stats_var).pack(fill="x", pady=(pad, 0))
        ttk.Label(frm, textvariable=self.status_var).pack(fill="x", pady=(pad, 0))

        tracker = ttk.Frame(frm); tracker.pack(fill="x", pady=(pad, 0))
        self.mouse_xy_var = tk.StringVar(value="Mouse XY: ...")
        self.track_mouse = tk.BooleanVar(value=False)
        ttk.Checkbutton(tracker, text="Track mouse XY", variable=self.track_mouse, command=self.update_mouse_tracker).pack(side="left")
        ttk.Label(tracker, textvariable=self.mouse_xy_var).pack(side="left", padx=8)

        ttk.Label(frm, text="Hotkeys: Ctrl+Shift+S save now, Ctrl+Shift+X STOP now.").pack(fill="x", pady=(pad, 0))

        ttk.Label(frm, text="This workflow closes Chrome windows during each download. Use a dedicated session.").pack(fill="x", pady=(pad, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_hotkeys()
        self.root.after(150, self.poll_ui)
        self.root.after(120, self.update_mouse_tracker)

    # window close handler
    def on_close(self):
        self.stop_now()
        def _wait_then_close():
            if hasattr(self, "worker") and getattr(self.worker, "is_alive", lambda: False)():
                self.root.after(200, _wait_then_close)
            else:
                try: self.stop_anti_idle()
                except Exception as error:
                    _stop_on_failsafe(error)
                    pass
                ensure_chrome_closed()
                self.root.destroy()
        _wait_then_close()

    # persistence
    def _load_last_excel(self) -> Optional[str]:
        try:
            if os.path.exists(APP_SETTINGS):
                with open(APP_SETTINGS, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return cfg.get("last_excel")
        except Exception as error:
            _stop_on_failsafe(error)
            return None
        return None

    def _save_last_excel(self, path: str):
        try:
            Path(APP_SETTINGS).parent.mkdir(parents=True, exist_ok=True)
            with open(APP_SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"last_excel": path}, f, indent=2)
        except Exception as error:
            _stop_on_failsafe(error)
            pass

    def save_box_text(self):
        g = load_calibration().get("GLOBAL_SAVE", {})
        sav = tuple(g.get("save_xy")) if g.get("save_xy") else None
        return f"FILE NAME BOX XY: {sav}"

    def update_mouse_tracker(self):
        if self.track_mouse.get():
            p = pyautogui.position(); self.mouse_xy_var.set(f"Mouse XY: ({p.x}, {p.y})")
            self.root.after(120, self.update_mouse_tracker)

    def pick_file(self):
        path = filedialog.askopenfilename(title="Pick inventory file", filetypes=[("Inventory", "*.csv *.xlsx")])
        if path:
            self.excel_path_var.set(path); self._save_last_excel(path)

    def _working_inventory_path(self, path):
        """Continue a local inventory without writing into its source workbook."""
        settings = dict(SETTINGS)
        settings["workbook"] = Path(path)
        working = prepare_local_inventory(settings)
        self.excel_path_var.set(str(working))
        self._save_last_excel(str(working))
        return working

    def open_sample(self, name):
        url = SAMPLE_URLS.get(name)
        if not url:
            messagebox.showinfo("Sample URL", f"Set sample_urls.{name} in the literature retrieval configuration.")
            return
        ensure_chrome_closed()
        open_in_chrome("about:blank", new_window=True); time.sleep(BROWSER_OPEN_WAIT)
        go_to_address_bar_and_open(url)

    def _capture_f8_f9_points(self):
        points = []; done_flag = {"done": False}
        def on_press(key):
            try:
                if key == pynput_keyboard.Key.f8:
                    p = pyautogui.position(); points.append((p.x, p.y))
                elif key == pynput_keyboard.Key.f9:
                    done_flag["done"] = True; return False
            except Exception as error:
                _stop_on_failsafe(error)
                return False
        listener = pynput_keyboard.Listener(on_press=on_press); listener.start()
        while listener.is_alive():
            if done_flag["done"]: break
            self.root.update(); time.sleep(0.05)
        return points

    def capture_global_save_xy(self):
        messagebox.showinfo("Save-box capture", "Open any Save dialog. Hover FILE NAME box, press F8. Press F9 to finish.")
        points = self._capture_f8_f9_points()
        if not points:
            messagebox.showwarning("Save-box", "No position captured."); return
        pos = points[-1]
        cal = load_calibration()
        cal.setdefault("GLOBAL_SAVE", {})["save_xy"] = [int(pos[0]), int(pos[1])]
        save_calibration(cal)
        self.save_box_var.set(self.save_box_text())
        messagebox.showinfo("Saved", f"FILE NAME BOX XY saved at {pos}")

    # hotkeys
    def start_hotkeys(self):
        def on_save():
            global save_requested
            save_requested = True
            log("Hotkey save requested")
        def on_stop_now():
            global abort_now, save_requested
            save_requested = True
            abort_now = True
            log("Hotkey STOP now")
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
                    m_total = payload.get("eta_secs", 0) // 60
                    h, m = divmod(m_total, 60)
                    self.stats_var.set(f"Left: {left}  Success: {succ}  Fail: {fail}  ETA: {h:02d}:{m:02d}")
                elif kind == "restore":
                    try: self.root.deiconify(); self.root.lift()
                    except Exception as error:
                        _stop_on_failsafe(error)
                        pass
        except queue.Empty:
            pass
        self.root.after(150, self.poll_ui)

    # anti-idle
    def start_anti_idle(self):
        if getattr(self, "anti_idle_thread", None) and self.anti_idle_thread.is_alive():
            return
        self.anti_idle_stop = threading.Event()
        def runner():
            while not self.anti_idle_stop.wait(ANTI_IDLE_SECONDS):
                try:
                    x, y = pyautogui.position()
                    pyautogui.moveTo(x, max(1, y-ANTI_IDLE_PIXELS), duration=0.05)
                    pyautogui.moveTo(x, y, duration=0.05)
                except Exception as error:
                    _stop_on_failsafe(error)
                    pass
        self.anti_idle_thread = threading.Thread(target=runner, daemon=True)
        self.anti_idle_thread.start()
        log("Anti-idle thread started")

    def stop_anti_idle(self):
        if getattr(self, "anti_idle_stop", None):
            self.anti_idle_stop.set()
            log("Anti-idle thread stop requested")

    # BLOCK 1
    def block1_sync(self):
        p = self.excel_path_var.get().strip()
        if not p:
            messagebox.showerror("Error", "Pick an inventory file first."); return
        excel_path = Path(p)
        if not excel_path.exists():
            messagebox.showerror("Error", f"File not found:\n{display_path(excel_path)}"); return

        try:
            excel_path = self._working_inventory_path(excel_path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Inventory", display_paths(str(error))); return
        df = load_and_prepare_excel(excel_path)
        si_dir = ensure_si_download_dir(excel_path)

        df["SI Downloaded"] = df["SI Downloaded"].apply(si_norm)

        col_before = df["SI Downloaded"]
        cnt_1_before = int((col_before == "1").sum())
        cnt_0_before = int((col_before == "0").sum())
        cnt_empty_before = int((col_before == "").sum())

        folder_files = [f for f in si_dir.iterdir() if f.is_file()]
        stems = {f.stem for f in folder_files}
        in_folder = len(folder_files)

        target_stems = df["DOI"].astype(str).map(doi_stem)

        to_update_mask = (col_before == "") & (target_stems.isin(stems))
        updated_stems = set(target_stems[to_update_mask].tolist())
        df.loc[to_update_mask, "SI Downloaded"] = "1"
        updates_applied = int(to_update_mask.sum())

        already_one_stems = set(target_stems[col_before == "1"].tolist())
        unmatched_in_folder = stems - updated_stems - already_one_stems

        save_progress(df, excel_path, apply_links=APPLY_HYPERLINKS_ON_FINAL_SAVE)

        col_after = df["SI Downloaded"].apply(si_norm)
        cnt_1_after = int((col_after == "1").sum())
        cnt_0_after = int((col_after == "0").sum())
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
            f"Not applied in this pass: {len(unmatched_in_folder)} (see console)."
        )

    # BLOCK 2
    def start(self):
        global abort_now, save_requested
        abort_now = False; save_requested = False

        p = self.excel_path_var.get().strip()
        if not p:
            messagebox.showerror("Error", "Pick an inventory file first."); return
        excel_path = Path(p)
        if not excel_path.exists():
            messagebox.showerror("Error", f"File not found:\n{display_path(excel_path)}"); return

        coords_save = load_calibration().get("GLOBAL_SAVE", {}).get("save_xy")
        if not coords_save or len(coords_save) != 2:
            messagebox.showwarning("Calibration", "Set the Save dialog FILE NAME box coordinates before starting.")
            return
        try:
            excel_path = self._working_inventory_path(excel_path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Inventory", display_paths(str(error))); return
        df_main = load_and_prepare_excel(excel_path)

        work = df_main[["DOI", "DOI Link", "SI Downloaded"]].copy()
        work["DOI"] = work["DOI"].astype(str).str.strip()
        work["SI Downloaded"] = work["SI Downloaded"].apply(si_norm)
        work["TargetStem"] = work["DOI"].apply(doi_stem)

        s_col = work["SI Downloaded"]
        self.succ_count = int((s_col == "1").sum())
        self.fail_count = int((s_col == "0").sum())

        self.start_anti_idle()

        self.root.update(); self.root.geometry("320x120+0+0"); self.root.iconify()

        def worker():
            try:
                self.process_rows(df_main, work, excel_path, self.double_check_var.get())
                self.ui_queue.put(("status", "Done.")); self.ui_queue.put(("restore", None))
            except SystemExit:
                self.ui_queue.put(("status", "Stopped.")); self.ui_queue.put(("restore", None))
            except Exception as e:
                _stop_on_failsafe(e)
                log("Worker error:", e)
                self.ui_queue.put(("status", f"Error: {e}")); self.ui_queue.put(("restore", None))
            finally:
                try:
                    self.stop_anti_idle()
                except Exception as error:
                    _stop_on_failsafe(error)
                    pass
                ensure_chrome_closed()

        self.worker = threading.Thread(target=worker, daemon=True); self.worker.start()

    def stop_now(self):
        global abort_now, save_requested
        save_requested = True
        abort_now = True
        self.ui_queue.put(("status", "STOP now requested."))
        log("STOP requested")

    def process_rows(self, df_main: pd.DataFrame, work: pd.DataFrame, excel_path: Path, double_check_mode: bool):
        global save_requested
        si_dir = ensure_si_download_dir(excel_path)
        coords_save = tuple(load_calibration().get("GLOBAL_SAVE", {}).get("save_xy") or [])
        if not coords_save or len(coords_save) != 2:
            raise SystemExit("Global FILE NAME BOX XY not set.")

        icon_dir = Path(ICON_DIR)
        if not icon_dir.exists():
            raise SystemExit(f"Icon folder not found:\n{icon_dir}\nPut SI icons in this folder.")

        col_raw = work["SI Downloaded"]
        if double_check_mode:
            pending_mask = (col_raw == "0")
            total_to_check = int(pending_mask.sum())
            log(f"[Block 2] Double check mode: total rows with 0 = {total_to_check}")
        else:
            pending_mask = ~(col_raw.isin(["0", "1"]))
            total_to_check = int(pending_mask.sum())
            log(f"[Block 2] Normal mode: total pending empties = {total_to_check}")

        pending_indices = work.index[pending_mask].tolist()
        # Test mode limits the pending inventory to five rows without changing its order.
        if self.test_mode_var.get():
            pending_indices = pending_indices[:5]

        self.pending_set = set(pending_indices)
        self.start_time = time.time()
        processed_pending_since_save = 0
        processed_since_start = 0

        j_fail_counts: Dict[str, int] = {}
        j_success_counts: Dict[str, int] = {}

        def record_fail(jkey: str):
            if not jkey: return
            j_fail_counts[jkey] = j_fail_counts.get(jkey, 0) + 1

        def record_success(jkey: str):
            if not jkey: return
            j_success_counts[jkey] = j_success_counts.get(jkey, 0) + 1

        def allowed_fail_limit(jkey: str) -> int:
            base = MAX_JOURNAL_FAILS_BASE
            succ = j_success_counts.get(jkey, 0)
            return base * (JOURNAL_SUCCESS_BOOST_MULTIPLIER if succ > JOURNAL_SUCCESS_THRESHOLD_FOR_BOOST else 1)

        def flush(force=False):
            nonlocal processed_pending_since_save
            global save_requested
            if processed_pending_since_save >= SAVE_EVERY_PENDING or save_requested or force:
                df_out = df_main.copy()
                df_out["SI Downloaded"] = work["SI Downloaded"]
                save_progress(df_out, excel_path, apply_links=(APPLY_HYPERLINKS_ON_FINAL_SAVE and force))
                log("[Block 2] Saved workbook (batch)")
                processed_pending_since_save = 0
                save_requested = False

        def update_stats():
            left = len(self.pending_set)
            elapsed = max(time.time() - self.start_time, 1.0)
            done = max(processed_since_start, 1)
            eta_secs = int(left * elapsed / done)
            self.ui_queue.put(("stats", {"left": left, "succ": self.succ_count, "fail": self.fail_count, "eta_secs": eta_secs}))

        update_stats()

        try:
            for idx in pending_indices:
                if abort_now: raise SystemExit("Aborted")
                if idx not in self.pending_set: continue

                doi = work.at[idx, "DOI"]
                pub_key = publisher_key(df_main.at[idx, "Publisher"])
                jkey = doi_journal_key(doi)
                initial_si = work.at[idx, "SI Downloaded"]

                log(f"[Row {idx}] start DOI='{doi}' Pub='{pub_key}' JKey='{jkey}'")

                if jkey:
                    allowed = allowed_fail_limit(jkey)
                    if j_fail_counts.get(jkey, 0) >= allowed:
                        log(f"[Row {idx}] skip journal threshold (fails={j_fail_counts.get(jkey,0)} allowed={allowed})")
                        self.pending_set.discard(idx); update_stats()
                        continue

                target_base = (si_dir / work.at[idx, "TargetStem"]).resolve()
                link = doi_to_link(doi)
                work.at[idx, "DOI Link"] = link

                existing = fresh_file_ready_any(target_base, timeout=0.3)
                if existing:
                    work.at[idx, "SI Downloaded"] = "1"
                    self.succ_count += 1; record_success(jkey)
                    log(f"[Row {idx}] already saved -> mark 1 ({existing.name})")
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    processed_pending_since_save += 1
                    flush()
                    update_stats()
                    ensure_chrome_closed()
                    continue

                ok = False
                skip_row = False
                attempted_flow = False

                for attempt in range(1, MAX_RETRIES_PER_ROW + 1):
                    if abort_now: raise SystemExit("Aborted")
                    log(f"[Row {idx}] attempt {attempt}/{MAX_RETRIES_PER_ROW}")
                    try:
                        ensure_chrome_closed()
                        safe_reset_to_desktop(include_enter=True)
                        open_in_chrome("about:blank", new_window=True); time.sleep(BROWSER_OPEN_WAIT)
                        go_to_address_bar_and_open(link)
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
                        _stop_on_failsafe(e)
                        log(f"[Row {idx}] error: {e}")
                        ok = False
                    finally:
                        ensure_chrome_closed()
                        safe_reset_to_desktop(include_enter=True)
                        move_cursor_top_center()
                    log(f"[Row {idx}] result attempt {attempt}: {ok}{' (SKIP)' if skip_row else ''}")
                    if skip_row or ok:
                        break

                if skip_row:
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    update_stats()
                    ensure_chrome_closed()
                    continue

                if ok and fresh_file_ready_any(target_base, timeout=1.0):
                    work.at[idx, "SI Downloaded"] = "1"
                    self.succ_count += 1; record_success(jkey)
                    log(f"[Row {idx}] mark 1")
                    self.pending_set.discard(idx)
                    processed_since_start += 1
                    processed_pending_since_save += 1
                    flush()
                    update_stats()
                    ensure_chrome_closed()
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
                    ensure_chrome_closed()
                    continue

                log(f"[Row {idx}] no flow attempted -> keep as '{initial_si}'")
                self.pending_set.discard(idx)
                processed_since_start += 1
                update_stats()
                ensure_chrome_closed()

        finally:
            flush(force=True)
            update_stats()
            ensure_chrome_closed()
            log("[Block 2] All done")

# ---------- application entry points ----------
_TUNING_KEYS = (
    "BROWSER_OPEN_WAIT", "WAIT_AFTER_NAV", "ICON_CONFIDENCE", "ICON_SEARCH_TICK",
    "PUBLISHER_W_SCROLL_TOTAL_SEC", "PUBLISHER_W_SCROLL_STEP_SEC", "PUBLISHER_W_SCROLL_UP_COUNT",
    "MAX_RETRIES_PER_ROW", "SAVE_EVERY_PENDING", "DESKTOP_RESET_PAUSE",
    "STEP_PAUSE", "ICON_BEFORE_RENAME_WAIT", "POST_ENTER_WAIT", "ACCEPT_COOKIE_WAIT",
    "MAX_JOURNAL_FAILS_BASE", "JOURNAL_SUCCESS_THRESHOLD_FOR_BOOST",
    "JOURNAL_SUCCESS_BOOST_MULTIPLIER", "ANTI_IDLE_SECONDS", "ANTI_IDLE_PIXELS",
    "APPLY_HYPERLINKS_ON_FINAL_SAVE",
)


def configure(settings: dict):
    """Set paths and optional timing overrides before opening the desktop app."""
    global DEFAULT_EXCEL_PATH, APP_SETTINGS, CAL_FILE, ICON_DIR, DOWNLOAD_DIR, SAMPLE_URLS, SETTINGS
    SETTINGS = dict(settings)
    DEFAULT_EXCEL_PATH = str(settings["workbook"])
    APP_SETTINGS = str(settings["app_settings_file"])
    CAL_FILE = str(settings["calibration_file"])
    ICON_DIR = Path(settings["icon_dir"])
    DOWNLOAD_DIR = Path(settings["download_dir"])
    SAMPLE_URLS = dict(settings.get("sample_urls", {}))
    tuning = settings.get("tuning", {})
    for key, value in tuning.items():
        if key not in _TUNING_KEYS:
            raise ValueError(f"Unknown SI literature retrieval setting: {key}")
        globals()[key] = value


def warn_missing_templates():
    """Report known absent captures without changing the image matching sequence."""
    if icon_path(ICON_DIR, "publisher_W_SI_1") is None:
        log("Missing template publisher_W_SI_1: capture the profile W anchor locally before using that flow.")
    if icon_path(ICON_DIR, "publisher_S_SI_Accept2") is None:
        log("Optional template publisher_S_SI_Accept2 is absent; this cookie-button check will be skipped.")


def launch(settings: dict):
    """Open the desktop application with a local working copy of the inventory."""
    global abort_now, save_requested
    configure(settings)
    _load_gui_dependencies()
    workbook = prepare_local_inventory(settings)
    warn_missing_templates()
    abort_now = False
    save_requested = False
    root = tk.Tk()
    app = App(root, workbook_path=workbook)
    try:
        root.mainloop()
    finally:
        abort_now = True
        save_requested = True
        app.stop_anti_idle()
        app.hotkey_listener.stop()
    return app


def main(argv=None):
    """Validate an inventory without a display, or launch desktop literature retrieval."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/literature_retrieval.json", help="Literature retrieval configuration JSON")
    parser.add_argument("--workbook", help="Override the configured input CSV or Excel workbook")
    parser.add_argument("--validate", action="store_true", help="Inspect the inventory and icon templates without opening the GUI")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config, mode="si")
        if args.workbook:
            settings["workbook"] = Path(args.workbook).expanduser().resolve()
        if args.validate:
            report = audit_inventory(settings["workbook"], mode="si", icon_dir=settings["icon_dir"])
            print(json.dumps(display_paths(report), indent=2, default=str))
            return 0
        launch(settings)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        parser.exit(1, f"SI literature retrieval: {display_paths(str(error))}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
