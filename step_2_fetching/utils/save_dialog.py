"""
Save-As dialog helpers shared by Step 2.1 / 2.2.

After each row's flow clicks the publisher's download link, Chrome opens
its native Save As dialog. These helpers:

  - wait for the saved file to appear on disk (``fresh_file_ready``,
    ``fresh_file_ready_any``);
  - drive the Save dialog's filename text box to a target path via a
    calibrated click + Ctrl+A + Delete + paste + Enter sequence
    (``rename_in_save_dialog``).

Two file-detection variants because the two pipelines differ:
  - Step 2.1 saves a single fixed-extension file (always ``.pdf``).
  - Step 2.2 saves the publisher's chosen SI extension (``.pdf``,
    ``.docx``, ``.zip``, ...), so detection scans a candidate-extension
    list.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Tuple

import pyautogui
import pyperclip

from .chrome import IS_MAC


# File extensions a publisher's SI download might land on (Step 2.2).
CANDIDATE_SI_EXTS = [
    ".pdf", ".docx", ".doc", ".zip", ".xlsx", ".xls",
    ".pptx", ".ppt", ".csv", ".txt", ".rar", ".gz", ".7z",
]


# ===========================================================================
# Disk polling — has the file finished writing?
# ===========================================================================
def fresh_file_ready(path: Path, timeout: float = 90.0, abort_flag=lambda: False) -> bool:
    """
    Wait for ``path`` to exist + be non-empty + have no temp sibling.

    Used by Step 2.1 where the saved filename is fully known up front.
    Polls every 200 ms. Returns False on timeout. Raises
    ``SystemExit("Aborted")`` if ``abort_flag`` becomes true.
    """
    tmp_exts = [".crdownload", ".part", ".tmp"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        if abort_flag():
            raise SystemExit("Aborted")
        if (
            path.exists()
            and path.stat().st_size > 0
            and not any(Path(str(path) + e).exists() for e in tmp_exts)
        ):
            return True
        time.sleep(0.2)
    return False


def fresh_file_ready_any(
    target_base_path: Path,
    timeout: float = 90.0,
    abort_flag=lambda: False,
) -> Optional[Path]:
    """
    Wait for ``<target_base_path>`` OR ``<target_base_path><ext>`` (where ext
    is one of ``CANDIDATE_SI_EXTS``) to land on disk.

    Used by Step 2.2 because the SI file's extension depends on the
    publisher. Returns the actual ``Path`` that appeared, or ``None``.
    """
    tmp_exts = [".crdownload", ".part", ".tmp"]
    folder = target_base_path.parent
    stem = target_base_path.name
    t0 = time.time()
    while time.time() - t0 < timeout:
        if abort_flag():
            raise SystemExit("Aborted")
        p0 = folder / stem
        if p0.exists() and p0.stat().st_size > 0 and not any(Path(str(p0) + e).exists() for e in tmp_exts):
            return p0
        for ext in CANDIDATE_SI_EXTS:
            p = folder / (stem + ext)
            if p.exists() and p.stat().st_size > 0 and not any(Path(str(p) + e).exists() for e in tmp_exts):
                return p
        time.sleep(0.25)
    return None


# ===========================================================================
# Drive the Save dialog's filename text box
# ===========================================================================
def rename_in_save_dialog(
    target_base_path: Path,
    coords_save_xy: Tuple[int, int],
    *,
    before_rename_wait: float = 2.0,
    step_pause: float = 0.35,
    post_enter_wait: float = 0.7,
    abort_flag=lambda: False,
) -> Optional[Path]:
    """
    Type ``target_base_path`` into the Save dialog's filename box, hit Enter,
    and wait for the file to materialize.

    ``coords_save_xy`` is the screen coordinate of the filename text box,
    captured during calibration (F8/F9). Returns the saved file's actual
    ``Path`` (extension may not match ``target_base_path``'s) or ``None``
    on timeout.
    """
    sx, sy = coords_save_xy
    time.sleep(before_rename_wait)

    pyautogui.moveTo(int(sx), int(sy), duration=0.2)
    time.sleep(0.05)
    pyautogui.click()
    time.sleep(step_pause)

    pyautogui.hotkey("command" if IS_MAC else "ctrl", "a")
    time.sleep(step_pause)
    pyautogui.press("delete")
    time.sleep(step_pause)

    pyperclip.copy(str(target_base_path))
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v")
    time.sleep(step_pause)
    pyautogui.press("enter")
    time.sleep(post_enter_wait)
    pyautogui.press("enter")
    time.sleep(0.3)

    # Dismiss any lingering modal by clicking screen center.
    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2)

    return fresh_file_ready_any(target_base_path, timeout=90, abort_flag=abort_flag)
