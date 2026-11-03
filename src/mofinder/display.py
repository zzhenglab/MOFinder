"""Short project paths for console and notebook output, never for file access."""

from functools import lru_cache
from pathlib import Path, PurePath, PureWindowsPath
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def _project_prefix(project_root):
    """Match native, forward-slash and escaped versions of a project path."""
    windows = PureWindowsPath(project_root).is_absolute()
    root = PureWindowsPath(project_root) if windows else Path(project_root)
    parts = re.split(r"[/\\]+", str(root).rstrip("/\\"))
    prefix = r"[/\\]+".join(re.escape(part) for part in parts)
    # Keep similarly named sibling directories and unrelated text intact.
    pattern = re.compile(
        r"(?<![\w./\\~-])" + prefix + r"(?=$|[/\\\s'\"<>,;:)\]}])",
        re.IGNORECASE if windows else 0,
    )
    return pattern, root.name


def display_path(path, *, project_root=None):
    """Display a project path from its folder name, e.g. MOFinder/Demo/outputs.

    Relative paths and paths outside the project are left as supplied. The
    function also accepts messages containing a project path. It does not
    resolve, modify or access the path.
    """
    pattern, name = _project_prefix(str(PROJECT_ROOT if project_root is None else project_root))
    return pattern.sub(lambda match: name, str(path))


def display_paths(value, *, project_root=None):
    """Copy a nested report with short paths for printing or notebook display.

    Keep the original report for subsequent processing and saved manifests.
    """
    if isinstance(value, (str, PurePath)):
        return display_path(value, project_root=project_root)
    if isinstance(value, dict):
        return {
            display_paths(key, project_root=project_root): display_paths(item, project_root=project_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [display_paths(item, project_root=project_root) for item in value]
    if isinstance(value, tuple):
        return tuple(display_paths(item, project_root=project_root) for item in value)
    return value
