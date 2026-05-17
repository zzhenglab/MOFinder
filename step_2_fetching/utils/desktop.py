"""
Desktop / keyboard / mouse helpers shared by Step 2.1 / 2.2.

Used between rows to put the system back to a known state, and during a
flow to scroll a page or move the cursor out of the way of an icon match.
"""
from __future__ import annotations

import time

import pyautogui

from .chrome import IS_WIN


# Default pause used by reset_to_desktop between sub-actions.
DESKTOP_RESET_PAUSE = 0.5


def reset_to_desktop(include_enter: bool = True, pause: float = DESKTOP_RESET_PAUSE) -> None:
    """
    Windows only: Win+D shows desktop, optional Enter, click screen center.

    Used between rows to clear any modal dialog and re-anchor the cursor.
    On macOS / Linux this is a no-op — the per-publisher flows there are
    written to not need it.
    """
    if not IS_WIN:
        return
    pyautogui.hotkey("winleft", "d")
    time.sleep(pause)
    if include_enter:
        pyautogui.press("enter")
        time.sleep(pause)
    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2)
    time.sleep(pause)


def safe_reset_to_desktop(include_enter: bool = True, log=print) -> None:
    """Call ``reset_to_desktop`` and swallow any exception with a log line."""
    try:
        reset_to_desktop(include_enter)
    except Exception as e:
        log("safe_reset_to_desktop error:", e)


def move_cursor_top_center(margin_y: int = 8) -> None:
    """Park the cursor at the top-center of the screen so it doesn't occlude icons."""
    w, _h = pyautogui.size()
    pyautogui.moveTo(w // 2, max(1, margin_y), duration=0.2)


def fast_scroll_down(seconds: float, step_sec: float = 0.03, abort_flag=lambda: False) -> None:
    """
    Hammer Page Down for ``seconds`` to fast-scroll to the bottom of a page.

    ``step_sec`` is the delay between key presses. ``abort_flag`` is
    polled so the user can interrupt mid-scroll.
    """
    t_end = time.time() + seconds
    while time.time() < t_end:
        if abort_flag():
            raise SystemExit("Aborted")
        pyautogui.press("pagedown")
        time.sleep(step_sec)


def press_down_n(n: int, interval: float = 0.03) -> None:
    """Press the Down arrow ``n`` times."""
    for _ in range(n):
        pyautogui.press("down")
        time.sleep(interval)


def press_up_n(n: int, interval: float = 0.03) -> None:
    """Press the Up arrow ``n`` times."""
    for _ in range(n):
        pyautogui.press("up")
        time.sleep(interval)
