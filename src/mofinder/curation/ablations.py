"""Compatibility entry point; preparation now lives in mofinder.datasets.ablations."""

from mofinder.datasets import ablations as _implementation

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]


def __getattr__(name):
    return getattr(_implementation, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    _implementation.main()
