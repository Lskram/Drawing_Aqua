from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PIL import Image

from .artpia_templates import (
    find_artpia_part_template,
    save_artpia_mask_file,
    save_artpia_template_files,
)
from .app_icon import load_app_icon
from .screen import get_screen_pixel_rgb
from .config import AppConfig, ClothingPartSpec, MainColor, ShadeButton, default_config_path, load_config, save_config
from .game_draw_data import (
    GAME_DRAW_PARTS_BY_PRESET,
    GAME_DRAW_PRESET_NAMES,
    game_draw_part_names,
    game_draw_part_size,
    is_game_draw_preset,
)
from .image_processing import ImagePrepOptions, PixelGrid, load_and_resize_to_grid
from .overlay import Marker, MarkersOverlay, PointResult, PointSelectOverlay, RectResult, RectSelectOverlay, StatusOverlay
from .paint import PainterOptions, erase_canvas, open_shades_panel_for_main, paint_grid, select_shade_for_painting


ONE_TO_ONE_PRESET_NAME = "1:1"
SIXTEEN_NINE_PRESET_NAME = "16:9"
NINE_SIXTEEN_PRESET_NAME = "9:16"
FOUR_THREE_PRESET_NAME = "4:3"
THREE_FOUR_PRESET_NAME = "3:4"
TSHIRT_PRESET_NAME = "T-Shirt"
TANK_TOP_PRESET_NAME = "Tank Top"
DRESS_PRESET_NAME = "Dress"
CUSTOM_CLOTHING_PRESET_NAME = "Custom Clothing"
ASPECT_PRESET_NAMES = {
    ONE_TO_ONE_PRESET_NAME,
    SIXTEEN_NINE_PRESET_NAME,
    NINE_SIXTEEN_PRESET_NAME,
    FOUR_THREE_PRESET_NAME,
    THREE_FOUR_PRESET_NAME,
}

ONE_TO_ONE_PRECISIONS: dict[str, Tuple[int, int]] = {
    "Small": (30, 30),
    "Medium": (50, 50),
    "Big": (100, 100),
    "Super Large": (150, 150),
}

SIXTEEN_NINE_PRECISIONS: dict[str, Tuple[int, int]] = {
    "Small": (30, 18),
    "Medium": (50, 28),
    "Big": (100, 56),
    "Super Large": (150, 84),
}

NINE_SIXTEEN_PRECISIONS: dict[str, Tuple[int, int]] = {
    "Small": (18, 30),
    "Medium": (28, 50),
    "Big": (56, 100),
    "Super Large": (84, 150),
}

FOUR_THREE_PRECISIONS: dict[str, Tuple[int, int]] = {
    "Small": (30, 24),
    "Medium": (50, 38),
    "Big": (100, 76),
    "Super Large": (150, 114),
}

THREE_FOUR_PRECISIONS: dict[str, Tuple[int, int]] = {
    "Small": (24, 30),
    "Medium": (38, 50),
    "Big": (76, 100),
    "Super Large": (114, 150),
}

TSHIRT_PARTS: dict[str, Tuple[int, int]] = GAME_DRAW_PARTS_BY_PRESET.get(TSHIRT_PRESET_NAME, {
    "Front": (64, 80),
    "Back": (64, 80),
    "Left Sleeve": (64, 48),
    "Right Sleeve": (64, 48),
})

TANK_TOP_PARTS: dict[str, Tuple[int, int]] = GAME_DRAW_PARTS_BY_PRESET.get(TANK_TOP_PRESET_NAME, {
    "Front": (64, 64),
    "Back": (64, 64),
})

DRESS_PARTS: dict[str, Tuple[int, int]] = GAME_DRAW_PARTS_BY_PRESET.get(DRESS_PRESET_NAME, {
    "Front": (102, 154),
    "Back": (76, 154),
    "Innerwear": (168, 102),
})

DRESS_MAPPINGS: dict[str, Tuple[Tuple[float, float, float, float], str]] = {
    part: ((0.0, 0.0, 1.0, 1.0), "none")
    for part in DRESS_PARTS
}

LEGACY_GAME_DRAW_PART_ALIASES: dict[str, dict[str, str]] = {
    DRESS_PRESET_NAME: {
        "Front Part": "Front",
        "Back Part": "Back",
        "Full Body": "Front",
    }
}


def _first_key(data: dict[str, Tuple[int, int]], fallback: str) -> str:
    return next(iter(data), fallback)


def default_game_draw_part(preset: str) -> str:
    parts = GAME_DRAW_PARTS_BY_PRESET.get(preset, {})
    return _first_key(parts, "Part 1")


def canonical_game_draw_part(preset: str, part: Optional[str]) -> str:
    parts = GAME_DRAW_PARTS_BY_PRESET.get(preset, {})
    fallback = default_game_draw_part(preset)
    name = str(part or "").strip()
    name = LEGACY_GAME_DRAW_PART_ALIASES.get(preset, {}).get(name, name)
    return name if name in parts else fallback


def selection_key(preset: str, variant: Optional[str]) -> str:
    if preset in ASPECT_PRESET_NAMES:
        precision = variant or "Small"
        return f"{preset}::{precision}"
    if is_game_draw_preset(preset):
        return f"{preset}::{canonical_game_draw_part(preset, variant)}"
    if preset == CUSTOM_CLOTHING_PRESET_NAME:
        return f"{preset}::{variant or 'Part 1'}"
    return preset


@dataclass
class LoadedImage:
    path: str
    grid: PixelGrid


@dataclass
class ClickCaptureResult:
    pos: Tuple[int, int]
    rgb: Tuple[int, int, int]


