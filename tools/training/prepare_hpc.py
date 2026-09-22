#!/usr/bin/env python3
"""Command-line entry point for HPC input preparation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mofinder.training.prepare import main

if __name__ == "__main__":
    main()
