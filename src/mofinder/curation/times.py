"""Convert reported reaction-time ranges and qualitative durations to hours."""
from __future__ import annotations

import math
import re


TIME_PARSER_VERSION = "duration-phrases-v1"
_NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)"
_UNIT = r"(?:hours?|hrs?|h|days?|d|weeks?|wks?|wk|months?|mos?|mo)"
_RANGE = re.compile(
    rf"(?<![\w.])(?P<lower>{_NUMBER})\s*(?:(?P<lower_unit>{_UNIT})\s*)?"
    rf"(?:[-\u2013\u2014]|\bto\b)\s*(?P<upper>{_NUMBER})\s*"
    rf"(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)
_UPPER_LIMIT = re.compile(
    rf"\bto\s+(?P<upper>{_NUMBER})\s*(?P<unit>{_UNIT})\b", re.IGNORECASE
)
_SEVERAL = re.compile(r"\b(?:several|serval)\s+(days?|weeks?|months?)\b", re.IGNORECASE)


def _unit_hours(unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("h"):
        return 1.0
    if unit.startswith("d"):
        return 24.0
    if unit.startswith("w"):
        return 168.0
    return 720.0  # Numeric month durations use 30 days per month.


def parse_time_hours(text) -> float | None:
    """Interpret supported ranges and qualitative phrases; leave other text unresolved."""
    if text is None:
        return None
    text = str(text).strip()
    match = _RANGE.search(text)
    if match:
        lower = float(match["lower"]) * _unit_hours(match["lower_unit"] or match["unit"])
        upper = float(match["upper"]) * _unit_hours(match["unit"])
        return max(lower, upper)
    match = _UPPER_LIMIT.search(text)
    if match:
        return float(match["upper"]) * _unit_hours(match["unit"])
    if re.search(r"\bovernight\b", text, re.IGNORECASE):
        return 12.0
    match = _SEVERAL.search(text)
    if match:
        return {"day": 144.0, "week": 432.0, "month": 2160.0}[match[1].lower().rstrip("s")]
    if re.search(r"\bimmediate\w*\b", text, re.IGNORECASE) and not re.search(r"\d", text):
        return 0.1
    return None


def normalize_time_hours(value, text):
    """Preserve numeric hours; resolve missing or textual values from duration phrases."""
    try:
        if math.isfinite(float(value)):
            return value
    except (TypeError, ValueError):
        pass
    for candidate in (value, text):
        parsed = parse_time_hours(candidate)
        if parsed is not None:
            return format(parsed, ".15g")
    return value