class WorkerSignals(QtCore.QObject):
    progress = QtCore.Signal(int, int)
    status = QtCore.Signal(str)
    verify_cell = QtCore.Signal(int, int)
    bucket_base = QtCore.Signal(str, int, int, int, int, int, int, int)
    finished = QtCore.Signal()
    error = QtCore.Signal(str)
    paused = QtCore.Signal(str)
    stopped = QtCore.Signal(str)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heartopia Image Painter")
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.statusBar().showMessage("Ready")

        self._config_path = default_config_path()
        self._cfg = load_config(self._config_path)
        self._migrate_selection_state_keys()

        self._loaded: Optional[LoadedImage] = None
        self._canvas_rect: Optional[Tuple[int, int, int, int]] = None

        self._overlay: Optional[RectSelectOverlay] = None

        self._markers_overlay: Optional[MarkersOverlay] = None

        self._status_overlay: Optional[StatusOverlay] = None
        self._game_window_rect: Optional[Tuple[int, int, int, int]] = None
        self._target_hwnd: Optional[int] = None
        self._target_window_title: str = ""

        self._esc_listener = None
        self._hidden_for_automation = False

        self._stop_flag = False
        self._stop_reason: Optional[str] = None  # "pause" | "stop" | None
        # Paint session state (used for pause/resume)
        self._paint_total: int = 0
        self._paint_done: set[tuple[int, int]] = set()
        self._paint_paused: bool = False
        self._paint_session_sig: Optional[tuple] = None
        self._paint_base_bucket_key: Optional[tuple[tuple[int, int], tuple[int, int]]] = None
        self._paint_base_bucket_rgb: Optional[tuple[int, int, int]] = None

        self._build_ui()
        self._apply_persisted_state()
        self._refresh_config_view()

    def _migrate_selection_state_keys(self) -> None:
        changed = False
        for preset, aliases in LEGACY_GAME_DRAW_PART_ALIASES.items():
            for old_part, new_part in aliases.items():
                old_key = f"{preset}::{old_part}"
                new_key = selection_key(preset, new_part)
                if old_key in self._cfg.last_canvas_rect_by_key and new_key not in self._cfg.last_canvas_rect_by_key:
                    self._cfg.last_canvas_rect_by_key[new_key] = self._cfg.last_canvas_rect_by_key[old_key]
                    changed = True
                if old_key in self._cfg.last_image_path_by_key and new_key not in self._cfg.last_image_path_by_key:
                    self._cfg.last_image_path_by_key[new_key] = self._cfg.last_image_path_by_key[old_key]
                    changed = True
                if self._cfg.game_draw_part_by_preset.get(preset) == old_part:
                    self._cfg.game_draw_part_by_preset[preset] = canonical_game_draw_part(preset, old_part)
                    changed = True
        if changed:
            self._save_cfg()

    def _ensure_status_overlay(self) -> StatusOverlay:
        if self._status_overlay is None:
            self._status_overlay = StatusOverlay(title="Heartopia Painter")
        return self._status_overlay

    def _capture_foreground_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        # Best-effort on Windows; used to anchor the in-game overlays.
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            return None

    def _window_rect(self, hwnd: Optional[int]) -> Optional[Tuple[int, int, int, int]]:
        if os.name != "nt" or not hwnd:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            if not user32.IsWindow(int(hwnd)):
                return None
            rect = wintypes.RECT()
            if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
                return None
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            return None

    def _window_title(self, hwnd: Optional[int]) -> str:
        if os.name != "nt" or not hwnd:
            return ""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            length = int(user32.GetWindowTextLengthW(int(hwnd)))
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(int(hwnd), buf, length + 1)
            return str(buf.value)
        except Exception:
            return ""

    def _window_class(self, hwnd: Optional[int]) -> str:
        if os.name != "nt" or not hwnd:
            return ""
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(int(hwnd), buf, len(buf))
            return str(buf.value)
        except Exception:
            return ""

    def _is_shell_window(self, hwnd: Optional[int]) -> bool:
        cls = self._window_class(self._root_window(hwnd))
        return cls in {"Progman", "WorkerW", "Shell_TrayWnd"}

    def _window_pid(self, hwnd: Optional[int]) -> Optional[int]:
        if os.name != "nt" or not hwnd:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            return int(pid.value)
        except Exception:
            return None

    def _root_window(self, hwnd: Optional[int]) -> Optional[int]:
        if os.name != "nt" or not hwnd:
            return hwnd
        try:
            import ctypes

            GA_ROOT = 2
            root = int(ctypes.windll.user32.GetAncestor(int(hwnd), GA_ROOT))
            return root or int(hwnd)
        except Exception:
            return hwnd

    def _is_own_window(self, hwnd: Optional[int]) -> bool:
        pid = self._window_pid(self._root_window(hwnd))
        return pid is not None and int(pid) == os.getpid()

    def _window_from_point(self, x: int, y: int) -> Optional[int]:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            pt = wintypes.POINT(int(x), int(y))
            hwnd = int(ctypes.windll.user32.WindowFromPoint(pt))
            return self._root_window(hwnd) if hwnd else None
        except Exception:
            return None

    def _find_target_window_at_point(self, x: int, y: int) -> Optional[int]:
        """Find the top visible non-app window under a native screen point."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            matches: list[int] = []

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def callback(hwnd, _lparam):
                hwnd = int(hwnd)
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                if self._is_own_window(hwnd):
                    return True
                if self._is_shell_window(hwnd):
                    return True
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width < 20 or height < 20:
                    return True
                if int(rect.left) <= int(x) < int(rect.right) and int(rect.top) <= int(y) < int(rect.bottom):
                    matches.append(hwnd)
                    return False
                return True

            user32.EnumWindows(EnumWindowsProc(callback), 0)
            if matches:
                return self._root_window(matches[0])

            hwnd = self._window_from_point(int(x), int(y))
            if hwnd and not self._is_own_window(hwnd) and not self._is_shell_window(hwnd):
                return hwnd
            return None
        except Exception:
            return None

    def _canvas_center_point(self) -> Optional[Tuple[int, int]]:
        if self._canvas_rect is None:
            return None
        x, y, w, h = self._canvas_rect
        return (int(x + w / 2), int(y + h / 2))

    def _remember_target_window_for_canvas(self) -> None:
        center = self._canvas_center_point()
        if center is None:
            self._target_hwnd = None
            self._target_window_title = ""
            return
        hwnd = self._find_target_window_at_point(center[0], center[1])
        self._target_hwnd = int(hwnd) if hwnd else None
        self._target_window_title = self._window_title(hwnd) if hwnd else ""
        if self._target_hwnd:
            title = self._target_window_title or f"HWND {self._target_hwnd}"
            self.statusBar().showMessage(f"Target window detected: {title}", 5000)

    def _focus_target_window(self) -> None:
        if os.name != "nt":
            return
        center = self._canvas_center_point()
        hwnd = self._target_hwnd
        if not hwnd or self._window_rect(hwnd) is None or self._is_own_window(hwnd):
            hwnd = self._find_target_window_at_point(center[0], center[1]) if center else None
            self._target_hwnd = int(hwnd) if hwnd else None
            self._target_window_title = self._window_title(hwnd) if hwnd else ""
        if not hwnd:
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            SW_RESTORE = 9
            user32.ShowWindow(int(hwnd), SW_RESTORE)
            user32.BringWindowToTop(int(hwnd))
            user32.SetForegroundWindow(int(hwnd))
        except Exception:
            pass

    def _prepare_automation_window(self) -> bool:
        """Hide app windows, focus target, and ensure clicks won't hit this app."""
        self._hide_status_overlay()
        self._hide_main_window_for_automation()
        self._focus_target_window()
        QtWidgets.QApplication.processEvents()
        time.sleep(0.25)

        center = self._canvas_center_point()
        if center is None:
            self._restore_main_window_after_automation()
            return False

        hwnd_at_center = self._window_from_point(center[0], center[1])
        if hwnd_at_center and self._is_own_window(hwnd_at_center):
            self._restore_main_window_after_automation()
            QtWidgets.QMessageBox.warning(
                self,
                "Canvas target blocked",
                "The selected canvas center is still on Heartopia Image Painter, so painting was stopped before clicking.\n\n"
                "Move the app window away from the game, select the in-game canvas area again, then press Paint now.",
            )
            return False

        target_hwnd = self._find_target_window_at_point(center[0], center[1])
        if not target_hwnd:
            self._restore_main_window_after_automation()
            QtWidgets.QMessageBox.warning(
                self,
                "Game target not found",
                "No valid game window was found under the selected canvas center.\n\n"
                "Put the game drawing canvas visible on screen, move this app away from it, select the canvas area again, then press Paint now.",
            )
            return False

        self._target_hwnd = int(target_hwnd)
        self._target_window_title = self._window_title(target_hwnd)
        return True

    def _hide_status_overlay(self) -> None:
        try:
            if self._status_overlay is not None:
                self._status_overlay.stop()
        except Exception:
            pass
        # Status overlay contains replica canvas + cursors; nothing else to stop.

    def _hide_main_window_for_automation(self) -> None:
        """Keep the app from sitting above the game while pyautogui clicks."""
        if self.isVisible():
            self._hidden_for_automation = True
            self.hide()
            QtWidgets.QApplication.processEvents()
            # Let Windows reveal/refocus the game under this window before the worker captures/clicks.
            time.sleep(0.35)

    def _restore_main_window_after_automation(self) -> None:
        if not self._hidden_for_automation:
            return
        self._hidden_for_automation = False
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_worker_status(self, msg: str) -> None:
        if not bool(getattr(self._cfg, "status_overlay_enabled", True)):
            return
        if self._hidden_for_automation:
            return
        ov = self._ensure_status_overlay()
        if self._game_window_rect is not None:
            ov.set_anchor_rect(self._game_window_rect)
        if not ov.isVisible():
            ov.start()
        ov.set_status(msg)

    def _on_worker_verify_cell(self, x: int, y: int) -> None:
        if not bool(getattr(self._cfg, "status_overlay_enabled", True)):
            return
        if self._hidden_for_automation:
            return
        ov = self._ensure_status_overlay()
        if self._game_window_rect is not None:
            ov.set_anchor_rect(self._game_window_rect)
        if not ov.isVisible():
            ov.start()
        ov.set_verify_cursor(int(x), int(y))

    def _on_worker_progress(self, x: int, y: int) -> None:
        # IMPORTANT: connect worker signals to QObject methods (not lambdas)
        # so Qt can safely queue delivery onto the UI thread.
        total = int(self._paint_total) if int(self._paint_total) > 0 else 1
        self._on_progress(int(x), int(y), total)

    def _on_worker_bucket_base(self, main_name: str, mx: int, my: int, sx: int, sy: int, r: int, g: int, b: int) -> None:
        # Remember the base bucket-fill shade so Resume can keep using region-fill.
        del main_name
        self._paint_base_bucket_key = ((int(mx), int(my)), (int(sx), int(sy)))
        self._paint_base_bucket_rgb = (int(r), int(g), int(b))

    def _start_esc_listener(self) -> None:
        # Global hotkey so it works even when the game window is focused.
        try:
            from pynput import keyboard  # type: ignore
        except Exception:
            self.statusBar().showMessage("ESC stop hotkey unavailable (pynput import failed)", 5000)
            return

        # Stop any previous listener.
        self._stop_esc_listener()

        def on_press(key):
            try:
                if key == keyboard.Key.esc:
                    # Pause painting immediately (worker thread checks should_stop).
                    self._stop_reason = "pause"
                    self._stop_flag = True

                    # Stop listening so we don't re-trigger.
                    try:
                        self._run_on_ui_thread(lambda: self.statusBar().showMessage("Pausing…", 1500))
                    except Exception:
                        pass
                    return False  # stop listener
            except Exception:
                return None
            return None

        # On some Windows setups, suppress=True can fail (or require elevated privileges).
        # Prefer suppression to avoid ESC closing dialogs, but fall back if needed.
        try:
            self._esc_listener = keyboard.Listener(on_press=on_press, suppress=True)
            self._esc_listener.daemon = True
            self._esc_listener.start()
            self.statusBar().showMessage("ESC hotkey armed (suppressed)", 2500)
        except Exception:
            try:
                self._esc_listener = keyboard.Listener(on_press=on_press, suppress=False)
                self._esc_listener.daemon = True
                self._esc_listener.start()
                self.statusBar().showMessage("ESC hotkey armed", 2500)
            except Exception:
                self._esc_listener = None
                self.statusBar().showMessage("ESC stop hotkey unavailable (listener failed)", 5000)

    def _stop_esc_listener(self) -> None:
        try:
            if self._esc_listener is not None:
                self._esc_listener.stop()
        except Exception:
            pass
        finally:
            self._esc_listener = None

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        tab_main = QtWidgets.QWidget()
        tab_main_layout = QtWidgets.QVBoxLayout(tab_main)

        tab_cfg = QtWidgets.QWidget()
        tab_cfg_layout = QtWidgets.QVBoxLayout(tab_cfg)

        tab_timing = QtWidgets.QWidget()
        tab_timing_layout = QtWidgets.QVBoxLayout(tab_timing)

        tabs.addTab(tab_main, "Main")
        tabs.addTab(tab_cfg, "Color configuration")
        tabs.addTab(tab_timing, "Timing / reliability")

        # Image load
        row1 = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Import image…")
        self.lbl_image = QtWidgets.QLabel("No image loaded")
        self.lbl_image.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row1.addWidget(self.btn_load)
        row1.addWidget(self.lbl_image, 1)
        tab_main_layout.addLayout(row1)

        # Preset / Precision / Part
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Canvas preset:"))
        self.cbo_preset = QtWidgets.QComboBox()
        self.cbo_preset.addItems(
            [
                ONE_TO_ONE_PRESET_NAME,
                SIXTEEN_NINE_PRESET_NAME,
                NINE_SIXTEEN_PRESET_NAME,
                FOUR_THREE_PRESET_NAME,
                THREE_FOUR_PRESET_NAME,
                *GAME_DRAW_PRESET_NAMES,
                CUSTOM_CLOTHING_PRESET_NAME,
            ]
        )
        row2.addWidget(self.cbo_preset, 1)

        self.lbl_precision = QtWidgets.QLabel("Precision:")
        self.cbo_precision = QtWidgets.QComboBox()
        self.cbo_precision.addItems(list(ONE_TO_ONE_PRECISIONS.keys()))
        row2.addWidget(self.lbl_precision)
        row2.addWidget(self.cbo_precision)

        self.lbl_part = QtWidgets.QLabel("Part:")
        self.cbo_part = QtWidgets.QComboBox()
        self.cbo_part.addItems(game_draw_part_names(TSHIRT_PRESET_NAME) or list(TSHIRT_PARTS.keys()))
        row2.addWidget(self.lbl_part)
        row2.addWidget(self.cbo_part)

        self.btn_edit_custom_part = QtWidgets.QPushButton("Add/Edit part...")
        self.btn_remove_custom_part = QtWidgets.QPushButton("Remove part")
        row2.addWidget(self.btn_edit_custom_part)
        row2.addWidget(self.btn_remove_custom_part)

        self.btn_select_canvas = QtWidgets.QPushButton("Select canvas area…")
        row2.addWidget(self.btn_select_canvas)
        tab_main_layout.addLayout(row2)

        self.lbl_canvas = QtWidgets.QLabel("Canvas: not selected")
        tab_main_layout.addWidget(self.lbl_canvas)

        self.lbl_global_buttons = QtWidgets.QLabel("Palette buttons: not set")
        self.lbl_global_buttons.setWordWrap(True)
        tab_main_layout.addWidget(self.lbl_global_buttons)

        # Smart image preparation
        prep_group = QtWidgets.QGroupBox("Smart image prep")
        prep_layout = QtWidgets.QGridLayout(prep_group)

        self.cbo_fit_mode = QtWidgets.QComboBox()
        self.cbo_fit_mode.addItems(["Smart", "Stretch", "Contain", "Cover"])
        self.chk_auto_crop = QtWidgets.QCheckBox("Auto-crop empty border")
        self.chk_palette_map = QtWidgets.QCheckBox("Map preview to captured palette")
        self.chk_dither = QtWidgets.QCheckBox("Dither palette-mapped image")
        self.btn_bg_color = QtWidgets.QPushButton("Background: #FFFFFF")
        self.btn_reapply_prep = QtWidgets.QPushButton("Re-apply to loaded image")
        self.artpia_template_widget = QtWidgets.QWidget()
        artpia_template_layout = QtWidgets.QHBoxLayout(self.artpia_template_widget)
        artpia_template_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_artpia_exact_mask = QtWidgets.QCheckBox("Clip imported image to Art-pia exact mask")
        self.btn_export_artpia_guide = QtWidgets.QPushButton("Export Art-pia GPT guide...")
        artpia_template_layout.addWidget(self.chk_artpia_exact_mask)
        artpia_template_layout.addWidget(self.btn_export_artpia_guide)
        artpia_template_layout.addStretch(1)
        self.lbl_prep_hint = QtWidgets.QLabel(
            "Smart keeps the full artwork, trims empty borders, then fits it into the selected grid."
        )
        self.lbl_prep_hint.setWordWrap(True)

        self.dress_mapping_widget = QtWidgets.QWidget()
        dress_mapping_layout = QtWidgets.QHBoxLayout(self.dress_mapping_widget)
        dress_mapping_layout.setContentsMargins(0, 0, 0, 0)
        self.spin_dress_scale = QtWidgets.QSpinBox()
        self.spin_dress_scale.setRange(25, 300)
        self.spin_dress_scale.setSingleStep(5)
        self.spin_dress_scale.setSuffix(" %")
        self.spin_dress_offset_x = QtWidgets.QSpinBox()
        self.spin_dress_offset_x.setRange(-500, 500)
        self.spin_dress_offset_x.setSingleStep(1)
        self.spin_dress_offset_x.setSuffix(" px")
        self.spin_dress_offset_y = QtWidgets.QSpinBox()
        self.spin_dress_offset_y.setRange(-500, 500)
        self.spin_dress_offset_y.setSingleStep(1)
        self.spin_dress_offset_y.setSuffix(" px")
        self.btn_reset_dress_mapping = QtWidgets.QPushButton("Reset")
        self.btn_export_dress_templates = QtWidgets.QPushButton("Export Dress templates...")
        dress_mapping_layout.addWidget(QtWidgets.QLabel("Dress image scale:"))
        dress_mapping_layout.addWidget(self.spin_dress_scale)
        dress_mapping_layout.addWidget(QtWidgets.QLabel("Offset X:"))
        dress_mapping_layout.addWidget(self.spin_dress_offset_x)
        dress_mapping_layout.addWidget(QtWidgets.QLabel("Offset Y:"))
        dress_mapping_layout.addWidget(self.spin_dress_offset_y)
        dress_mapping_layout.addWidget(self.btn_reset_dress_mapping)
        dress_mapping_layout.addWidget(self.btn_export_dress_templates)
        dress_mapping_layout.addStretch(1)

        prep_layout.addWidget(QtWidgets.QLabel("Fit:"), 0, 0)
        prep_layout.addWidget(self.cbo_fit_mode, 0, 1)
        prep_layout.addWidget(self.chk_auto_crop, 0, 2)
        prep_layout.addWidget(self.chk_palette_map, 1, 0, 1, 2)
        prep_layout.addWidget(self.chk_dither, 1, 2)
        prep_layout.addWidget(self.btn_bg_color, 2, 0)
        prep_layout.addWidget(self.btn_reapply_prep, 2, 1)
        prep_layout.addWidget(self.artpia_template_widget, 3, 0, 1, 3)
        prep_layout.addWidget(self.dress_mapping_widget, 4, 0, 1, 3)
        prep_layout.addWidget(self.lbl_prep_hint, 5, 0, 1, 3)
        tab_main_layout.addWidget(prep_group)

        # Config
        cfg_group = QtWidgets.QGroupBox("Color configuration")
        cfg_layout = QtWidgets.QVBoxLayout(cfg_group)

        row_cfg1 = QtWidgets.QHBoxLayout()
        self.btn_set_shades_button = QtWidgets.QPushButton("Set shades-panel button")
        self.btn_set_back_button = QtWidgets.QPushButton("Set back button")
        self.btn_show_main_overlay = QtWidgets.QPushButton("Show main-color overlay")
        row_cfg1.addWidget(self.btn_set_shades_button)
        row_cfg1.addWidget(self.btn_set_back_button)
        row_cfg1.addWidget(self.btn_show_main_overlay)
        cfg_layout.addLayout(row_cfg1)

        row_cfg_tools = QtWidgets.QHBoxLayout()
        self.btn_set_paint_tool = QtWidgets.QPushButton("Set paint tool button")
        self.btn_set_bucket_tool = QtWidgets.QPushButton("Set bucket tool button")
        row_cfg_tools.addWidget(self.btn_set_paint_tool)
        row_cfg_tools.addWidget(self.btn_set_bucket_tool)
        cfg_layout.addLayout(row_cfg_tools)

        row_cfg_tools2 = QtWidgets.QHBoxLayout()
        self.btn_set_eraser_tool = QtWidgets.QPushButton("Set eraser tool button")
        self.btn_set_eraser_thick_up = QtWidgets.QPushButton("Set eraser thickness + button")
        row_cfg_tools2.addWidget(self.btn_set_eraser_tool)
        row_cfg_tools2.addWidget(self.btn_set_eraser_thick_up)
        cfg_layout.addLayout(row_cfg_tools2)

        row_cfg2 = QtWidgets.QHBoxLayout()
        self.btn_add_color = QtWidgets.QPushButton("Setup new color…")
        self.btn_remove_color = QtWidgets.QPushButton("Remove selected")
        self.btn_fix_swap_rb = QtWidgets.QPushButton("Fix colors: swap R/B")
        row_cfg2.addWidget(self.btn_add_color)
        row_cfg2.addWidget(self.btn_remove_color)
        row_cfg2.addWidget(self.btn_fix_swap_rb)
        cfg_layout.addLayout(row_cfg2)

        self.lst_colors = QtWidgets.QListWidget()
        cfg_layout.addWidget(self.lst_colors)

        self.lbl_cfg_hint = QtWidgets.QLabel(
            "Tip: Move mouse to top-left to abort painting (PyAutoGUI failsafe)."
        )
        self.lbl_cfg_hint.setWordWrap(True)
        cfg_layout.addWidget(self.lbl_cfg_hint)

        tab_cfg_layout.addWidget(cfg_group)

        tab_cfg_layout.addStretch(1)

        # Timing / reliability (tab)
        timing = QtWidgets.QGroupBox("Timing / reliability")
        tlay = QtWidgets.QGridLayout(timing)

        def ms_spin(min_ms: int, max_ms: int, step_ms: int):
            s = QtWidgets.QSpinBox()
            s.setRange(min_ms, max_ms)
            s.setSingleStep(step_ms)
            s.setSuffix(" ms")
            return s

        self.spin_move = ms_spin(0, 500, 5)
        self.spin_down = ms_spin(0, 500, 5)
        self.spin_after = ms_spin(0, 2000, 10)
        self.spin_panel = ms_spin(0, 3000, 10)
        self.spin_shade = ms_spin(0, 2000, 10)
        self.spin_row = ms_spin(0, 5000, 10)

        self.chk_drag = QtWidgets.QCheckBox("Stroke neighbors (rapid clicks)")
        self.spin_drag_step = ms_spin(0, 200, 1)
        self.spin_after_drag = ms_spin(0, 2000, 10)

        self.chk_verify = QtWidgets.QCheckBox("Verify (repaint misses)")
        self.spin_verify_tol = QtWidgets.QSpinBox()
        self.spin_verify_tol.setRange(0, 255)
        self.spin_verify_tol.setSingleStep(1)
        self.spin_verify_tol.setSuffix(" tol")
        self.spin_verify_passes = QtWidgets.QSpinBox()
        self.spin_verify_passes.setRange(1, 50)
        self.spin_verify_passes.setSingleStep(1)
        self.spin_verify_passes.setSuffix(" passes")

        self.chk_verify_streaming = QtWidgets.QCheckBox("Verify while painting (lag)")
        self.spin_verify_lag = QtWidgets.QSpinBox()
        self.spin_verify_lag.setRange(0, 500)
        self.spin_verify_lag.setSingleStep(1)
        self.spin_verify_lag.setSuffix(" cells")

        self.chk_verify_auto_recover = QtWidgets.QCheckBox("Auto-recover verify loops (skip stuck verify)")

        self.chk_status_overlay = QtWidgets.QCheckBox("Show in-game status overlay")

        tlay.addWidget(QtWidgets.QLabel("Mouse move duration:"), 0, 0)
        tlay.addWidget(self.spin_move, 0, 1)
        tlay.addWidget(QtWidgets.QLabel("Mouse down hold:"), 1, 0)
        tlay.addWidget(self.spin_down, 1, 1)
        tlay.addWidget(QtWidgets.QLabel("After each click delay:"), 2, 0)
        tlay.addWidget(self.spin_after, 2, 1)
        tlay.addWidget(QtWidgets.QLabel("After opening shades panel:"), 0, 2)
        tlay.addWidget(self.spin_panel, 0, 3)
        tlay.addWidget(QtWidgets.QLabel("After selecting shade:"), 1, 2)
        tlay.addWidget(self.spin_shade, 1, 3)
        tlay.addWidget(QtWidgets.QLabel("Row delay:"), 2, 2)
        tlay.addWidget(self.spin_row, 2, 3)

        tlay.addWidget(self.chk_drag, 3, 0, 1, 2)
        tlay.addWidget(QtWidgets.QLabel("Stroke step delay:"), 3, 2)
        tlay.addWidget(self.spin_drag_step, 3, 3)
        tlay.addWidget(QtWidgets.QLabel("After stroke delay:"), 4, 2)
        tlay.addWidget(self.spin_after_drag, 4, 3)

        tlay.addWidget(self.chk_verify, 4, 0, 1, 2)
        tlay.addWidget(QtWidgets.QLabel("Verify tolerance:"), 5, 2)
        tlay.addWidget(self.spin_verify_tol, 5, 3)
        tlay.addWidget(QtWidgets.QLabel("Verify max passes:"), 6, 2)
        tlay.addWidget(self.spin_verify_passes, 6, 3)

        tlay.addWidget(self.chk_verify_streaming, 5, 0, 1, 2)
        tlay.addWidget(QtWidgets.QLabel("Verify lag:"), 6, 0)
        tlay.addWidget(self.spin_verify_lag, 6, 1)

        tlay.addWidget(self.chk_verify_auto_recover, 7, 2, 1, 2)

        tlay.addWidget(self.chk_status_overlay, 8, 0, 1, 2)

        tab_timing_layout.addWidget(timing)

        tab_timing_layout.addStretch(1)

        # Paint (main tab)
        paint_group = QtWidgets.QGroupBox("Paint")
        paint_layout = QtWidgets.QVBoxLayout(paint_group)

        rowm = QtWidgets.QHBoxLayout()
        rowm.addWidget(QtWidgets.QLabel("Method:"))
        self.cbo_paint_mode = QtWidgets.QComboBox()
        self.cbo_paint_mode.addItems(["Paint by Row", "Paint by Color"])
        rowm.addWidget(self.cbo_paint_mode)
        rowm.addStretch(1)
        paint_layout.addLayout(rowm)

        row_bucket = QtWidgets.QHBoxLayout()
        self.chk_bucket_fill = QtWidgets.QCheckBox("Bucket-fill most-used color first")
        self.spin_bucket_min = QtWidgets.QSpinBox()
        self.spin_bucket_min.setRange(0, 100000)
        self.spin_bucket_min.setSingleStep(10)
        self.spin_bucket_min.setSuffix(" min cells")
        row_bucket.addWidget(self.chk_bucket_fill)
        row_bucket.addStretch(1)
        row_bucket.addWidget(QtWidgets.QLabel("Threshold:"))
        row_bucket.addWidget(self.spin_bucket_min)
        paint_layout.addLayout(row_bucket)

        row_bucket2 = QtWidgets.QHBoxLayout()
        self.chk_bucket_regions = QtWidgets.QCheckBox("Bucket-fill large regions (outline first)")
        self.spin_bucket_regions_min = QtWidgets.QSpinBox()
        self.spin_bucket_regions_min.setRange(0, 100000)
        self.spin_bucket_regions_min.setSingleStep(25)
        self.spin_bucket_regions_min.setSuffix(" min cells")
        row_bucket2.addWidget(self.chk_bucket_regions)
        row_bucket2.addStretch(1)
        row_bucket2.addWidget(QtWidgets.QLabel("Threshold:"))
        row_bucket2.addWidget(self.spin_bucket_regions_min)
        paint_layout.addLayout(row_bucket2)

        rowp = QtWidgets.QHBoxLayout()
        self.btn_paint = QtWidgets.QPushButton("Paint now")
        self.btn_resume = QtWidgets.QPushButton("Resume")
        self.btn_resume.setEnabled(False)
        self.btn_erase = QtWidgets.QPushButton("Erase canvas")
        self.btn_stop = QtWidgets.QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        rowp.addWidget(self.btn_paint)
        rowp.addWidget(self.btn_resume)
        rowp.addWidget(self.btn_erase)
        rowp.addWidget(self.btn_stop)
        paint_layout.addLayout(rowp)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        paint_layout.addWidget(self.progress)

        tab_main_layout.addWidget(paint_group)

        tab_main_layout.addStretch(1)

        # Wiring
        self.btn_load.clicked.connect(self._on_load)
        self.btn_select_canvas.clicked.connect(self._on_select_canvas)
        self.btn_edit_custom_part.clicked.connect(self._on_add_edit_custom_part)
        self.btn_remove_custom_part.clicked.connect(self._on_remove_custom_part)
        self.btn_set_shades_button.clicked.connect(lambda: self._capture_global_button("shades"))
        self.btn_set_back_button.clicked.connect(lambda: self._capture_global_button("back"))
        self.btn_show_main_overlay.clicked.connect(self._on_toggle_main_color_overlay)
        self.btn_set_paint_tool.clicked.connect(lambda: self._capture_global_button("paint_tool"))
        self.btn_set_bucket_tool.clicked.connect(lambda: self._capture_global_button("bucket_tool"))
        self.btn_set_eraser_tool.clicked.connect(lambda: self._capture_global_button("eraser_tool"))
        self.btn_set_eraser_thick_up.clicked.connect(lambda: self._capture_global_button("eraser_thick_up"))
        self.btn_add_color.clicked.connect(self._on_setup_new_color)
        self.btn_remove_color.clicked.connect(self._on_remove_selected_color)
        self.btn_fix_swap_rb.clicked.connect(self._on_fix_swap_rb)
        self.btn_paint.clicked.connect(self._on_paint)
        self.btn_resume.clicked.connect(self._on_resume)
        self.btn_erase.clicked.connect(self._on_erase)
        self.btn_stop.clicked.connect(self._on_stop)

        self.cbo_preset.currentTextChanged.connect(self._on_preset_changed)
        self.cbo_precision.currentTextChanged.connect(self._on_precision_changed)
        self.cbo_part.currentTextChanged.connect(self._on_part_changed)
        self.cbo_part.currentIndexChanged.connect(lambda _i: self._on_part_changed(self.cbo_part.currentText()))

        self.cbo_fit_mode.currentTextChanged.connect(lambda _v: self._on_image_prep_changed())
        self.chk_auto_crop.stateChanged.connect(lambda _v: self._on_image_prep_changed())
        self.chk_palette_map.stateChanged.connect(lambda _v: self._on_image_prep_changed())
        self.chk_dither.stateChanged.connect(lambda _v: self._on_image_prep_changed())
        self.chk_artpia_exact_mask.stateChanged.connect(lambda _v: self._on_image_prep_changed())
        self.btn_bg_color.clicked.connect(self._on_background_color)
        self.btn_reapply_prep.clicked.connect(self._on_reapply_image_prep)
        self.btn_export_artpia_guide.clicked.connect(self._on_export_artpia_guide)
        self.spin_dress_scale.valueChanged.connect(lambda _v: self._on_dress_mapping_changed())
        self.spin_dress_offset_x.valueChanged.connect(lambda _v: self._on_dress_mapping_changed())
        self.spin_dress_offset_y.valueChanged.connect(lambda _v: self._on_dress_mapping_changed())
        self.btn_reset_dress_mapping.clicked.connect(self._on_reset_dress_mapping)
        self.btn_export_dress_templates.clicked.connect(self._on_export_dress_templates)

        self.cbo_paint_mode.currentTextChanged.connect(self._on_paint_mode_changed)

        self.chk_bucket_fill.stateChanged.connect(lambda _v: self._on_bucket_fill_changed())
        self.spin_bucket_min.valueChanged.connect(lambda _v: self._on_bucket_fill_changed())
        self.chk_bucket_regions.stateChanged.connect(lambda _v: self._on_bucket_fill_changed())
        self.spin_bucket_regions_min.valueChanged.connect(lambda _v: self._on_bucket_fill_changed())

        self.spin_move.valueChanged.connect(self._on_timing_changed)
        self.spin_down.valueChanged.connect(self._on_timing_changed)
        self.spin_after.valueChanged.connect(self._on_timing_changed)
        self.spin_panel.valueChanged.connect(self._on_timing_changed)
        self.spin_shade.valueChanged.connect(self._on_timing_changed)
        self.spin_row.valueChanged.connect(self._on_timing_changed)
        self.chk_drag.stateChanged.connect(lambda _v: self._on_timing_changed(0))
        self.spin_drag_step.valueChanged.connect(self._on_timing_changed)
        self.spin_after_drag.valueChanged.connect(self._on_timing_changed)

        self.chk_verify.stateChanged.connect(lambda _v: self._on_verify_changed())
        self.spin_verify_tol.valueChanged.connect(lambda _v: self._on_verify_changed())
        self.spin_verify_passes.valueChanged.connect(lambda _v: self._on_verify_changed())
        self.chk_verify_streaming.stateChanged.connect(lambda _v: self._on_verify_changed())
        self.spin_verify_lag.valueChanged.connect(lambda _v: self._on_verify_changed())
        self.chk_verify_auto_recover.stateChanged.connect(lambda _v: self._on_verify_changed())

        self.chk_status_overlay.stateChanged.connect(lambda _v: self._on_status_overlay_changed())

    def _on_status_overlay_changed(self) -> None:
        self._cfg.status_overlay_enabled = bool(self.chk_status_overlay.isChecked())
        self._save_cfg()
        if not self._cfg.status_overlay_enabled:
            self._hide_status_overlay()

    def _on_toggle_main_color_overlay(self) -> None:
        # Toggle if already visible.
        try:
            if self._markers_overlay is not None and self._markers_overlay.isVisible():
                self._markers_overlay.hide()
                return
        except Exception:
            pass

        markers: list[Marker] = []
        for mc in getattr(self._cfg, "main_colors", []) or []:
            pos = getattr(mc, "pos", None)
            if not pos or tuple(pos) == (0, 0):
                continue
            rgb = getattr(mc, "rgb", (0, 200, 255))
            markers.append(Marker(label=str(getattr(mc, "name", "Color")), pos=(int(pos[0]), int(pos[1])), color=rgb))

        if not markers:
            QtWidgets.QMessageBox.information(
                self,
                "No main colors",
                "No main color button positions are saved yet.\n\nUse 'Setup new color…' first.",
            )
            return

        self._markers_overlay = MarkersOverlay(
            markers=markers,
            title="Main color button positions",
            duration_ms=15000,
        )
        self._markers_overlay.start()

    def _ensure_custom_parts(self) -> None:
        if not getattr(self._cfg, "custom_clothing_parts", None):
            self._cfg.custom_clothing_parts = [ClothingPartSpec(name="Part 1", w=64, h=80)]
        names = [p.name for p in self._cfg.custom_clothing_parts]
        if getattr(self._cfg, "custom_clothing_part", "") not in names:
            self._cfg.custom_clothing_part = names[0]

    def _custom_part_by_name(self, name: str) -> ClothingPartSpec:
        self._ensure_custom_parts()
        for part in self._cfg.custom_clothing_parts:
            if part.name == name:
                return part
        return self._cfg.custom_clothing_parts[0]

    def _remember_current_game_draw_part(self) -> None:
        preset = self.cbo_preset.currentText()
        if not is_game_draw_preset(preset):
            return
        part = canonical_game_draw_part(preset, self.cbo_part.currentText())
        if not isinstance(getattr(self._cfg, "game_draw_part_by_preset", None), dict):
            self._cfg.game_draw_part_by_preset = {}
        self._cfg.game_draw_part_by_preset[preset] = part
        if preset == TSHIRT_PRESET_NAME:
            self._cfg.tshirt_part = part
        elif preset == TANK_TOP_PRESET_NAME:
            self._cfg.tank_top_part = part
        elif preset == DRESS_PRESET_NAME:
            self._cfg.dress_part = part

    def _sync_part_combo_for_preset(self) -> None:
        preset = self.cbo_preset.currentText()
        self.cbo_part.blockSignals(True)
        try:
            self.cbo_part.clear()
            if is_game_draw_preset(preset):
                parts = game_draw_part_names(preset)
                self.cbo_part.addItems(parts)
                preferred = (getattr(self._cfg, "game_draw_part_by_preset", {}) or {}).get(preset, "")
                if not preferred and preset == TSHIRT_PRESET_NAME:
                    preferred = getattr(self._cfg, "tshirt_part", "")
                elif not preferred and preset == TANK_TOP_PRESET_NAME:
                    preferred = getattr(self._cfg, "tank_top_part", "")
                elif not preferred and preset == DRESS_PRESET_NAME:
                    preferred = getattr(self._cfg, "dress_part", "")
                if preferred not in parts:
                    preferred = default_game_draw_part(preset)
                if preferred and self.cbo_part.findText(preferred) >= 0:
                    self.cbo_part.setCurrentText(preferred)
                self._remember_current_game_draw_part()
            elif preset == CUSTOM_CLOTHING_PRESET_NAME:
                self._ensure_custom_parts()
                self.cbo_part.addItems([p.name for p in self._cfg.custom_clothing_parts])
                if self._cfg.custom_clothing_part and self.cbo_part.findText(self._cfg.custom_clothing_part) >= 0:
                    self.cbo_part.setCurrentText(self._cfg.custom_clothing_part)
            else:
                self.cbo_part.addItems(list(TSHIRT_PARTS.keys()))
        finally:
            self.cbo_part.blockSignals(False)

    def _palette_rgbs(self) -> list[Tuple[int, int, int]]:
        rgbs: list[Tuple[int, int, int]] = []
        for mc in getattr(self._cfg, "main_colors", []) or []:
            for sh in getattr(mc, "shades", []) or []:
                try:
                    rgbs.append((int(sh.rgb[0]), int(sh.rgb[1]), int(sh.rgb[2])))
                except Exception:
                    pass
        return rgbs

    def _painter_options_from_cfg(self) -> PainterOptions:
        return PainterOptions(
            move_duration_s=float(getattr(self._cfg, "move_duration_s", 0.03)),
            mouse_down_s=float(getattr(self._cfg, "mouse_down_s", 0.02)),
            after_click_delay_s=float(getattr(self._cfg, "after_click_delay_s", 0.06)),
            panel_open_delay_s=float(getattr(self._cfg, "panel_open_delay_s", 0.12)),
            shade_select_delay_s=float(getattr(self._cfg, "shade_select_delay_s", 0.06)),
            row_delay_s=float(getattr(self._cfg, "row_delay_s", 0.10)),
            enable_drag_strokes=bool(getattr(self._cfg, "enable_drag_strokes", False)),
            drag_step_duration_s=float(getattr(self._cfg, "drag_step_duration_s", 0.01)),
            after_drag_delay_s=float(getattr(self._cfg, "after_drag_delay_s", 0.02)),
        )

    def _current_prep_options(self) -> ImagePrepOptions:
        return ImagePrepOptions(
            fit_mode=str(getattr(self._cfg, "image_fit_mode", "Smart")),
            auto_crop=bool(getattr(self._cfg, "image_auto_crop", True)),
            palette_map=bool(getattr(self._cfg, "image_palette_map_enabled", False)),
            dither=bool(getattr(self._cfg, "image_dither_enabled", False)),
            background_rgb=tuple(getattr(self._cfg, "image_background_rgb", (255, 255, 255))),
        )

    def _current_dress_part(self) -> str:
        fallback = default_game_draw_part(DRESS_PRESET_NAME)
        part = self.cbo_part.currentText() or getattr(self._cfg, "dress_part", fallback) or fallback
        return canonical_game_draw_part(DRESS_PRESET_NAME, part)

    def _current_game_draw_part(self, preset: str) -> str:
        fallback = default_game_draw_part(preset)
        part = self.cbo_part.currentText() or (getattr(self._cfg, "game_draw_part_by_preset", {}) or {}).get(preset, "") or fallback
        return canonical_game_draw_part(preset, part)

    def _dress_mapping_values(self, part: str) -> tuple[float, float, float]:
        scale_map = getattr(self._cfg, "dress_mapping_scale_by_part", {}) or {}
        offset_x_map = getattr(self._cfg, "dress_mapping_offset_x_by_part", {}) or {}
        offset_y_map = getattr(self._cfg, "dress_mapping_offset_y_by_part", {}) or {}
        try:
            scale = float(scale_map.get(part, 1.0))
        except Exception:
            scale = 1.0
        try:
            offset_x = float(offset_x_map.get(part, 0.0))
        except Exception:
            offset_x = 0.0
        try:
            offset_y = float(offset_y_map.get(part, 0.0))
        except Exception:
            offset_y = 0.0
        return max(0.25, min(3.0, scale)), max(-500.0, min(500.0, offset_x)), max(-500.0, min(500.0, offset_y))

    def _set_dress_mapping_values(self, part: str, scale: float, offset_x: float, offset_y: float) -> None:
        if not isinstance(getattr(self._cfg, "dress_mapping_scale_by_part", None), dict):
            self._cfg.dress_mapping_scale_by_part = {}
        if not isinstance(getattr(self._cfg, "dress_mapping_offset_x_by_part", None), dict):
            self._cfg.dress_mapping_offset_x_by_part = {}
        if not isinstance(getattr(self._cfg, "dress_mapping_offset_y_by_part", None), dict):
            self._cfg.dress_mapping_offset_y_by_part = {}
        self._cfg.dress_mapping_scale_by_part[part] = max(0.25, min(3.0, float(scale)))
        self._cfg.dress_mapping_offset_x_by_part[part] = max(-500.0, min(500.0, float(offset_x)))
        self._cfg.dress_mapping_offset_y_by_part[part] = max(-500.0, min(500.0, float(offset_y)))

    def _adjusted_dress_content_rect(
        self,
        base_rect: Tuple[float, float, float, float],
        part: str,
    ) -> Tuple[float, float, float, float]:
        grid_w, grid_h = DRESS_PARTS.get(part, next(iter(DRESS_PARTS.values()), (102, 154)))
        scale, offset_x, offset_y = self._dress_mapping_values(part)
        x, y, w, h = base_rect
        cx = x + (w / 2.0) + (offset_x / max(1, grid_w))
        cy = y + (h / 2.0) + (offset_y / max(1, grid_h))
        ww = w * scale
        hh = h * scale
        return (cx - (ww / 2.0), cy - (hh / 2.0), ww, hh)

    def _dress_prep_options_for_part(self, part: str) -> ImagePrepOptions:
        prep = self._current_prep_options()
        if str(prep.fit_mode).strip().lower() == "smart":
            # Clothing parts should fill their pattern by default. Plain
            # Smart/Contain preserves the whole source image and leaves
            # empty bands on tall Dress canvases.
            prep.fit_mode = "Cover"
        rect, shape = DRESS_MAPPINGS.get(part, ((0.0, 0.0, 1.0, 1.0), "none"))
        prep.content_rect = self._adjusted_dress_content_rect(rect, part)
        prep.paint_mask_shape = shape
        return prep

    def _artpia_mask_cache_path_for(self, preset: str, part: str) -> str | None:
        template = find_artpia_part_template(preset, part)
        if template is None:
            return None
        cache_dir = self._config_path.parent / "artpia_masks"
        stem = self._safe_template_stem(f"{preset}_{part}_{template.width}x{template.height}")
        path = cache_dir / f"{stem}__artpia_mask.png"
        try:
            if not path.exists():
                save_artpia_mask_file(template, path)
        except Exception:
            return None
        return str(path)

    def _game_draw_prep_options_for_part(self, preset: str, part: str) -> ImagePrepOptions:
        if preset == DRESS_PRESET_NAME:
            prep = self._dress_prep_options_for_part(part)
            if bool(getattr(self._cfg, "artpia_exact_mask_enabled", False)):
                prep.mask_image_path = self._artpia_mask_cache_path_for(preset, part)
            return prep

        prep = self._current_prep_options()
        if str(prep.fit_mode).strip().lower() == "smart":
            # Game draw parts are object surfaces, not normal picture canvases.
            # Match Dress behavior: fill the selected part before palette mapping
            # so background padding does not dominate the colors to paint.
            prep.fit_mode = "Cover"
        prep.content_rect = (0.0, 0.0, 1.0, 1.0)
        prep.paint_mask_shape = "none"
        if bool(getattr(self._cfg, "artpia_exact_mask_enabled", False)):
            prep.mask_image_path = self._artpia_mask_cache_path_for(preset, part)
        return prep

    def _exact_dress_template_prep_options(self, part: str) -> ImagePrepOptions:
        prep = self._current_prep_options()
        prep.fit_mode = "Stretch"
        prep.auto_crop = False
        prep.content_rect = None
        prep.paint_mask_shape = DRESS_MAPPINGS.get(part, ((0.0, 0.0, 1.0, 1.0), "none"))[1]
        return prep

    def _exact_template_prep_options(self, path: str) -> ImagePrepOptions:
        prep = self._current_prep_options()
        prep.fit_mode = "Stretch"
        prep.auto_crop = False
        prep.content_rect = None
        prep.paint_mask_shape = "none"
        name = Path(path).name.lower()
        if "__clothing_template__" in name and "__clothing_template_masked__" not in name:
            prep.ignore_source_alpha = True
        elif self.cbo_preset.currentText() == DRESS_PRESET_NAME and "__clothing_template_masked__" not in name:
            prep.paint_mask_shape = DRESS_MAPPINGS.get(
                self._current_dress_part(),
                ((0.0, 0.0, 1.0, 1.0), "none"),
            )[1]
        return prep

    def _is_exact_template_path(self, path: str, w: int, h: int) -> bool:
        name = Path(path).name.lower()
        markers = ("__dress_template__", "__clothing_template__", "__clothing_template_masked__", "__tshirt_template__")
        if not any(marker in name for marker in markers):
            return False
        try:
            with Image.open(path) as img:
                return img.size == (int(w), int(h))
        except Exception:
            return False

    def _current_image_prep_options(self) -> ImagePrepOptions:
        prep = self._current_prep_options()
        preset = self.cbo_preset.currentText()
        if is_game_draw_preset(preset):
            prep = self._game_draw_prep_options_for_part(preset, self._current_game_draw_part(preset))
        return prep

    def _load_grid_for_path(self, path: str) -> PixelGrid:
        w, h = self._selected_preset_wh()
        palette = self._palette_rgbs() if bool(getattr(self._cfg, "image_palette_map_enabled", False)) else None
        prep = self._current_image_prep_options()
        if is_game_draw_preset(self.cbo_preset.currentText()) and self._is_exact_template_path(path, w, h):
            prep = self._exact_template_prep_options(path)
        return load_and_resize_to_grid(
            path,
            w=w,
            h=h,
            prep=prep,
            palette_rgbs=palette,
        )

    def _update_bg_button(self) -> None:
        rgb = tuple(getattr(self._cfg, "image_background_rgb", (255, 255, 255)))
        try:
            r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        except Exception:
            r, g, b = 255, 255, 255
        self.btn_bg_color.setText(f"Background: #{r:02X}{g:02X}{b:02X}")

    def _sync_image_prep_ui_from_cfg(self) -> None:
        widgets = [
            self.cbo_fit_mode,
            self.chk_auto_crop,
            self.chk_palette_map,
            self.chk_dither,
            self.chk_artpia_exact_mask,
        ]
        for w in widgets:
            w.blockSignals(True)
        try:
            mode = str(getattr(self._cfg, "image_fit_mode", "Smart")).title()
            if self.cbo_fit_mode.findText(mode) < 0:
                mode = "Smart"
            self.cbo_fit_mode.setCurrentText(mode)
            self.chk_auto_crop.setChecked(bool(getattr(self._cfg, "image_auto_crop", True)))
            self.chk_palette_map.setChecked(bool(getattr(self._cfg, "image_palette_map_enabled", False)))
            self.chk_dither.setChecked(bool(getattr(self._cfg, "image_dither_enabled", False)))
            self.chk_artpia_exact_mask.setChecked(bool(getattr(self._cfg, "artpia_exact_mask_enabled", False)))
            self._update_bg_button()
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._sync_dress_mapping_ui_from_cfg()

    def _sync_dress_mapping_ui_from_cfg(self) -> None:
        if not hasattr(self, "spin_dress_scale"):
            return
        widgets = [self.spin_dress_scale, self.spin_dress_offset_x, self.spin_dress_offset_y]
        for w in widgets:
            w.blockSignals(True)
        try:
            part = self._current_dress_part()
            scale, offset_x, offset_y = self._dress_mapping_values(part)
            self.spin_dress_scale.setValue(int(round(scale * 100.0)))
            self.spin_dress_offset_x.setValue(int(round(offset_x)))
            self.spin_dress_offset_y.setValue(int(round(offset_y)))
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _update_dress_mapping_ui_visibility(self) -> None:
        if not hasattr(self, "dress_mapping_widget"):
            return
        preset = self.cbo_preset.currentText()
        is_dress = preset == DRESS_PRESET_NAME
        is_game = is_game_draw_preset(preset)
        self.dress_mapping_widget.setVisible(is_dress)
        self.artpia_template_widget.setVisible(is_game)
        if is_dress:
            self.lbl_prep_hint.setText(
                "Dress + Smart fills the selected clothing part. Use Scale/Offset to align the artwork; "
                "Export Art-pia GPT guide when you need the exact outline and size for generation."
            )
        elif is_game:
            self.lbl_prep_hint.setText(
                "Export Art-pia GPT guide for an exact outline. Enable exact mask to clip generated images "
                "back to the real drawable shape before painting."
            )
        else:
            self.lbl_prep_hint.setText(
                "Smart keeps the full artwork, trims empty borders, then fits it into the selected grid."
            )

    def _reload_loaded_image(self) -> bool:
        if self._loaded is None:
            return False
        path = self._loaded.path
        try:
            grid = self._load_grid_for_path(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Image prep failed", str(e))
            return False
        self._loaded = LoadedImage(path=path, grid=grid)
        self.lbl_image.setText(f"Loaded: {path} ({grid.w}x{grid.h})")
        self._reset_paint_session()
        return True

    def _on_image_prep_changed(self) -> None:
        self._cfg.image_fit_mode = self.cbo_fit_mode.currentText().strip() or "Smart"
        self._cfg.image_auto_crop = bool(self.chk_auto_crop.isChecked())
        self._cfg.image_palette_map_enabled = bool(self.chk_palette_map.isChecked())
        self._cfg.image_dither_enabled = bool(self.chk_dither.isChecked())
        self._cfg.artpia_exact_mask_enabled = bool(self.chk_artpia_exact_mask.isChecked())
        self._save_cfg()
        self._reload_loaded_image()

    def _on_reapply_image_prep(self) -> None:
        if not self._reload_loaded_image():
            QtWidgets.QMessageBox.information(self, "No image", "Import an image first.")

    def _on_dress_mapping_changed(self) -> None:
        if self.cbo_preset.currentText() != DRESS_PRESET_NAME:
            return
        part = self._current_dress_part()
        self._set_dress_mapping_values(
            part,
            self.spin_dress_scale.value() / 100.0,
            float(self.spin_dress_offset_x.value()),
            float(self.spin_dress_offset_y.value()),
        )
        self._save_cfg()
        self._reload_loaded_image()

    def _on_reset_dress_mapping(self) -> None:
        if self.cbo_preset.currentText() != DRESS_PRESET_NAME:
            return
        self._set_dress_mapping_values(self._current_dress_part(), 1.0, 0.0, 0.0)
        self._sync_dress_mapping_ui_from_cfg()
        self._save_cfg()
        self._reload_loaded_image()

    def _safe_template_stem(self, text: str) -> str:
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
        cleaned = "_".join(part for part in cleaned.split("_") if part)
        return cleaned or "image"

    def _save_grid_png(self, grid: PixelGrid, path: Path) -> None:
        img = Image.new("RGB", (int(grid.w), int(grid.h)))
        img.putdata([(int(r), int(g), int(b)) for r, g, b in grid.pixels])
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)

    def _on_export_artpia_guide(self) -> None:
        preset = self.cbo_preset.currentText()
        if not is_game_draw_preset(preset):
            QtWidgets.QMessageBox.information(
                self,
                "Art-pia guide",
                "Choose a game clothing/furniture preset first.",
            )
            return
        part = self._current_game_draw_part(preset)
        template = find_artpia_part_template(preset, part)
        if template is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Art-pia guide",
                f"No Art-pia template data for {preset} / {part}.",
            )
            return

        default_dir = Path(self._loaded.path).parent if self._loaded is not None else Path.home() / "Downloads"
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Export Art-pia GPT guide",
            str(default_dir),
        )
        if not out_dir:
            return

        try:
            paths = save_artpia_template_files(preset, part, Path(out_dir), scale=10)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Art-pia guide export failed", str(e))
            return

        QtWidgets.QMessageBox.information(
            self,
            "Art-pia guide exported",
            "Created exact Art-pia template files:\n\n"
            f"GPT guide: {paths['guide']}\n"
            f"Mask: {paths['mask']}\n\n"
            "Send the GPT guide image to GPT. When you import the generated image back here, "
            "enable Art-pia exact mask to clip it to the same drawable shape.",
        )

    def _on_export_dress_templates(self) -> None:
        if self._loaded is None:
            QtWidgets.QMessageBox.information(self, "No image", "Import the source image first.")
            return
        if self.cbo_preset.currentText() != DRESS_PRESET_NAME:
            self.cbo_preset.setCurrentText(DRESS_PRESET_NAME)

        source_path = Path(self._loaded.path)
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Export Dress templates",
            str(source_path.parent if source_path.exists() else Path.home()),
        )
        if not out_dir:
            return

        palette = self._palette_rgbs() if bool(getattr(self._cfg, "image_palette_map_enabled", False)) else None
        source_stem = self._safe_template_stem(source_path.stem)
        output_paths: dict[str, Path] = {}

        try:
            for part, (w, h) in DRESS_PARTS.items():
                part_stem = self._safe_template_stem(part)
                out_path = Path(out_dir) / f"{source_stem}__dress_template__{part_stem}__{w}x{h}.png"
                grid = load_and_resize_to_grid(
                    str(source_path),
                    w=int(w),
                    h=int(h),
                    prep=self._dress_prep_options_for_part(part),
                    palette_rgbs=palette,
                )
                self._save_grid_png(grid, out_path)
                output_paths[part] = out_path
                self._cfg.last_image_path_by_key[selection_key(DRESS_PRESET_NAME, part)] = str(out_path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(e))
            return

        current_part = self._current_dress_part()
        current_path = output_paths.get(current_part)
        if current_path is not None:
            try:
                grid = self._load_grid_for_path(str(current_path))
                self._loaded = LoadedImage(path=str(current_path), grid=grid)
                self.lbl_image.setText(f"Loaded: {current_path} ({grid.w}x{grid.h})")
                self._reset_paint_session()
            except Exception:
                pass

        self._cfg.last_image_path = str(current_path or source_path)
        self._save_cfg()
        created = "\n".join(str(p) for p in output_paths.values())
        QtWidgets.QMessageBox.information(
            self,
            "Dress templates exported",
            "Created exact-size Dress template images:\n\n"
            f"{created}\n\n"
            "These files can be imported back without being cropped or covered again. "
            "Select the matching Dress part, then select canvas area in-game.",
        )

    def _on_background_color(self) -> None:
        rgb = tuple(getattr(self._cfg, "image_background_rgb", (255, 255, 255)))
        current = QtGui.QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        color = QtWidgets.QColorDialog.getColor(current, self, "Background color")
        if not color.isValid():
            return
        self._cfg.image_background_rgb = (int(color.red()), int(color.green()), int(color.blue()))
        self._update_bg_button()
        self._save_cfg()
        self._reload_loaded_image()

    def _apply_persisted_state(self):
        # Restore preset
        if self._cfg.canvas_preset and self.cbo_preset.findText(self._cfg.canvas_preset) >= 0:
            self.cbo_preset.setCurrentText(self._cfg.canvas_preset)
        self._sync_part_combo_for_preset()

        # Restore precision
        if self._cfg.canvas_preset == ONE_TO_ONE_PRESET_NAME:
            prec = getattr(self._cfg, "one_to_one_precision", None)
            if prec and self.cbo_precision.findText(prec) >= 0:
                self.cbo_precision.setCurrentText(prec)
        elif self._cfg.canvas_preset == SIXTEEN_NINE_PRESET_NAME:
            prec = getattr(self._cfg, "sixteen_nine_precision", None)
            if prec and self.cbo_precision.findText(prec) >= 0:
                self.cbo_precision.setCurrentText(prec)
        elif self._cfg.canvas_preset == NINE_SIXTEEN_PRESET_NAME:
            prec = getattr(self._cfg, "nine_sixteen_precision", None)
            if prec and self.cbo_precision.findText(prec) >= 0:
                self.cbo_precision.setCurrentText(prec)
        elif self._cfg.canvas_preset == FOUR_THREE_PRESET_NAME:
            prec = getattr(self._cfg, "four_three_precision", None)
            if prec and self.cbo_precision.findText(prec) >= 0:
                self.cbo_precision.setCurrentText(prec)
        elif self._cfg.canvas_preset == THREE_FOUR_PRESET_NAME:
            prec = getattr(self._cfg, "three_four_precision", None)
            if prec and self.cbo_precision.findText(prec) >= 0:
                self.cbo_precision.setCurrentText(prec)

        if is_game_draw_preset(self._cfg.canvas_preset):
            self._sync_part_combo_for_preset()
        if self._cfg.canvas_preset == CUSTOM_CLOTHING_PRESET_NAME:
            self._sync_part_combo_for_preset()
            if self._cfg.custom_clothing_part and self.cbo_part.findText(self._cfg.custom_clothing_part) >= 0:
                self.cbo_part.setCurrentText(self._cfg.custom_clothing_part)

        self._update_variant_ui_visibility()
        self._sync_image_prep_ui_from_cfg()

        # Restore per-selection state (image + canvas)
        self._restore_selection_state()

        # Restore timing controls
        self._sync_timing_ui_from_cfg()

        # Restore paint mode
        self._sync_paint_mode_ui_from_cfg()

    def _sync_paint_mode_ui_from_cfg(self) -> None:
        # Block signals so we don't save during startup.
        self.cbo_paint_mode.blockSignals(True)
        try:
            pm = (getattr(self._cfg, "paint_mode", "row") or "row").strip().lower()
            if pm == "color":
                self.cbo_paint_mode.setCurrentText("Paint by Color")
            else:
                self.cbo_paint_mode.setCurrentText("Paint by Row")
        finally:
            self.cbo_paint_mode.blockSignals(False)

    def _on_paint_mode_changed(self, _text: str) -> None:
        txt = self.cbo_paint_mode.currentText().strip().lower()
        self._cfg.paint_mode = "color" if "color" in txt else "row"
        self._save_cfg()

    def _sync_timing_ui_from_cfg(self):
        def to_ms(v: float) -> int:
            return int(round(max(0.0, float(v)) * 1000.0))

        # Block signals to avoid saving on startup repeatedly
        widgets = [
            self.spin_move,
            self.spin_down,
            self.spin_after,
            self.spin_panel,
            self.spin_shade,
            self.spin_row,
            self.spin_drag_step,
            self.spin_after_drag,
        ]
        for w in widgets:
            w.blockSignals(True)
        self.chk_drag.blockSignals(True)
        self.chk_verify.blockSignals(True)
        self.spin_verify_tol.blockSignals(True)
        self.spin_verify_passes.blockSignals(True)
        self.chk_verify_streaming.blockSignals(True)
        self.spin_verify_lag.blockSignals(True)
        self.chk_verify_auto_recover.blockSignals(True)
        self.chk_bucket_fill.blockSignals(True)
        self.spin_bucket_min.blockSignals(True)
        self.chk_bucket_regions.blockSignals(True)
        self.spin_bucket_regions_min.blockSignals(True)
        self.chk_status_overlay.blockSignals(True)

        self.spin_move.setValue(to_ms(self._cfg.move_duration_s))
        self.spin_down.setValue(to_ms(self._cfg.mouse_down_s))
        self.spin_after.setValue(to_ms(self._cfg.after_click_delay_s))
        self.spin_panel.setValue(to_ms(self._cfg.panel_open_delay_s))
        self.spin_shade.setValue(to_ms(self._cfg.shade_select_delay_s))
        self.spin_row.setValue(to_ms(self._cfg.row_delay_s))

        self.chk_drag.setChecked(bool(getattr(self._cfg, "enable_drag_strokes", False)))
        self.spin_drag_step.setValue(to_ms(getattr(self._cfg, "drag_step_duration_s", 0.01)))
        self.spin_after_drag.setValue(to_ms(getattr(self._cfg, "after_drag_delay_s", 0.02)))

        self.chk_verify.setChecked(bool(getattr(self._cfg, "verify_rows", True)))
        self.spin_verify_tol.setValue(int(getattr(self._cfg, "verify_tolerance", 35)))
        self.spin_verify_passes.setValue(int(getattr(self._cfg, "verify_max_passes", 10)))

        self.chk_verify_streaming.setChecked(bool(getattr(self._cfg, "verify_streaming_enabled", False)))
        self.spin_verify_lag.setValue(int(getattr(self._cfg, "verify_streaming_lag", 10)))
        self.chk_verify_auto_recover.setChecked(bool(getattr(self._cfg, "verify_auto_recover_loops", False)))

        self.chk_bucket_fill.setChecked(bool(getattr(self._cfg, "bucket_fill_enabled", False)))
        self.spin_bucket_min.setValue(int(getattr(self._cfg, "bucket_fill_min_cells", 50)))

        self.chk_bucket_regions.setChecked(bool(getattr(self._cfg, "bucket_fill_regions_enabled", False)))
        self.spin_bucket_regions_min.setValue(int(getattr(self._cfg, "bucket_fill_regions_min_cells", 200)))

        self.chk_status_overlay.setChecked(bool(getattr(self._cfg, "status_overlay_enabled", True)))

        for w in widgets:
            w.blockSignals(False)
        self.chk_drag.blockSignals(False)
        self.chk_verify.blockSignals(False)
        self.spin_verify_tol.blockSignals(False)
        self.spin_verify_passes.blockSignals(False)
        self.chk_verify_streaming.blockSignals(False)
        self.spin_verify_lag.blockSignals(False)
        self.chk_verify_auto_recover.blockSignals(False)
        self.chk_bucket_fill.blockSignals(False)
        self.spin_bucket_min.blockSignals(False)
        self.chk_bucket_regions.blockSignals(False)
        self.spin_bucket_regions_min.blockSignals(False)
        self.chk_status_overlay.blockSignals(False)

    def _on_timing_changed(self, _value: int):
        # Persist timing settings immediately
        def to_s(ms: int) -> float:
            return max(0.0, float(ms) / 1000.0)

        self._cfg.move_duration_s = to_s(self.spin_move.value())
        self._cfg.mouse_down_s = to_s(self.spin_down.value())
        self._cfg.after_click_delay_s = to_s(self.spin_after.value())
        self._cfg.panel_open_delay_s = to_s(self.spin_panel.value())
        self._cfg.shade_select_delay_s = to_s(self.spin_shade.value())
        self._cfg.row_delay_s = to_s(self.spin_row.value())

        self._cfg.enable_drag_strokes = bool(self.chk_drag.isChecked())
        self._cfg.drag_step_duration_s = to_s(self.spin_drag_step.value())
        self._cfg.after_drag_delay_s = to_s(self.spin_after_drag.value())
        self._save_cfg()

    def _on_verify_changed(self) -> None:
        self._cfg.verify_rows = bool(self.chk_verify.isChecked())
        self._cfg.verify_tolerance = int(self.spin_verify_tol.value())
        self._cfg.verify_max_passes = int(self.spin_verify_passes.value())
        self._cfg.verify_streaming_enabled = bool(self.chk_verify_streaming.isChecked())
        self._cfg.verify_streaming_lag = int(self.spin_verify_lag.value())
        self._cfg.verify_auto_recover_loops = bool(self.chk_verify_auto_recover.isChecked())
        self._save_cfg()

    def _on_bucket_fill_changed(self) -> None:
        self._cfg.bucket_fill_enabled = bool(self.chk_bucket_fill.isChecked())
        self._cfg.bucket_fill_min_cells = int(self.spin_bucket_min.value())
        self._cfg.bucket_fill_regions_enabled = bool(self.chk_bucket_regions.isChecked())
        self._cfg.bucket_fill_regions_min_cells = int(self.spin_bucket_regions_min.value())
        self._save_cfg()

    def _refresh_config_view(self):
        self.lst_colors.clear()
        for mc in self._cfg.main_colors:
            self.lst_colors.addItem(f"{mc.name}  ({len(mc.shades)} shades)")

        preset = self.cbo_preset.currentText()
        part_txt = ""
        if preset == ONE_TO_ONE_PRESET_NAME:
            part_txt = f" — {self.cbo_precision.currentText()}"
        elif preset == SIXTEEN_NINE_PRESET_NAME:
            part_txt = f" — {self.cbo_precision.currentText()}"
        elif preset == NINE_SIXTEEN_PRESET_NAME:
            part_txt = f" — {self.cbo_precision.currentText()}"
        elif preset == FOUR_THREE_PRESET_NAME:
            part_txt = f" — {self.cbo_precision.currentText()}"
        elif preset == THREE_FOUR_PRESET_NAME:
            part_txt = f" — {self.cbo_precision.currentText()}"
        elif is_game_draw_preset(preset):
            w, h = self._selected_preset_wh()
            part_txt = f" - {self.cbo_part.currentText()} ({w}x{h})"
        elif preset == CUSTOM_CLOTHING_PRESET_NAME:
            w, h = self._selected_preset_wh()
            part_txt = f" - {self.cbo_part.currentText()} ({w}x{h})"
        elif preset == TSHIRT_PRESET_NAME:
            part_txt = f" — {self.cbo_part.currentText()}"
        elif preset == TANK_TOP_PRESET_NAME:
            part_txt = f" — {self.cbo_part.currentText()}"

        if self._canvas_rect is None:
            self.lbl_canvas.setText(f"Canvas{part_txt}: not selected")
        else:
            x, y, w, h = self._canvas_rect
            self.lbl_canvas.setText(f"Canvas{part_txt}: x={x}, y={y}, w={w}, h={h}")

        sp = self._cfg.shades_panel_button_pos
        bp = self._cfg.back_button_pos
        pp = getattr(self._cfg, "paint_tool_button_pos", None)
        bk = getattr(self._cfg, "bucket_tool_button_pos", None)
        er = getattr(self._cfg, "eraser_tool_button_pos", None)
        eu = getattr(self._cfg, "eraser_thickness_up_button_pos", None)
        sp_txt = f"{sp}" if sp is not None else "(not set)"
        bp_txt = f"{bp}" if bp is not None else "(not set)"
        pp_txt = f"{pp}" if pp is not None else "(not set)"
        bk_txt = f"{bk}" if bk is not None else "(not set)"
        er_txt = f"{er}" if er is not None else "(not set)"
        eu_txt = f"{eu}" if eu is not None else "(not set)"
        self.lbl_global_buttons.setText(
            f"Palette buttons — Shades panel: {sp_txt} | Back: {bp_txt} | Paint tool: {pp_txt} | Bucket: {bk_txt} | Eraser: {er_txt} | Eraser +: {eu_txt}"
        )

    def _save_cfg(self):
        save_config(self._config_path, self._cfg)

    def _run_on_ui_thread(self, fn) -> None:
        # QTimer.singleShot reliably queues work onto the Qt event loop.
        QtCore.QTimer.singleShot(0, fn)

    def _confirm_capture(self, label: str, res: ClickCaptureResult):
        self.statusBar().showMessage(f"Captured {label} at {res.pos} rgb={res.rgb}", 5000)
        QtWidgets.QMessageBox.information(
            self,
            "Captured",
            f"Captured {label}.\n\nPosition: {res.pos}\nRGB: {res.rgb}",
        )

    def _capture_click_async(self, title: str, message: str, apply_capture):
        """Shows a prompt, then uses a fullscreen overlay to pick a point + sample RGB."""
        QtWidgets.QMessageBox.information(self, title, message)

        ov = PointSelectOverlay(instruction="Click the location on screen (ESC/right-click to cancel)")
        self._point_overlay = ov  # keep alive

        def on_sel(p: PointResult):
            rgb = get_screen_pixel_rgb(int(p.x), int(p.y))
            res = ClickCaptureResult(pos=(int(p.x), int(p.y)), rgb=rgb)
            self._run_on_ui_thread(lambda: apply_capture(res))

        ov.pointSelected.connect(on_sel)
        ov.cancelled.connect(lambda: None)
        ov.start()

    def _selected_preset_wh(self) -> Tuple[int, int]:
        preset = self.cbo_preset.currentText()
        if preset == ONE_TO_ONE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or self._cfg.one_to_one_precision or "Small"
            return ONE_TO_ONE_PRECISIONS.get(precision, ONE_TO_ONE_PRECISIONS["Small"])
        if preset == SIXTEEN_NINE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "sixteen_nine_precision", "Small") or "Small"
            return SIXTEEN_NINE_PRECISIONS.get(precision, SIXTEEN_NINE_PRECISIONS["Small"])
        if preset == NINE_SIXTEEN_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "nine_sixteen_precision", "Small") or "Small"
            return NINE_SIXTEEN_PRECISIONS.get(precision, NINE_SIXTEEN_PRECISIONS["Small"])
        if preset == FOUR_THREE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "four_three_precision", "Small") or "Small"
            return FOUR_THREE_PRECISIONS.get(precision, FOUR_THREE_PRECISIONS["Small"])
        if preset == THREE_FOUR_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "three_four_precision", "Small") or "Small"
            return THREE_FOUR_PRECISIONS.get(precision, THREE_FOUR_PRECISIONS["Small"])
        if is_game_draw_preset(preset):
            part = self._current_game_draw_part(preset)
            size = game_draw_part_size(preset, part)
            if size is not None:
                return size
        if preset == CUSTOM_CLOTHING_PRESET_NAME:
            part = self._custom_part_by_name(self.cbo_part.currentText() or self._cfg.custom_clothing_part)
            return (int(part.w), int(part.h))
        return (30, 30)

    def _current_selection_key(self) -> str:
        preset = self.cbo_preset.currentText()
        if preset == ONE_TO_ONE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or self._cfg.one_to_one_precision or "Small"
            return selection_key(preset, precision)
        if preset == SIXTEEN_NINE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "sixteen_nine_precision", "Small") or "Small"
            return selection_key(preset, precision)
        if preset == NINE_SIXTEEN_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "nine_sixteen_precision", "Small") or "Small"
            return selection_key(preset, precision)
        if preset == FOUR_THREE_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "four_three_precision", "Small") or "Small"
            return selection_key(preset, precision)
        if preset == THREE_FOUR_PRESET_NAME:
            precision = self.cbo_precision.currentText() or getattr(self._cfg, "three_four_precision", "Small") or "Small"
            return selection_key(preset, precision)
        if is_game_draw_preset(preset):
            part = self._current_game_draw_part(preset)
            return selection_key(preset, part)
        if preset == CUSTOM_CLOTHING_PRESET_NAME:
            part = self.cbo_part.currentText() or self._cfg.custom_clothing_part or "Part 1"
            return selection_key(preset, part)
        return selection_key(preset, None)

    def _current_selection_key_aliases(self) -> list[str]:
        preset = self.cbo_preset.currentText()
        primary = self._current_selection_key()
        keys = [primary]
        if is_game_draw_preset(preset):
            part = self._current_game_draw_part(preset)
            for old_part, new_part in LEGACY_GAME_DRAW_PART_ALIASES.get(preset, {}).items():
                if new_part == part:
                    keys.append(f"{preset}::{old_part}")
        return list(dict.fromkeys(keys))

    def _lookup_selection_map_value(self, data: dict):
        keys = self._current_selection_key_aliases()
        primary = keys[0]
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            if key != primary and primary not in data:
                data[primary] = value
            return value
        return None

    def _update_variant_ui_visibility(self) -> None:
        preset = self.cbo_preset.currentText()
        is_precision = preset in ASPECT_PRESET_NAMES
        is_game = is_game_draw_preset(preset)
        is_custom = preset == CUSTOM_CLOTHING_PRESET_NAME

        self.lbl_precision.setVisible(is_precision)
        self.cbo_precision.setVisible(is_precision)
        self.lbl_part.setVisible(is_game or is_custom)
        self.cbo_part.setVisible(is_game or is_custom)
        self.btn_edit_custom_part.setVisible(is_custom)
        self.btn_remove_custom_part.setVisible(is_custom)
        self.lbl_part.setText("Custom part:" if is_custom else "Game part:")
        self._update_dress_mapping_ui_visibility()

    def _restore_selection_state(self) -> None:
        sel_key = self._current_selection_key()

        # Canvas areas are restored by exact preset/precision/part key. Do not
        # silently reuse the latest global rectangle for another part; that makes
        # Dress Front/Back/Innerwear and other multi-part presets overwrite each
        # other in practice. The legacy global rect is used only for old configs
        # that have no keyed rects yet.
        rect = self._lookup_selection_map_value(
            self._cfg.last_canvas_rect_by_key,
        )
        if rect is None and not self._cfg.last_canvas_rect_by_key and self._cfg.last_canvas_rect is not None:
            rect = tuple(self._cfg.last_canvas_rect)
            self._cfg.last_canvas_rect_by_key[sel_key] = rect
            self._save_cfg()
        self._canvas_rect = tuple(rect) if rect is not None else None

        img_path = self._lookup_selection_map_value(
            self._cfg.last_image_path_by_key,
        )
        if not img_path and not self._cfg.last_image_path_by_key and self._cfg.last_image_path:
            img_path = self._cfg.last_image_path
            self._cfg.last_image_path_by_key[sel_key] = img_path
            self._save_cfg()

        self._loaded = None
        if img_path:
            p = Path(img_path)
            if p.exists():
                try:
                    w, h = self._selected_preset_wh()
                    grid = self._load_grid_for_path(str(p))
                    self._loaded = LoadedImage(path=str(p), grid=grid)
                    self.lbl_image.setText(f"Loaded: {p} ({grid.w}x{grid.h})")
                except Exception:
                    # If the image can't be loaded anymore, just ignore it.
                    self._loaded = None
                    self.lbl_image.setText("No image loaded")
            else:
                self.lbl_image.setText("No image loaded")
        else:
            self.lbl_image.setText("No image loaded")

        self._refresh_config_view()

    def _on_load(self):
        w, h = self._selected_preset_wh()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not path:
            return
        try:
            grid = self._load_grid_for_path(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Import failed", str(e))
            return

        self._loaded = LoadedImage(path=path, grid=grid)
        self.lbl_image.setText(f"Loaded: {path} ({grid.w}x{grid.h})")

        sel_key = self._current_selection_key()
        self._cfg.last_image_path_by_key[sel_key] = path
        self._cfg.last_image_path = path
        self._cfg.canvas_preset = self.cbo_preset.currentText()
        if self.cbo_preset.currentText() == ONE_TO_ONE_PRESET_NAME:
            self._cfg.one_to_one_precision = self.cbo_precision.currentText() or self._cfg.one_to_one_precision
        if self.cbo_preset.currentText() == SIXTEEN_NINE_PRESET_NAME:
            self._cfg.sixteen_nine_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "sixteen_nine_precision", "Small"
            )
        if self.cbo_preset.currentText() == NINE_SIXTEEN_PRESET_NAME:
            self._cfg.nine_sixteen_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "nine_sixteen_precision", "Small"
            )
        if self.cbo_preset.currentText() == FOUR_THREE_PRESET_NAME:
            self._cfg.four_three_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "four_three_precision", "Small"
            )
        if self.cbo_preset.currentText() == THREE_FOUR_PRESET_NAME:
            self._cfg.three_four_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "three_four_precision", "Small"
            )
        if is_game_draw_preset(self.cbo_preset.currentText()):
            self._remember_current_game_draw_part()
        if self.cbo_preset.currentText() == CUSTOM_CLOTHING_PRESET_NAME:
            self._cfg.custom_clothing_part = self.cbo_part.currentText() or self._cfg.custom_clothing_part
        self._save_cfg()

    def _on_select_canvas(self):
        if self._loaded is None:
            QtWidgets.QMessageBox.information(self, "Select image", "Import an image first.")
            return

        # Build preview pixmap from the resized grid (matches the preset exactly)
        grid = self._loaded.grid
        qimg = QtGui.QImage(grid.w, grid.h, QtGui.QImage.Format.Format_RGB888)
        for y in range(grid.h):
            for x in range(grid.w):
                r, g, b = grid.get(x, y)
                qimg.setPixel(x, y, QtGui.qRgb(r, g, b))
        pix = QtGui.QPixmap.fromImage(qimg)

        self._overlay = RectSelectOverlay(preview_pixmap=pix)
        self._overlay.rectSelected.connect(self._on_canvas_rect_selected)
        self._overlay.cancelled.connect(lambda: None)
        self._overlay.start()

    def _on_canvas_rect_selected(self, r: RectResult):
        # Use selection as canvas rect (we'll refine snapping later)
        self._canvas_rect = (r.x, r.y, r.w, r.h)
        self._remember_target_window_for_canvas()

        sel_key = self._current_selection_key()
        self._cfg.last_canvas_rect_by_key[sel_key] = self._canvas_rect
        self._cfg.last_canvas_rect = self._canvas_rect
        self._save_cfg()
        self._refresh_config_view()

        QtWidgets.QMessageBox.information(
            self,
            "Canvas selected",
            "Canvas area saved.\n\n"
            f"Position: ({r.x}, {r.y})\nSize: {r.w}x{r.h}\n"
            f"Target: {self._target_window_title or 'detected by canvas position'}",
        )

    def _capture_global_button(self, which: str):
        self._capture_click_async(
            "Capture",
            "After closing this dialog, click the button location in-game (the click will NOT press it).",
            lambda res: self._apply_global_button_capture(which, res),
        )

    def _apply_global_button_capture(self, which: str, res: ClickCaptureResult):
        if which == "shades":
            self._cfg.shades_panel_button_pos = res.pos
            self._confirm_capture("shades-panel button", res)
        elif which == "back":
            self._cfg.back_button_pos = res.pos
            self._confirm_capture("back button", res)
        elif which == "paint_tool":
            self._cfg.paint_tool_button_pos = res.pos
            self._confirm_capture("paint tool button", res)
        elif which == "bucket_tool":
            self._cfg.bucket_tool_button_pos = res.pos
            self._confirm_capture("bucket tool button", res)
        elif which == "eraser_tool":
            self._cfg.eraser_tool_button_pos = res.pos
            self._confirm_capture("eraser tool button", res)
        elif which == "eraser_thick_up":
            self._cfg.eraser_thickness_up_button_pos = res.pos
            self._confirm_capture("eraser thickness + button", res)
        self._save_cfg()
        self._refresh_config_view()

    def _on_preset_changed(self, _text: str):
        self._cfg.canvas_preset = self.cbo_preset.currentText()
        self._sync_part_combo_for_preset()
        self._update_variant_ui_visibility()
        self._sync_dress_mapping_ui_from_cfg()
        if self.cbo_preset.currentText() == ONE_TO_ONE_PRESET_NAME:
            self._cfg.one_to_one_precision = self.cbo_precision.currentText() or self._cfg.one_to_one_precision
        if self.cbo_preset.currentText() == SIXTEEN_NINE_PRESET_NAME:
            self._cfg.sixteen_nine_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "sixteen_nine_precision", "Small"
            )
        if self.cbo_preset.currentText() == NINE_SIXTEEN_PRESET_NAME:
            self._cfg.nine_sixteen_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "nine_sixteen_precision", "Small"
            )
        if self.cbo_preset.currentText() == FOUR_THREE_PRESET_NAME:
            self._cfg.four_three_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "four_three_precision", "Small"
            )
        if self.cbo_preset.currentText() == THREE_FOUR_PRESET_NAME:
            self._cfg.three_four_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "three_four_precision", "Small"
            )
        if is_game_draw_preset(self.cbo_preset.currentText()):
            self._remember_current_game_draw_part()
        if self.cbo_preset.currentText() == CUSTOM_CLOTHING_PRESET_NAME:
            self._cfg.custom_clothing_part = self.cbo_part.currentText() or self._cfg.custom_clothing_part
        self._save_cfg()
        self._restore_selection_state()

    def _on_precision_changed(self, _text: str):
        preset = self.cbo_preset.currentText()
        if preset == ONE_TO_ONE_PRESET_NAME:
            self._cfg.one_to_one_precision = self.cbo_precision.currentText() or self._cfg.one_to_one_precision
        elif preset == SIXTEEN_NINE_PRESET_NAME:
            self._cfg.sixteen_nine_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "sixteen_nine_precision", "Small"
            )
        elif preset == NINE_SIXTEEN_PRESET_NAME:
            self._cfg.nine_sixteen_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "nine_sixteen_precision", "Small"
            )
        elif preset == FOUR_THREE_PRESET_NAME:
            self._cfg.four_three_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "four_three_precision", "Small"
            )
        elif preset == THREE_FOUR_PRESET_NAME:
            self._cfg.three_four_precision = self.cbo_precision.currentText() or getattr(
                self._cfg, "three_four_precision", "Small"
            )
        else:
            return
        self._save_cfg()
        self._sync_dress_mapping_ui_from_cfg()
        self._restore_selection_state()

    def _on_part_changed(self, _text: str):
        preset = self.cbo_preset.currentText()
        if is_game_draw_preset(preset):
            self._remember_current_game_draw_part()
        elif preset == CUSTOM_CLOTHING_PRESET_NAME:
            self._cfg.custom_clothing_part = self.cbo_part.currentText() or self._cfg.custom_clothing_part
        else:
            return
        self._save_cfg()
        self._sync_dress_mapping_ui_from_cfg()
        self._restore_selection_state()

    def _on_add_edit_custom_part(self) -> None:
        self._ensure_custom_parts()
        current_name = self.cbo_part.currentText() or self._cfg.custom_clothing_part
        current = self._custom_part_by_name(current_name)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Custom clothing part")
        form = QtWidgets.QFormLayout(dlg)

        name_edit = QtWidgets.QLineEdit(current.name)
        spin_w = QtWidgets.QSpinBox()
        spin_w.setRange(1, 500)
        spin_w.setValue(int(current.w))
        spin_h = QtWidgets.QSpinBox()
        spin_h.setRange(1, 500)
        spin_h.setValue(int(current.h))

        form.addRow("Part name:", name_edit)
        form.addRow("Grid width:", spin_w)
        form.addRow("Grid height:", spin_h)

        hint = QtWidgets.QLabel(
            "Use the exact pixel/grid size from the in-game clothing canvas. "
            "After saving, import the image and select the canvas area for this part."
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        name = name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.information(self, "Invalid part", "Part name cannot be empty.")
            return

        parts = list(self._cfg.custom_clothing_parts)
        existing_idx = next((i for i, p in enumerate(parts) if p.name == current.name), -1)
        conflict_idx = next((i for i, p in enumerate(parts) if p.name == name and i != existing_idx), -1)
        if conflict_idx >= 0:
            QtWidgets.QMessageBox.information(self, "Duplicate part", "A custom part with this name already exists.")
            return

        updated = ClothingPartSpec(name=name, w=int(spin_w.value()), h=int(spin_h.value()))
        if existing_idx >= 0:
            parts[existing_idx] = updated
        else:
            parts.append(updated)

        self._cfg.custom_clothing_parts = parts
        self._cfg.custom_clothing_part = name
        self._cfg.canvas_preset = CUSTOM_CLOTHING_PRESET_NAME
        if self.cbo_preset.currentText() != CUSTOM_CLOTHING_PRESET_NAME:
            self.cbo_preset.setCurrentText(CUSTOM_CLOTHING_PRESET_NAME)
        self._sync_part_combo_for_preset()
        if self.cbo_part.findText(name) >= 0:
            self.cbo_part.setCurrentText(name)
        self._save_cfg()
        self._restore_selection_state()

    def _on_remove_custom_part(self) -> None:
        self._ensure_custom_parts()
        if len(self._cfg.custom_clothing_parts) <= 1:
            QtWidgets.QMessageBox.information(self, "Cannot remove", "Keep at least one custom part.")
            return

        name = self.cbo_part.currentText() or self._cfg.custom_clothing_part
        if (
            QtWidgets.QMessageBox.warning(
                self,
                "Remove custom part",
                f"Remove '{name}' from custom clothing presets?",
                QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            != QtWidgets.QMessageBox.StandardButton.Ok
        ):
            return

        self._cfg.custom_clothing_parts = [p for p in self._cfg.custom_clothing_parts if p.name != name]
        self._ensure_custom_parts()
        self._cfg.custom_clothing_part = self._cfg.custom_clothing_parts[0].name
        self._sync_part_combo_for_preset()
        self._save_cfg()
        self._restore_selection_state()

    def _on_setup_new_color(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New color", "Color name:")
        if not ok or not name.strip():
            return
        name = name.strip()

        # Ensure global buttons exist (shades panel + back). Capture them as part of the wizard.
        self._wizard_ensure_globals_then_continue(name)

    def _wizard_ensure_globals_then_continue(self, color_name: str):
        if self._cfg.shades_panel_button_pos is None:
            self._capture_click_async(
                "Setup new color",
                "Before adding colors, we need the SHADES-PANEL button location.\n\n"
                "After closing this dialog, click the button that opens the shades panel.",
                lambda res: self._wizard_set_global_then_continue(color_name, "shades", res),
            )
            return
        if self._cfg.back_button_pos is None:
            self._capture_click_async(
                "Setup new color",
                "Before adding colors, we need the BACK button location.\n\n"
                "After closing this dialog, click the back button (returns to main colors).",
                lambda res: self._wizard_set_global_then_continue(color_name, "back", res),
            )
            return

        self._wizard_capture_main_color(color_name)

    def _wizard_set_global_then_continue(self, color_name: str, which: str, res: ClickCaptureResult):
        if which == "shades":
            self._cfg.shades_panel_button_pos = res.pos
            self._confirm_capture("shades-panel button", res)
        elif which == "back":
            self._cfg.back_button_pos = res.pos
            self._confirm_capture("back button", res)
        self._save_cfg()
        self._refresh_config_view()
        # Continue capturing any remaining globals, then proceed.
        self._wizard_ensure_globals_then_continue(color_name)

    def _wizard_capture_main_color(self, name: str):
        self._capture_click_async(
            "Setup new color",
            "Step 1: Click the MAIN color button in the main palette.",
            lambda res: self._wizard_after_main_capture(name, res),
        )

    def _wizard_after_main_capture(self, name: str, res: ClickCaptureResult):
        self._confirm_capture(f"main color '{name}'", res)
        main = MainColor(name=name, pos=res.pos, rgb=res.rgb, shades=[])
        self._cfg.main_colors.append(main)
        self._save_cfg()
        self._refresh_config_view()

        try:
            open_shades_panel_for_main(self._cfg, self._painter_options_from_cfg(), main)
            self.statusBar().showMessage(
                f"Selected main color '{name}' and opened shades panel with paint-click logic.",
                5000,
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Palette click check failed",
                "The main color was saved, but the app could not auto-open the shades panel "
                "with the painting click sequence.\n\n"
                f"Error: {e}\n\n"
                "Open the shades panel manually, then continue capturing shades.",
            )

        QtWidgets.QMessageBox.information(
            self,
            "Setup new color",
            "Step 2: The app will use the same click sequence as painting when testing each shade.\n"
            "Click each shade button location one-by-one.\n"
            "When you are done, click 'Finish'.",
        )

        # Collect shade picks until user clicks Finish.
        # Important: keep this NON-MODAL so you can freely interact with the game.
        shades: list[ShadeButton] = []
        self._shade_capture_active = True

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Capture shades — {name}")
        dlg.setModal(False)
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint)

        v = QtWidgets.QVBoxLayout(dlg)
        lbl = QtWidgets.QLabel(
            "Click 'Capture next shade', then click the shade button location in the game.\n"
            "Repeat until done, then click Finish." 
        )
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        lst = QtWidgets.QListWidget()
        v.addWidget(lst)

        row = QtWidgets.QHBoxLayout()
        btn_capture = QtWidgets.QPushButton("Capture next shade")
        btn_finish = QtWidgets.QPushButton("Finish")
        row.addWidget(btn_capture)
        row.addWidget(btn_finish)
        v.addLayout(row)

        def add_shade_capture(res2: ClickCaptureResult):
            if not getattr(self, "_shade_capture_active", False):
                return
            shade_name = f"shade-{len(shades)+1}"
            sh = ShadeButton(name=shade_name, pos=res2.pos, rgb=res2.rgb)
            shades.append(sh)
            lst.addItem(f"{shade_name} @ {res2.pos} rgb={res2.rgb}")
            click_error: Exception | None = None
            dlg_was_visible = False
            try:
                dlg_was_visible = dlg.isVisible()
                if dlg_was_visible:
                    dlg.hide()
                    QtWidgets.QApplication.processEvents()
                    time.sleep(0.12)
                select_shade_for_painting(self._cfg, self._painter_options_from_cfg(), main, sh)
            except Exception as e:
                click_error = e
            finally:
                if dlg_was_visible and getattr(self, "_shade_capture_active", False):
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()

            if click_error is None:
                self.statusBar().showMessage(
                    f"Captured and paint-tested {shade_name} at {res2.pos} rgb={res2.rgb}",
                    5000,
                )
            else:
                self.statusBar().showMessage(f"Captured {shade_name}, but paint-test failed: {click_error}", 7000)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Shade click check failed",
                    f"Saved {shade_name}, but selecting it with the painting click sequence failed.\n\n"
                    f"Error: {click_error}",
                )

        def capture_one():
            if not getattr(self, "_shade_capture_active", False):
                return

            ov = PointSelectOverlay(instruction="Click the SHADE button location (ESC/right-click to cancel)")
            self._point_overlay = ov

            def on_sel(p: PointResult):
                rgb = get_screen_pixel_rgb(int(p.x), int(p.y))
                r = ClickCaptureResult(pos=(int(p.x), int(p.y)), rgb=rgb)
                self._run_on_ui_thread(lambda: add_shade_capture(r))

            def on_cancel():
                self.statusBar().showMessage("Shade capture cancelled", 3000)

            ov.pointSelected.connect(on_sel)
            ov.cancelled.connect(on_cancel)
            ov.start()

        def finish():
            self._shade_capture_active = False
            # Save shades into matching main color
            for mc in self._cfg.main_colors:
                if mc.name == name and mc.pos == main.pos:
                    mc.shades = shades
                    break
            self._save_cfg()
            self._refresh_config_view()
            dlg.close()

            QtWidgets.QMessageBox.information(
                self,
                "Shades saved",
                f"Saved {len(shades)} shades for '{name}'.",
            )

        def on_close(_event):
            # If user closes the window, stop capturing to avoid orphan overlays.
            self._shade_capture_active = False

        dlg.closeEvent = on_close  # type: ignore[method-assign]

        btn_capture.clicked.connect(capture_one)
        btn_finish.clicked.connect(finish)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_remove_selected_color(self):
        idx = self.lst_colors.currentRow()
        if idx < 0:
            return
        if idx >= len(self._cfg.main_colors):
            return
        name = self._cfg.main_colors[idx].name
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Remove",
                f"Remove color '{name}'?",
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return
        self._cfg.main_colors.pop(idx)
        self._save_cfg()
        self._refresh_config_view()

    def _on_fix_swap_rb(self):
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Swap R/B channels?",
                "If your captured palette colors look wrong (e.g. yellows behave like blues),\n"
                "you may have captured colors when the sampler had swapped channels.\n\n"
                "This will swap the Red and Blue channels for ALL saved main/shade colors.\n\n"
                "Proceed?",
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return

        def swap(rgb):
            r, g, b = rgb
            return (b, g, r)

        for mc in self._cfg.main_colors:
            mc.rgb = swap(mc.rgb)
            for sh in mc.shades:
                sh.rgb = swap(sh.rgb)

        self._save_cfg()
        self._refresh_config_view()
        QtWidgets.QMessageBox.information(self, "Done", "Swapped R/B for saved colors.")

    def _on_paint(self):
        if self._loaded is None:
            QtWidgets.QMessageBox.information(self, "Missing", "Import an image first.")
            return
        if self._canvas_rect is None:
            QtWidgets.QMessageBox.information(self, "Missing", "Select canvas area first.")
            return

        if (
            not self._cfg.main_colors
            or self._cfg.shades_panel_button_pos is None
            or self._cfg.back_button_pos is None
        ):
            QtWidgets.QMessageBox.information(
                self,
                "Missing configuration",
                "Set up your colors and the global buttons first.\n\n"
                "Required: at least one main color with shades, plus the shades-panel and back buttons.",
            )
            return

        # Safety prompt
        if (
            QtWidgets.QMessageBox.warning(
                self,
                "About to paint",
                "This will control your mouse and click in-game.\n"
                "Make sure the game is focused and your palette/canvas is visible.\n\n"
                "PyAutoGUI failsafe: move mouse to top-left to abort.",
                QtWidgets.QMessageBox.StandardButton.Ok
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            != QtWidgets.QMessageBox.StandardButton.Ok
        ):
            return

        if not self._paint_countdown(seconds=3):
            return

        if not self._prepare_automation_window():
            return
        self._start_paint_worker(resume=False)

    def _on_erase(self) -> None:
        if self._canvas_rect is None:
            QtWidgets.QMessageBox.information(self, "Missing", "Select canvas area first.")
            return

        if self._cfg.eraser_tool_button_pos is None or self._cfg.eraser_thickness_up_button_pos is None:
            QtWidgets.QMessageBox.information(
                self,
                "Missing configuration",
                "Capture the eraser tool button and the eraser thickness + button first (Color configuration tab).",
            )
            return

        if (
            QtWidgets.QMessageBox.warning(
                self,
                "About to erase",
                "This will control your mouse and erase the entire selected canvas in-game.\n"
                "Make sure the game is focused and the canvas is visible.\n\n"
                "PyAutoGUI failsafe: move mouse to top-left to abort.",
                QtWidgets.QMessageBox.StandardButton.Ok
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            != QtWidgets.QMessageBox.StandardButton.Ok
        ):
            return

        if not self._paint_countdown(seconds=3):
            return

        # Erasing invalidates any paused paint session.
        self._reset_paint_session()
        if not self._prepare_automation_window():
            return
        self._start_erase_worker()

    def _on_erase_done(self) -> None:
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        self.statusBar().showMessage("Erase complete", 4000)

    def _on_erase_stopped(self, msg: str) -> None:
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        self.statusBar().showMessage(msg or "Erase stopped", 4000)

    def _on_erase_error(self, msg: str) -> None:
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        QtWidgets.QMessageBox.warning(self, "Erase failed", f"Erase hit an error.\n\nError: {msg}")

    def _start_erase_worker(self) -> None:
        if self._canvas_rect is None:
            return

        self.btn_paint.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._stop_flag = False
        self._stop_reason = None

        # Prefer the canvas target window over whatever happens to be foreground.
        self._game_window_rect = self._window_rect(self._target_hwnd) or self._capture_foreground_window_rect()
        self._start_esc_listener()

        if bool(getattr(self._cfg, "status_overlay_enabled", True)) and not self._hidden_for_automation:
            try:
                ov = self._ensure_status_overlay()
                if self._game_window_rect is not None:
                    ov.set_anchor_rect(self._game_window_rect)
                if not ov.isVisible():
                    ov.start()
                ov.set_status("Starting erase…")
            except Exception:
                pass

        signals = WorkerSignals()
        qc = QtCore.Qt.ConnectionType.QueuedConnection
        signals.status.connect(self._on_worker_status, qc)
        signals.finished.connect(self._on_erase_done, qc)
        signals.error.connect(self._on_erase_error, qc)
        signals.stopped.connect(self._on_erase_stopped, qc)

        def work():
            try:
                opts = self._painter_options_from_cfg()

                grid_w, grid_h = self._selected_preset_wh()

                def status_cb(msg: str) -> None:
                    try:
                        signals.status.emit(str(msg))
                    except Exception:
                        pass

                erase_canvas(
                    cfg=self._cfg,
                    canvas_rect=self._canvas_rect,
                    grid_w=int(grid_w),
                    grid_h=int(grid_h),
                    options=opts,
                    should_stop=lambda: self._stop_flag,
                    status_cb=status_cb,
                )

                if self._stop_flag:
                    signals.stopped.emit("Erase stopped")
                    return

                signals.finished.emit()
            except Exception as e:
                signals.error.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def _paint_countdown(self, seconds: int = 3) -> bool:
        """Modal countdown before starting automation. Returns False if cancelled."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Starting")
        dlg.setModal(True)

        v = QtWidgets.QVBoxLayout(dlg)
        lbl = QtWidgets.QLabel()
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        v.addWidget(btn_cancel)

        remaining = {"n": max(0, int(seconds))}

        def update_text():
            n = remaining["n"]
            if n <= 0:
                lbl.setText("Starting now…")
            else:
                lbl.setText(
                    "Switch to the game window now.\n\n"
                    f"Starting in {n}…\n\n"
                    "Failsafe: move mouse to top-left to abort."
                )

        timer = QtCore.QTimer(dlg)

        def tick():
            remaining["n"] -= 1
            update_text()
            if remaining["n"] <= 0:
                timer.stop()
                dlg.accept()

        def cancel():
            timer.stop()
            dlg.reject()

        btn_cancel.clicked.connect(cancel)

        update_text()
        timer.timeout.connect(tick)
        timer.start(1000)

        return dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def _on_stop(self):
        # Manual stop is a cancel.
        self._stop_reason = "stop"
        self._stop_flag = True
        self._stop_esc_listener()
    def _current_paint_session_sig(self) -> Optional[tuple]:
        if self._loaded is None or self._canvas_rect is None:
            return None
        return (
            self._loaded.path,
            self._loaded.grid.w,
            self._loaded.grid.h,
            tuple(self._canvas_rect),
            self._current_selection_key(),
            str(getattr(self._cfg, "paint_mode", "row")),
        )

    def _reset_paint_session(self) -> None:
        self._paint_total = 0
        self._paint_done.clear()
        self._paint_paused = False
        self._paint_session_sig = None
        self._paint_base_bucket_key = None
        self._paint_base_bucket_rgb = None
        self.btn_resume.setEnabled(False)

    def _on_progress(self, x: int, y: int, total: int):
        # Progress callbacks can arrive out of order (Paint-by-Color) and can
        # repeat due to verification repaints. Track unique completed cells.
        if self._loaded is None:
            return
        if not self._loaded.grid.should_paint(int(x), int(y)):
            return
        if total > 0:
            self._paint_total = int(total)
        key = (int(x), int(y))
        if key not in self._paint_done:
            self._paint_done.add(key)

        denom = max(1, int(self._paint_total) or int(total) or 1)
        pct = int((len(self._paint_done) / denom) * 100)
        self.progress.setValue(max(0, min(100, pct)))

        # Replica canvas progress (best-effort)
        if bool(getattr(self._cfg, "status_overlay_enabled", True)):
            if self._hidden_for_automation:
                return
            try:
                ov = self._ensure_status_overlay()
                if self._game_window_rect is not None:
                    ov.set_anchor_rect(self._game_window_rect)
                if not ov.isVisible():
                    ov.start()
                ov.mark_painted(int(x), int(y))
            except Exception:
                pass

    def _on_paint_done(self):
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setValue(100)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        self._reset_paint_session()

    def _on_paint_paused(self, msg: str) -> None:
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(True)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        self._paint_paused = True
        self.statusBar().showMessage(msg or "Paused", 4000)

    def _on_paint_stopped(self, msg: str) -> None:
        self.btn_paint.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()
        self._reset_paint_session()
        self.statusBar().showMessage(msg or "Stopped", 4000)

    def _on_paint_error(self, msg: str):
        self.btn_paint.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_erase.setEnabled(True)
        self._stop_esc_listener()
        self._hide_status_overlay()
        self._restore_main_window_after_automation()

        # Keep the session state so the user can tweak settings and resume.
        self._paint_paused = True
        self.btn_resume.setEnabled(True)
        QtWidgets.QMessageBox.warning(
            self,
            "Paint paused",
            "Painting hit an error and has been paused.\n\n"
            "You can tweak timing/verification settings and press Resume to continue from the last completed step.\n\n"
            f"Error: {msg}",
        )

    def _start_paint_worker(self, resume: bool) -> None:
        if self._loaded is None or self._canvas_rect is None:
            return

        total = int(getattr(self._loaded.grid, "paint_count", self._loaded.grid.w * self._loaded.grid.h))
        if not resume:
            self._reset_paint_session()
            self._paint_total = total
            self._paint_session_sig = self._current_paint_session_sig()
        else:
            # Validate that the session hasn't changed.
            cur_sig = self._current_paint_session_sig()
            if self._paint_session_sig is None or cur_sig != self._paint_session_sig:
                QtWidgets.QMessageBox.information(
                    self,
                    "Can't resume",
                    "The image/canvas/preset changed since the last run.\n\nStart a new paint instead.",
                )
                self._reset_paint_session()
                return

        self.btn_paint.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_erase.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._stop_flag = False
        self._stop_reason = None

        # Prefer the canvas target window over whatever happens to be foreground.
        self._game_window_rect = self._window_rect(self._target_hwnd) or self._capture_foreground_window_rect()
        self._start_esc_listener()

        # Prepare the in-game status overlay (UI thread only).
        if bool(getattr(self._cfg, "status_overlay_enabled", True)) and not self._hidden_for_automation:
            try:
                ov = self._ensure_status_overlay()
                if self._game_window_rect is not None:
                    ov.set_anchor_rect(self._game_window_rect)
                ov.set_grid(self._loaded.grid.w, self._loaded.grid.h, self._loaded.grid.pixels)
                if resume and self._paint_done:
                    for (xx, yy) in list(self._paint_done):
                        ov.mark_painted(int(xx), int(yy))
                if not ov.isVisible():
                    ov.start()
                ov.set_status("Starting…")
            except Exception:
                pass

        signals = WorkerSignals()
        qc = QtCore.Qt.ConnectionType.QueuedConnection
        signals.progress.connect(self._on_worker_progress, qc)
        signals.status.connect(self._on_worker_status, qc)
        signals.verify_cell.connect(self._on_worker_verify_cell, qc)
        signals.bucket_base.connect(self._on_worker_bucket_base, qc)
        signals.finished.connect(self._on_paint_done, qc)
        signals.error.connect(self._on_paint_error, qc)
        signals.paused.connect(self._on_paint_paused, qc)
        signals.stopped.connect(self._on_paint_stopped, qc)

        def work():
            try:
                opts = self._painter_options_from_cfg()

                def get_pixel(x: int, y: int):
                    return self._loaded.grid.get(x, y)

                skip_fn = (lambda x, y: (int(x), int(y)) in self._paint_done) if resume else None
                def should_skip_pixel(x: int, y: int) -> bool:
                    if not self._loaded.grid.should_paint(int(x), int(y)):
                        return True
                    return bool(skip_fn and skip_fn(int(x), int(y)))

                def status_cb(msg: str) -> None:
                    try:
                        signals.status.emit(str(msg))
                    except Exception:
                        pass

                def verify_cb(pt: Optional[Tuple[int, int]]) -> None:
                    try:
                        if pt is None:
                            signals.verify_cell.emit(-1, -1)
                        else:
                            signals.verify_cell.emit(int(pt[0]), int(pt[1]))
                    except Exception:
                        pass

                def bucket_base_cb(main_name: str, mx: int, my: int, sx: int, sy: int, r: int, g: int, b: int) -> None:
                    try:
                        signals.bucket_base.emit(
                            str(main_name),
                            int(mx),
                            int(my),
                            int(sx),
                            int(sy),
                            int(r),
                            int(g),
                            int(b),
                        )
                    except Exception:
                        pass

                paint_grid(
                    cfg=self._cfg,
                    canvas_rect=self._canvas_rect,
                    grid_w=self._loaded.grid.w,
                    grid_h=self._loaded.grid.h,
                    get_pixel=get_pixel,
                    options=opts,
                    paint_mode=self._cfg.paint_mode,
                    skip=should_skip_pixel,
                    allow_bucket_fill=(not resume),
                    allow_region_bucket_fill=(not resume) or (self._paint_base_bucket_key is not None),
                    resume_base_bucket_key=(
                        (self._paint_base_bucket_key[0], self._paint_base_bucket_key[1])
                        if resume and self._paint_base_bucket_key is not None
                        else None
                    ),
                    resume_base_bucket_rgb=(
                        self._paint_base_bucket_rgb if resume and self._paint_base_bucket_rgb is not None else None
                    ),
                    bucket_base_cb=bucket_base_cb,
                    progress_cb=lambda x, y: signals.progress.emit(x, y),
                    should_stop=lambda: self._stop_flag,
                    status_cb=status_cb,
                    verify_cb=verify_cb,
                )

                if self._stop_flag:
                    if self._stop_reason == "pause":
                        signals.paused.emit("Paused (ESC)")
                        return
                    if self._stop_reason == "stop":
                        signals.stopped.emit("Stopped")
                        return

                signals.finished.emit()
            except Exception as e:
                signals.error.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_resume(self) -> None:
        if not self._paint_paused:
            return
        if self._loaded is None or self._canvas_rect is None:
            return
        if not self._paint_done:
            return

        # Short countdown to refocus the game window.
        if not self._paint_countdown(seconds=2):
            return

        self._paint_paused = False
        if not self._prepare_automation_window():
            return
        self._start_paint_worker(resume=True)


def run():
    # Qt on Windows can emit a scary-but-harmless DPI awareness warning on some setups.
    # Suppress that specific category to keep console output clean.
    rules = os.environ.get("QT_LOGGING_RULES", "")
    if "qt.qpa.window=false" not in rules:
        os.environ["QT_LOGGING_RULES"] = (rules + (";" if rules else "") + "qt.qpa.window=false").strip(";")

    app = QtWidgets.QApplication([])
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    w = MainWindow()
    w.resize(900, 650)
    w.show()
    app.exec()
