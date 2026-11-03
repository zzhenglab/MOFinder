"""Allocate numbered output directories without replacing earlier runs."""

from pathlib import Path
import re


def create_run_directory(parent, *, prefix="run"):
    """Create the next ``run_001`` directory, retrying concurrent allocations.

    Numbering continues after the largest existing number; gaps and historical
    timestamp-named runs remain untouched. Creating the directory reserves the
    number atomically, including when several processes start together.
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"{re.escape(prefix)}_([0-9]+)")
    numbers = [int(match.group(1)) for entry in parent.iterdir()
               if (match := pattern.fullmatch(entry.name))]
    number = max(numbers, default=0) + 1
    while True:
        destination = parent / f"{prefix}_{number:03d}"
        try:
            destination.mkdir()
        except FileExistsError:
            number += 1
        else:
            return destination
