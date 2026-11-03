"""Compatibility imports for mofinder.datasets.ablation_analysis."""

from mofinder.datasets import ablation_analysis as _implementation

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]


def __getattr__(name):
    return getattr(_implementation, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_implementation)))
