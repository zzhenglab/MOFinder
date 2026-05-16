"""
Chrome browser control shared by Step 2.1 / 2.2.

These functions open URLs in a fresh incognito Chrome window, force it
fullscreen so the on-screen icon templates match, paste a link into the
address bar, and close all Chrome processes between rows.

Platform notes
    - Windows: full-screen via Win+Up then F11; close via ``taskkill``.
    - macOS:   full-screen via Cmd+Ctrl+F;     close via osascript + pkill.
    - Linux:   full-screen via F11;            close via pkill.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import webbrowser
from typing import List, Optional

import pyautogui
import pyperclip


IS_MAC   = sys.platform == "darwin"
IS_WIN   = sys.platform.startswith("win")
IS_LINUX = not IS_MAC and not IS_WIN


# Chrome flags used for every download window: incognito (fresh session),
# no first-run dialog, no crash bubble, start fullscreen so icon matches.
CHROME_FLAGS = [
    "--disable-session-crashed-bubble",
    "--no-first-run",
    "--incognito",
    "--start-maximized",
    "--start-fullscreen",
]


def _chrome_candidates() -> List[str]:
    """Return likely Chrome executable paths for the current OS."""
    if IS_WIN:
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    if IS_MAC:
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    names = ["google-chrome", "chrome", "chromium-browser", "chromium"]
    return [shutil.which(n) for n in names if shutil.which(n)]


def _force_fullscreen() -> None:
    """Send the platform's fullscreen hotkey. Best-effort, errors swallowed."""
    try:
        if IS_MAC:
            pyautogui.hotkey("command", "ctrl", "f")
        elif IS_WIN:
            pyautogui.hotkey("winleft", "up")
            time.sleep(0.2)
            pyautogui.press("f11")
        else:
            pyautogui.press("f11")
    except Exception:
        pass


def open_in_chrome(
    url: str,
    new_window: bool = False,
    browser_open_wait: float = 2.0,
    log=print,
) -> None:
    """
    Launch Chrome at ``url`` and force the window fullscreen.

    Falls back to ``webbrowser.open_new_tab`` if no Chrome binary is found.
    ``browser_open_wait`` is the pause (seconds) before sending the
    fullscreen hotkey, so the window has time to materialize.
    """
    args_flags = list(CHROME_FLAGS)
    if new_window:
        args_flags.append("--new-window")

    for exe in _chrome_candidates():
        if not exe:
            continue
        try:
            log("Launching Chrome:", exe, "flags:", " ".join(args_flags), "url:", url)
            subprocess.Popen([exe, *args_flags, url])
            time.sleep(browser_open_wait)
            _force_fullscreen()
            return
        except Exception as e:
            log("Chrome launch failed with", exe, e)
            continue

    # No Chrome binary worked — fall back to the OS default browser.
    try:
        log("webbrowser fallback:", url)
        br = webbrowser.get("chrome")
        (br.open_new if new_window else br.open)(url)
    except Exception:
        log("open_new_tab fallback:", url)
        webbrowser.open_new_tab(url)

    time.sleep(browser_open_wait)
    _force_fullscreen()


def hotkey_address_bar() -> None:
    """Focus the Chrome address bar (Ctrl+L / Cmd+L)."""
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "l")


def hotkey_save() -> None:
    """Trigger the browser's Save dialog (Ctrl+S / Cmd+S)."""
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "s")


def go_to_address_bar_and_open(
    link: str,
    wait_after_nav: float = 4.0,
    abort_flag=lambda: False,
    log=print,
) -> None:
    """
    Focus the address bar, paste ``link``, press Enter, wait for the page.

    ``abort_flag`` is called periodically; raise ``SystemExit("Aborted")``
    via the caller's exception mechanism if it returns True.
    """
    if abort_flag():
        raise SystemExit("Aborted")
    log("Navigating:", link)
    hotkey_address_bar()
    time.sleep(0.2)
    pyperclip.copy(link)
    pyautogui.hotkey("command" if IS_MAC else "ctrl", "v")
    time.sleep(0.1)
    pyautogui.press("enter")
    # Sleep in small chunks so abort_flag can interrupt early.
    t_end = time.time() + wait_after_nav
    while time.time() < t_end:
        if abort_flag():
            raise SystemExit("Aborted")
        time.sleep(0.1)
    log("Navigation done")


def close_all_chrome(log=print) -> None:
    """Forcibly kill all Chrome processes for this OS, then pause briefly."""
    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/IM", "chrome.exe", "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif IS_MAC:
            subprocess.run(
                ["osascript", "-e", 'tell application "Google Chrome" to quit'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.6)
            subprocess.run(
                ["pkill", "-x", "Google Chrome"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            for cmd in (
                ["pkill", "-x", "google-chrome"],
                ["pkill", "-x", "chrome"],
                ["pkill", "chrome"],
            ):
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
    except Exception as e:
        log("close_all_chrome error:", e)
    time.sleep(1.2)


def ensure_chrome_closed(retries: int = 2, log=print) -> None:
    """Call ``close_all_chrome`` ``retries`` times in case a tab is stubborn."""
    for _ in range(retries):
        close_all_chrome(log=log)
        time.sleep(0.2)
