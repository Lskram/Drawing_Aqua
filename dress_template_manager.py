import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


try:
    from heartopia_painter.dress_template_manager import run
except ModuleNotFoundError as e:
    missing = getattr(e, "name", None)
    if missing in {"PySide6", "pillow", "PIL"} or (
        isinstance(missing, str) and missing.startswith("PySide6")
    ):
        sys.stderr.write(
            "Missing Python dependencies.\n\n"
            "Run with the project venv:\n"
            "  .\\.venv\\Scripts\\python.exe dress_template_manager.py\n"
        )
        raise SystemExit(1)
    raise


if __name__ == "__main__":
    run()
