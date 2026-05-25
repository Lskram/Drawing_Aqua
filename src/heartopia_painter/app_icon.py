from __future__ import annotations

from pathlib import Path

from PySide6 import QtGui


def app_icon_path() -> Path | None:
    path = Path(__file__).resolve().parent / "resources" / "app_icon.ico"
    return path if path.exists() else None


def load_app_icon() -> QtGui.QIcon:
    path = app_icon_path()
    if path is None:
        return QtGui.QIcon()
    return QtGui.QIcon(str(path))
