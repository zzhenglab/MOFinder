"""Launch the literature retrieval tool from a source checkout."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mofinder.literature_retrieval.si import main


if __name__ == "__main__":
    args = sys.argv[1:]
    if not any(arg == "--config" or arg.startswith("--config=") for arg in args):
        args = ["--config", str(ROOT / "configs/literature_retrieval.json"), *args]
    raise SystemExit(main(args))
