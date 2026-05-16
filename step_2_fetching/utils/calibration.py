"""
JSON-backed calibration store shared by Step 2.1 / 2.2.

Each Step keeps a small JSON file next to itself recording:
  - the Save-As dialog's "File name" text-box screen coordinates
    (``GLOBAL_SAVE.save_xy``); and
  - Step 2.1 only: per-publisher fallback click coordinates, recorded
    action sequences, and ICON-mode toggles.

This module is just thin load / save / F8-F9 capture helpers — it doesn't
know about specific keys; callers reach into the returned dict directly.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

import pyautogui
from pynput import keyboard as pynput_keyboard


def load_calibration(
    cal_file: str,
    defaults: Optional[Dict] = None,
) -> dict:
    """
    Load ``cal_file`` (creating it from ``defaults`` if absent or unreadable).

    Missing top-level keys from ``defaults`` are filled in and the file
    is rewritten — so first-run users get a fully-populated template.
    """
    data: dict = {}
    if os.path.exists(cal_file):
        try:
            with open(cal_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    if defaults:
        changed = False
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
                changed = True
            elif isinstance(val, dict) and isinstance(data[key], dict):
                for sub_k, sub_v in val.items():
                    if sub_k not in data[key]:
                        data[key][sub_k] = sub_v
                        changed = True
        if changed:
            save_calibration(cal_file, data)
    elif not os.path.exists(cal_file):
        save_calibration(cal_file, data)

    return data


def save_calibration(cal_file: str, data: dict) -> None:
    """Write ``data`` to ``cal_file`` as pretty-printed JSON. Errors swallowed."""
    try:
        with open(cal_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def capture_f8_f9_points(
    pump_ui: Callable[[], None] = lambda: None,
    on_each: Callable[[int], None] = lambda _n: None,
) -> List[Tuple[int, int]]:
    """
    Capture screen positions with F8 (add point) and F9 (finish).

    Returns the list of ``(x, y)`` tuples captured before F9. Calls
    ``pump_ui()`` while waiting (the Tk apps pass ``root.update``) and
    ``on_each(n)`` after each F8 so callers can update a counter label.
    """
    points: List[Tuple[int, int]] = []
    done_flag = {"done": False}

    def on_press(key):
        try:
            if key == pynput_keyboard.Key.f8:
                p = pyautogui.position()
                points.append((p.x, p.y))
                on_each(len(points))
            elif key == pynput_keyboard.Key.f9:
                done_flag["done"] = True
                return False
        except Exception:
            return False

    listener = pynput_keyboard.Listener(on_press=on_press)
    listener.start()
    while listener.is_alive():
        if done_flag["done"]:
            break
        pump_ui()
        time.sleep(0.05)
    return points
