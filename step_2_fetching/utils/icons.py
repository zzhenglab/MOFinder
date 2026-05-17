"""
On-screen icon matching shared by Step 2.1 / 2.2.

Both pipelines drive the browser by locating publisher-specific PNG/JPG
templates on the screen (the "icon" folder next to the Excel file) and
clicking their centers. These helpers wrap PyAutoGUI's image search so the
flow code can read top-to-bottom.

Two access patterns:
  - Step 2.1: a numbered sequence ``<PUBLISHER>_1, <PUBLISHER>_2, ...``
              fetched by ``list_icon_sequence``.
  - Step 2.2: named icons (``WILEY_SI_1``, ``WILEY_SI_3a`` ...) fetched
              one at a time by ``icon_path`` / ``wait_for_image`` /
              ``click_icon``.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

import pyautogui

try:
    import cv2  # noqa: F401
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False


# Image file extensions we recognize for templates.
ICON_EXTS = (".png", ".jpg", ".jpeg", ".bmp")


# ===========================================================================
# Step 2.1 access pattern: a numbered sequence per publisher
# ===========================================================================
def list_icon_sequence(publisher: str, icon_dir: Optional[Path], log=print) -> List[Path]:
    """
    Return the ordered list of icon files for ``publisher``.

    Looks for files named ``<publisher>_<N>.<ext>`` (case-insensitive) where
    ``N`` is a positive integer. Returns them sorted by ``N``.
    """
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


# ===========================================================================
# Step 2.2 access pattern: lookup by exact icon stem
# ===========================================================================
def icon_path(icon_dir: Path, name: str) -> Optional[Path]:
    """Return the icon file ``<icon_dir>/<name>.<ext>`` if it exists, else None."""
    for ext in ICON_EXTS:
        p = icon_dir / f"{name}{ext}"
        if p.exists():
            return p
    return None


# ===========================================================================
# Screen search primitives
# ===========================================================================
def locate_center_on_screen(image_path: Path, confidence: float, log=print) -> Optional[Tuple[int, int]]:
    """
    PyAutoGUI's ``locateCenterOnScreen`` with an optional confidence threshold.

    Returns ``(x, y)`` or ``None``. The confidence kwarg only works if
    OpenCV is installed (``HAS_CV2`` flag at module level).
    """
    try:
        box = (
            pyautogui.locateCenterOnScreen(str(image_path), confidence=confidence)
            if HAS_CV2
            else pyautogui.locateCenterOnScreen(str(image_path))
        )
        return (int(box.x), int(box.y)) if box else None
    except Exception as e:
        log("locate err", image_path, e)
        return None


def wait_for_image(
    icon_dir: Path,
    name: str,
    timeout: float,
    confidence: float = 0.87,
    tick: float = 0.6,
    abort_flag=lambda: False,
) -> Optional[Tuple[int, int]]:
    """
    Repeatedly search for icon ``name`` on the screen for up to ``timeout`` s.

    Returns the icon center as ``(x, y)`` or ``None`` if the timeout
    elapses without a hit. Raises ``SystemExit("Aborted")`` if
    ``abort_flag`` becomes true.
    """
    img = icon_path(icon_dir, name)
    if not img:
        return None
    t0 = time.time()
    while time.time() - t0 < timeout:
        if abort_flag():
            raise SystemExit("Aborted")
        pos = locate_center_on_screen(img, confidence)
        if pos:
            return pos
        time.sleep(tick)
    return None


def click_icon(
    icon_dir: Path,
    name: str,
    timeout: float,
    post_wait: float = 0.0,
    confidence: float = 0.87,
    tick: float = 0.6,
    abort_flag=lambda: False,
) -> bool:
    """Find icon ``name``, click its center, optionally pause ``post_wait`` s."""
    pos = wait_for_image(icon_dir, name, timeout, confidence=confidence, tick=tick, abort_flag=abort_flag)
    if not pos:
        return False
    pyautogui.moveTo(pos[0], pos[1], duration=0.20)
    time.sleep(0.05)
    pyautogui.click()
    if post_wait > 0:
        time.sleep(post_wait)
    return True
