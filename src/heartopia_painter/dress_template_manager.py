from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFilter
from PySide6 import QtCore, QtGui, QtWidgets

from .artpia_templates import find_artpia_part_template, save_artpia_template_files
from .app_icon import load_app_icon
from .game_draw_data import GAME_DRAW_PARTS_BY_PRESET
from .image_processing import ImagePrepOptions, PixelGrid, load_and_resize_to_grid


RGB = Tuple[int, int, int]
SettingKey = Tuple[str, str]

FALLBACK_CLOTHING_TYPES: dict[str, dict[str, Tuple[int, int]]] = {
    "Dress": {
        "Front": (102, 154),
        "Back": (76, 154),
        "Innerwear": (168, 102),
    },
    "T-Shirt": {
        "Front": (64, 80),
        "Back": (64, 80),
        "Left Sleeve": (64, 48),
        "Right Sleeve": (64, 48),
    },
    "Tank Top": {
        "Front": (64, 64),
        "Back": (64, 64),
    },
}

CLOTHING_TYPES: dict[str, dict[str, Tuple[int, int]]] = GAME_DRAW_PARTS_BY_PRESET or FALLBACK_CLOTHING_TYPES

PART_MASKS: dict[str, dict[str, str]] = {
    clothing: {part: "none" for part in parts}
    for clothing, parts in CLOTHING_TYPES.items()
}


@dataclass
class PartSettings:
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass
class MaskCalibration:
    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass
class SkeletonMapping:
    enabled: bool = False
    strength: float = 1.0
    edge_padding: int = 0


@dataclass
class PresetUiSettings:
    fit_text: str = "Cover / Fill part"
    auto_crop: bool = True
    clip_mask: bool = False


def _safe_stem(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "image"


def _checkerboard(size: Tuple[int, int], cell: int = 10) -> QtGui.QPixmap:
    w, h = size
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtGui.QColor(250, 245, 232))
    painter = QtGui.QPainter(pix)
    a = QtGui.QColor(232, 222, 202)
    b = QtGui.QColor(250, 245, 232)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            painter.fillRect(x, y, cell, cell, a if ((x // cell) + (y // cell)) % 2 else b)
    painter.end()
    return pix


def _largest_component_bbox_from_predicate(img: Image.Image, predicate) -> tuple[int, int, int, int] | None:
    rgb = img.convert("RGB")
    w, h = rgb.size
    pix = rgb.load()
    visited = bytearray(w * h)
    best_area = 0
    best_bbox: tuple[int, int, int, int] | None = None

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if visited[idx]:
                continue

            r, g, b = pix[x, y]
            if not predicate(r, g, b):
                visited[idx] = 1
                continue

            q: deque[tuple[int, int]] = deque([(x, y)])
            visited[idx] = 1
            area = 0
            min_x = max_x = x
            min_y = max_y = y

            while q:
                cx, cy = q.popleft()
                area += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)

                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    nidx = ny * w + nx
                    if visited[nidx]:
                        continue
                    nr, ng, nb = pix[nx, ny]
                    visited[nidx] = 1
                    if predicate(nr, ng, nb):
                        q.append((nx, ny))

            if area > best_area:
                best_area = area
                best_bbox = (min_x, min_y, max_x + 1, max_y + 1)

    return best_bbox


def _filter_mask_components(mask: Image.Image, min_area: int = 120) -> Image.Image:
    src = mask.convert("L")
    w, h = src.size
    pix = src.load()
    visited = bytearray(w * h)
    out = Image.new("L", (w, h), 0)
    out_pix = out.load()

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if visited[idx] or pix[x, y] == 0:
                visited[idx] = 1
                continue

            q: deque[tuple[int, int]] = deque([(x, y)])
            visited[idx] = 1
            points: list[tuple[int, int]] = []
            min_x = max_x = x
            min_y = max_y = y

            while q:
                cx, cy = q.popleft()
                points.append((cx, cy))
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)

                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    nidx = ny * w + nx
                    if not visited[nidx] and pix[nx, ny] > 0:
                        visited[nidx] = 1
                        q.append((nx, ny))

            area = len(points)
            comp_w = max_x - min_x + 1
            comp_h = max_y - min_y + 1
            if area >= min_area and comp_w >= 10 and comp_h >= 10:
                for px, py in points:
                    out_pix[px, py] = 255

    return out


def _scanline_fill_outline(outline: Image.Image) -> Image.Image:
    solid = outline.convert("L").filter(ImageFilter.MaxFilter(5))
    w, h = solid.size
    pix = solid.load()
    filled = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(filled)

    for y in range(h):
        runs: list[tuple[int, int]] = []
        in_run = False
        start = 0
        for x in range(w):
            active = pix[x, y] > 0
            if active and not in_run:
                start = x
                in_run = True
            if (not active or x == w - 1) and in_run:
                end = x - 1 if not active else x
                if end - start >= 2:
                    runs.append((start, end))
                in_run = False

        merged: list[tuple[int, int]] = []
        for left, right in runs:
            if merged and left - merged[-1][1] <= 5:
                merged[-1] = (merged[-1][0], right)
            else:
                merged.append((left, right))

        if len(merged) < 2:
            continue

        if len(merged) % 2 == 0:
            pairs = zip(merged[0::2], merged[1::2])
        else:
            pairs = [(merged[0], merged[-1])]

        for left, right in pairs:
            draw.line((left[0], y, right[1], y), fill=255)

    return filled.filter(ImageFilter.MaxFilter(3))


def _extract_game_mask_from_screenshot(path: Path, target_size: tuple[int, int]) -> tuple[Image.Image, str]:
    src = Image.open(path).convert("RGB")

    def is_canvas_orange(r: int, g: int, b: int) -> bool:
        return r >= 215 and g >= 140 and b <= 190 and (r - g) >= 15 and (g - b) >= 10

    bbox = _largest_component_bbox_from_predicate(src, is_canvas_orange)
    if bbox is None:
        raise RuntimeError("Could not find the orange drawing canvas in this screenshot.")

    crop = src.crop(bbox)
    w, h = crop.size
    pix = crop.load()
    outline = Image.new("L", (w, h), 0)
    outline_pix = outline.load()

    # The in-game outline is not always pure white; imported images tint it down
    # to light neutral gray. This threshold intentionally targets low-saturation
    # bright linework instead of only RGB(255,255,255).
    for y in range(h):
        for x in range(w):
            r, g, b = pix[x, y]
            if r >= 178 and g >= 178 and b >= 165 and max(r, g, b) - min(r, g, b) <= 42:
                outline_pix[x, y] = 255

    outline = _filter_mask_components(outline)
    if outline.getbbox() is None:
        raise RuntimeError("Could not isolate the in-game white outline from this screenshot.")

    filled = _scanline_fill_outline(outline)
    mask = filled.resize(target_size, Image.Resampling.LANCZOS).point(lambda v: 255 if v >= 96 else 0)
    coverage = sum(1 for value in mask.getdata() if value > 0) / max(1, target_size[0] * target_size[1])
    if coverage < 0.02 or coverage > 0.95:
        raise RuntimeError(
            f"Extracted mask coverage looks invalid ({coverage:.1%}). "
            "Use a screenshot of the blank game template without red marks or extra overlays."
        )

    info = f"canvas crop={crop.size[0]}x{crop.size[1]}, mask coverage={coverage:.1%}"
    return mask, info


class InteractivePreviewLabel(QtWidgets.QLabel):
    dragged = QtCore.Signal(int, int)
    wheelScaled = QtCore.Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._last_pos: QtCore.QPoint | None = None
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._last_pos = event.position().toPoint()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._last_pos is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            delta = pos - self._last_pos
            self._last_pos = pos
            self.dragged.emit(int(delta.x()), int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._last_pos = None
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        step = 5 if event.angleDelta().y() > 0 else -5
        self.wheelScaled.emit(step)
        event.accept()


class DressTemplateManager(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Heartopia Clothing Template Manager")
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(1220, 840)

        self.current_preset: str = next(iter(CLOTHING_TYPES))
        self.source_path: Path | None = None
        self.source_paths_by_key: Dict[SettingKey, Path] = {}
        self.mask_paths_by_key: Dict[SettingKey, Path] = {}
        self.output_dir: Path = Path.home() / "Downloads"
        self.background_rgb: RGB = (255, 255, 255)
        self.preset_ui_settings: Dict[str, PresetUiSettings] = {
            clothing: PresetUiSettings()
            for clothing in CLOTHING_TYPES
        }
        self.part_settings: Dict[SettingKey, PartSettings] = {
            (cloth, part): PartSettings()
            for cloth, parts in CLOTHING_TYPES.items()
            for part in parts
        }
        self.mask_calibrations: Dict[SettingKey, MaskCalibration] = {
            (cloth, part): MaskCalibration()
            for cloth, parts in CLOTHING_TYPES.items()
            for part in parts
        }
        self.skeleton_mappings: Dict[SettingKey, SkeletonMapping] = {
            (cloth, part): SkeletonMapping()
            for cloth, parts in CLOTHING_TYPES.items()
            for part in parts
        }
        self._current_grid: PixelGrid | None = None
        self.thumb_labels: Dict[str, QtWidgets.QLabel] = {}
        self.preset_buttons: Dict[str, QtWidgets.QToolButton] = {}

        self._build_ui()
        self._sync_preset_view()
        self._sync_part_combo()
        self._sync_part_controls()
        self._update_preview()

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)

        self.setStyleSheet(
            """
            QMainWindow { background: #f7f2e9; }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #d8c7ad;
                border-radius: 10px;
                margin-top: 12px;
                background: #fffaf1;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #6f5138;
            }
            QPushButton, QToolButton {
                border: 1px solid #cdb590;
                border-radius: 8px;
                padding: 7px 10px;
                background: #fff7e8;
            }
            QPushButton:hover, QToolButton:hover { background: #ffe7b6; }
            QToolButton:checked {
                background: #ffc94b;
                border: 2px solid #a97422;
                color: #4a2d0d;
                font-weight: 700;
            }
            QComboBox, QSpinBox {
                padding: 4px;
                border: 1px solid #cdb590;
                border-radius: 6px;
                background: white;
            }
            """
        )

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Heartopia Clothing Template Manager")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #5a412d;")
        subtitle = QtWidgets.QLabel("Simple flow: Preset -> Part/Image -> Position -> Export")
        subtitle.setStyleSheet("color: #8c735b;")
        title_box = QtWidgets.QVBoxLayout()
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.lbl_active_preset = QtWidgets.QLabel("")
        self.lbl_active_preset.setWordWrap(True)
        self.lbl_active_preset.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.lbl_active_preset, 1)
        layout.addLayout(header)

        preset_box = QtWidgets.QGroupBox("Step 1 - Choose preset")
        preset_box_layout = QtWidgets.QVBoxLayout(preset_box)
        preset_scroll = QtWidgets.QScrollArea()
        preset_scroll.setWidgetResizable(True)
        preset_scroll.setMaximumHeight(230)
        preset_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        preset_inner = QtWidgets.QWidget()
        preset_layout = QtWidgets.QGridLayout(preset_inner)
        preset_layout.setSpacing(8)
        self.preset_button_group = QtWidgets.QButtonGroup(self)
        self.preset_button_group.setExclusive(True)
        for idx, (clothing, parts) in enumerate(CLOTHING_TYPES.items()):
            sample_size = next(iter(parts.values()))
            button = QtWidgets.QToolButton()
            button.setText(f"{clothing}\n{len(parts)} parts\n{sample_size[0]}x{sample_size[1]} base")
            button.setCheckable(True)
            button.setMinimumSize(170, 76)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(lambda _checked=False, c=clothing: self._select_preset(c))
            self.preset_button_group.addButton(button)
            self.preset_buttons[clothing] = button
            preset_layout.addWidget(button, idx // 4, idx % 4)
        preset_layout.setColumnStretch(4, 1)
        preset_scroll.setWidget(preset_inner)
        preset_box_layout.addWidget(preset_scroll)
        layout.addWidget(preset_box)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)
        layout.addLayout(body, 1)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_scroll.setMinimumWidth(420)
        left_scroll.setMaximumWidth(500)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setSpacing(10)
        left_scroll.setWidget(left)
        body.addWidget(left_scroll, 0)

        part_box = QtWidgets.QGroupBox("Step 2 - Pick part and image")
        part_layout = QtWidgets.QVBoxLayout(part_box)
        part_form = QtWidgets.QFormLayout()
        self.lbl_selected_preset_value = QtWidgets.QLabel("")
        self.cbo_part = QtWidgets.QComboBox()
        part_form.addRow("Preset", self.lbl_selected_preset_value)
        part_form.addRow("Part", self.cbo_part)
        part_layout.addLayout(part_form)

        self.btn_open = QtWidgets.QPushButton("Import image for this part...")
        self.btn_open.setMinimumHeight(38)
        self.btn_use_for_type = QtWidgets.QPushButton("Use this image for all parts in preset")
        self.btn_clear_part_source = QtWidgets.QPushButton("Clear this part image")
        part_layout.addWidget(self.btn_open)
        part_layout.addWidget(self.btn_use_for_type)
        part_layout.addWidget(self.btn_clear_part_source)
        self.lbl_source = QtWidgets.QLabel("No source image for current part")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_source.setStyleSheet("color: #6f6254;")
        part_layout.addWidget(self.lbl_source)
        left_layout.addWidget(part_box)

        self.settings_box = QtWidgets.QGroupBox("Step 3 - Fit and position")
        fit_layout = QtWidgets.QVBoxLayout(self.settings_box)
        fit_form = QtWidgets.QFormLayout()
        self.cbo_fit = QtWidgets.QComboBox()
        self.cbo_fit.addItems(["Cover / Fill part", "Contain full image", "Stretch exact"])
        self.chk_auto_crop = QtWidgets.QCheckBox("Auto-crop empty border")
        self.chk_auto_crop.setChecked(True)
        self.btn_bg = QtWidgets.QPushButton("Background: #FFFFFF")

        self.spin_scale = QtWidgets.QSpinBox()
        self.spin_scale.setRange(25, 300)
        self.spin_scale.setSingleStep(5)
        self.spin_scale.setSuffix(" %")
        self.spin_offset_x = QtWidgets.QSpinBox()
        self.spin_offset_x.setRange(-500, 500)
        self.spin_offset_x.setSuffix(" px")
        self.spin_offset_y = QtWidgets.QSpinBox()
        self.spin_offset_y.setRange(-500, 500)
        self.spin_offset_y.setSuffix(" px")

        fit_form.addRow("Fit", self.cbo_fit)
        fit_form.addRow("Image scale", self.spin_scale)
        fit_form.addRow("Move X", self.spin_offset_x)
        fit_form.addRow("Move Y", self.spin_offset_y)
        fit_layout.addLayout(fit_form)
        fit_layout.addWidget(self.chk_auto_crop)
        fit_layout.addWidget(self.btn_bg)

        fit_actions = QtWidgets.QHBoxLayout()
        self.btn_reset_part = QtWidgets.QPushButton("Reset part")
        self.btn_copy_to_all_parts = QtWidgets.QPushButton("Copy position to all parts")
        self.btn_copy_to_all = QtWidgets.QPushButton("Copy to every preset")
        self.btn_copy_to_all.setVisible(False)
        fit_actions.addWidget(self.btn_reset_part)
        fit_actions.addWidget(self.btn_copy_to_all_parts)
        fit_layout.addLayout(fit_actions)
        tip = QtWidgets.QLabel("Tip: drag the preview to move the image. Use mouse wheel on preview to resize.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #8c735b;")
        fit_layout.addWidget(tip)
        left_layout.addWidget(self.settings_box)

        advanced_box = QtWidgets.QGroupBox("Optional - Mask, skeleton and calibration")
        advanced_layout = QtWidgets.QVBoxLayout(advanced_box)
        advanced_tabs = QtWidgets.QTabWidget()

        mask_tab = QtWidgets.QWidget()
        mask_layout = QtWidgets.QVBoxLayout(mask_tab)
        self.chk_clip_mask = QtWidgets.QCheckBox("Clip to mask / transparent shape")
        self.chk_clip_mask.setChecked(False)
        self.btn_export_artpia_guide_current = QtWidgets.QPushButton("Export Art-pia GPT guide for current part")
        self.btn_export_artpia_guide_type = QtWidgets.QPushButton("Export Art-pia GPT guides for preset")
        self.btn_import_mask = QtWidgets.QPushButton("Import mask for current part...")
        self.btn_extract_mask = QtWidgets.QPushButton("Extract mask from game screenshot...")
        self.btn_clear_mask = QtWidgets.QPushButton("Clear current part mask")
        self.lbl_mask = QtWidgets.QLabel("Mask: off")
        self.lbl_mask.setWordWrap(True)
        self.lbl_mask.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        mask_layout.addWidget(self.chk_clip_mask)
        mask_layout.addWidget(self.btn_export_artpia_guide_current)
        mask_layout.addWidget(self.btn_export_artpia_guide_type)
        mask_layout.addWidget(self.btn_import_mask)
        mask_layout.addWidget(self.btn_extract_mask)
        mask_layout.addWidget(self.btn_clear_mask)
        mask_layout.addWidget(self.lbl_mask)
        advanced_tabs.addTab(mask_tab, "Mask")

        skeleton_tab = QtWidgets.QWidget()
        skeleton_layout = QtWidgets.QFormLayout(skeleton_tab)
        self.chk_skeleton_warp = QtWidgets.QCheckBox("Flexible skeleton mapping")
        self.spin_skeleton_strength = QtWidgets.QSpinBox()
        self.spin_skeleton_strength.setRange(0, 100)
        self.spin_skeleton_strength.setSingleStep(5)
        self.spin_skeleton_strength.setSuffix(" %")
        self.spin_skeleton_padding = QtWidgets.QSpinBox()
        self.spin_skeleton_padding.setRange(-40, 40)
        self.spin_skeleton_padding.setSuffix(" px")
        self.btn_reset_skeleton = QtWidgets.QPushButton("Reset skeleton mapping")
        skeleton_layout.addRow(self.chk_skeleton_warp)
        skeleton_layout.addRow("Strength", self.spin_skeleton_strength)
        skeleton_layout.addRow("Edge padding", self.spin_skeleton_padding)
        skeleton_layout.addRow(self.btn_reset_skeleton)
        advanced_tabs.addTab(skeleton_tab, "Skeleton")

        calibration_tab = QtWidgets.QWidget()
        calibration_layout = QtWidgets.QFormLayout(calibration_tab)
        self.spin_mask_scale_x = QtWidgets.QSpinBox()
        self.spin_mask_scale_x.setRange(50, 150)
        self.spin_mask_scale_x.setSingleStep(1)
        self.spin_mask_scale_x.setSuffix(" %")
        self.spin_mask_scale_y = QtWidgets.QSpinBox()
        self.spin_mask_scale_y.setRange(50, 150)
        self.spin_mask_scale_y.setSingleStep(1)
        self.spin_mask_scale_y.setSuffix(" %")
        self.spin_mask_offset_x = QtWidgets.QSpinBox()
        self.spin_mask_offset_x.setRange(-100, 100)
        self.spin_mask_offset_x.setSuffix(" px")
        self.spin_mask_offset_y = QtWidgets.QSpinBox()
        self.spin_mask_offset_y.setRange(-100, 100)
        self.spin_mask_offset_y.setSuffix(" px")
        self.btn_reset_mask_calibration = QtWidgets.QPushButton("Reset mask calibration")
        calibration_layout.addRow("Mask scale X", self.spin_mask_scale_x)
        calibration_layout.addRow("Mask scale Y", self.spin_mask_scale_y)
        calibration_layout.addRow("Mask move X", self.spin_mask_offset_x)
        calibration_layout.addRow("Mask move Y", self.spin_mask_offset_y)
        calibration_layout.addRow(self.btn_reset_mask_calibration)
        advanced_tabs.addTab(calibration_tab, "Calibrate")

        advanced_layout.addWidget(advanced_tabs)
        left_layout.addWidget(advanced_box)

        export_box = QtWidgets.QGroupBox("Step 4 - Export")
        export_layout = QtWidgets.QVBoxLayout(export_box)
        out_row = QtWidgets.QHBoxLayout()
        self.lbl_output = QtWidgets.QLabel(str(self.output_dir))
        self.lbl_output.setWordWrap(True)
        self.lbl_output.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_choose_output = QtWidgets.QPushButton("Choose folder")
        out_row.addWidget(self.lbl_output, 1)
        out_row.addWidget(self.btn_choose_output)
        export_layout.addLayout(out_row)
        export_buttons = QtWidgets.QHBoxLayout()
        self.btn_export_current = QtWidgets.QPushButton("Export current part")
        self.btn_export_type = QtWidgets.QPushButton("Export current preset")
        self.btn_export_all = QtWidgets.QPushButton("Export all presets")
        self.btn_export_all.setVisible(False)
        self.btn_open_output = QtWidgets.QPushButton("Open output folder")
        export_buttons.addWidget(self.btn_export_current)
        export_buttons.addWidget(self.btn_export_type)
        export_layout.addLayout(export_buttons)
        export_layout.addWidget(self.btn_open_output)
        left_layout.addWidget(export_box)
        left_layout.addStretch(1)

        preview_box = QtWidgets.QGroupBox("Live preview")
        preview_layout = QtWidgets.QVBoxLayout(preview_box)
        body.addWidget(preview_box, 1)

        self.lbl_part_info = QtWidgets.QLabel("")
        self.lbl_part_info.setStyleSheet("font-weight: 600; color: #5a412d;")
        preview_layout.addWidget(self.lbl_part_info)

        self.lbl_preview = InteractivePreviewLabel()
        self.lbl_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumSize(600, 600)
        self.lbl_preview.setStyleSheet("QLabel { background: #202225; border: 1px solid #6b6f76; border-radius: 8px; }")
        preview_layout.addWidget(self.lbl_preview, 1)

        self.lbl_drag_hint = QtWidgets.QLabel("Drag preview = move image. Mouse wheel = resize. Export only after preview looks right.")
        self.lbl_drag_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_drag_hint.setStyleSheet("color: #8c735b;")
        preview_layout.addWidget(self.lbl_drag_hint)

        self.thumbs_layout = QtWidgets.QHBoxLayout()
        preview_layout.addLayout(self.thumbs_layout)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        self.btn_open.clicked.connect(self._on_open)
        self.btn_use_for_type.clicked.connect(self._on_use_current_source_for_type)
        self.btn_clear_part_source.clicked.connect(self._on_clear_current_part_source)
        self.cbo_part.currentTextChanged.connect(lambda _v: self._on_part_changed())
        self.cbo_fit.currentTextChanged.connect(lambda _v: self._on_preset_option_changed())
        self.chk_auto_crop.stateChanged.connect(lambda _v: self._on_preset_option_changed())
        self.chk_clip_mask.stateChanged.connect(lambda _v: self._on_preset_option_changed())
        self.btn_export_artpia_guide_current.clicked.connect(self._on_export_artpia_guide_current)
        self.btn_export_artpia_guide_type.clicked.connect(self._on_export_artpia_guide_type)
        self.btn_bg.clicked.connect(self._on_background)
        self.btn_import_mask.clicked.connect(self._on_import_mask)
        self.btn_extract_mask.clicked.connect(self._on_extract_mask_from_screenshot)
        self.btn_clear_mask.clicked.connect(self._on_clear_current_part_mask)
        self.spin_mask_scale_x.valueChanged.connect(lambda _v: self._on_mask_calibration_changed())
        self.spin_mask_scale_y.valueChanged.connect(lambda _v: self._on_mask_calibration_changed())
        self.spin_mask_offset_x.valueChanged.connect(lambda _v: self._on_mask_calibration_changed())
        self.spin_mask_offset_y.valueChanged.connect(lambda _v: self._on_mask_calibration_changed())
        self.btn_reset_mask_calibration.clicked.connect(self._on_reset_mask_calibration)
        self.chk_skeleton_warp.stateChanged.connect(lambda _v: self._on_skeleton_mapping_changed())
        self.spin_skeleton_strength.valueChanged.connect(lambda _v: self._on_skeleton_mapping_changed())
        self.spin_skeleton_padding.valueChanged.connect(lambda _v: self._on_skeleton_mapping_changed())
        self.btn_reset_skeleton.clicked.connect(self._on_reset_skeleton_mapping)
        self.spin_scale.valueChanged.connect(lambda _v: self._on_current_setting_changed())
        self.spin_offset_x.valueChanged.connect(lambda _v: self._on_current_setting_changed())
        self.spin_offset_y.valueChanged.connect(lambda _v: self._on_current_setting_changed())
        self.btn_reset_part.clicked.connect(self._on_reset_part)
        self.btn_copy_to_all_parts.clicked.connect(self._on_copy_to_all_parts)
        self.btn_copy_to_all.clicked.connect(self._on_copy_to_all)
        self.btn_choose_output.clicked.connect(self._on_choose_output)
        self.btn_open_output.clicked.connect(self._on_open_output)
        self.btn_export_current.clicked.connect(self._on_export_current)
        self.btn_export_type.clicked.connect(self._on_export_type)
        self.btn_export_all.clicked.connect(self._on_export_all)
        self.lbl_preview.dragged.connect(self._on_preview_dragged)
        self.lbl_preview.wheelScaled.connect(self._on_preview_wheel_scaled)

    def _current_clothing(self) -> str:
        clothing = self.current_preset or "Dress"
        return clothing if clothing in CLOTHING_TYPES else "Dress"

    def _preset_settings_for(self, clothing: str) -> PresetUiSettings:
        return self.preset_ui_settings.setdefault(clothing, PresetUiSettings())

    def _save_current_preset_options(self) -> None:
        if not hasattr(self, "cbo_fit"):
            return
        settings = self._preset_settings_for(self._current_clothing())
        settings.fit_text = self.cbo_fit.currentText() or settings.fit_text
        settings.auto_crop = bool(self.chk_auto_crop.isChecked())
        settings.clip_mask = bool(self.chk_clip_mask.isChecked())

    def _sync_preset_view(self) -> None:
        clothing = self._current_clothing()
        parts = CLOTHING_TYPES[clothing]
        for name, button in self.preset_buttons.items():
            button.blockSignals(True)
            try:
                button.setChecked(name == clothing)
            finally:
                button.blockSignals(False)

        part_summary = ", ".join(f"{part} {size[0]}x{size[1]}" for part, size in parts.items())
        self.lbl_active_preset.setText(f"Active preset: {clothing}\nLoaded parts: {part_summary}")
        self.lbl_selected_preset_value.setText(clothing)
        self.settings_box.setTitle(f"Step 3 - Fit and position ({clothing})")
        self.btn_use_for_type.setText(f"Use this image for all {clothing} parts")
        self.btn_export_type.setText(f"Export {clothing} preset")
        self.btn_copy_to_all_parts.setText(f"Copy position to all {clothing} parts")

        settings = self._preset_settings_for(clothing)
        widgets = (self.cbo_fit, self.chk_auto_crop, self.chk_clip_mask)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            if self.cbo_fit.findText(settings.fit_text) >= 0:
                self.cbo_fit.setCurrentText(settings.fit_text)
            self.chk_auto_crop.setChecked(settings.auto_crop)
            self.chk_clip_mask.setChecked(settings.clip_mask)
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def _select_preset(self, clothing: str) -> None:
        if clothing not in CLOTHING_TYPES:
            return
        if clothing == self._current_clothing():
            self._sync_preset_view()
            return
        self._save_current_preset_options()
        self.current_preset = clothing
        self._sync_preset_view()
        self._sync_part_combo()
        self._sync_part_controls()
        self._update_source_label()
        self._update_preview()

    def _parts_for_current_type(self) -> dict[str, Tuple[int, int]]:
        return CLOTHING_TYPES[self._current_clothing()]

    def _current_part(self) -> str:
        parts = self._parts_for_current_type()
        part = self.cbo_part.currentText() or next(iter(parts))
        return part if part in parts else next(iter(parts))

    def _mask_for(self, clothing: str, part: str) -> str:
        if not self.chk_clip_mask.isChecked():
            return "none"
        if (clothing, part) in self.mask_paths_by_key:
            return "none"
        return PART_MASKS.get(clothing, {}).get(part, "none")

    def _fit_mode(self) -> str:
        text = self.cbo_fit.currentText().lower()
        if "contain" in text:
            return "Contain"
        if "stretch" in text:
            return "Stretch"
        return "Cover"

    def _settings_for(self, clothing: str, part: str) -> PartSettings:
        return self.part_settings.setdefault((clothing, part), PartSettings())

    def _mask_calibration_for(self, clothing: str, part: str) -> MaskCalibration:
        return self.mask_calibrations.setdefault((clothing, part), MaskCalibration())

    def _skeleton_mapping_for(self, clothing: str, part: str) -> SkeletonMapping:
        return self.skeleton_mappings.setdefault((clothing, part), SkeletonMapping())

    def _source_for(self, clothing: str, part: str) -> Path | None:
        return self.source_paths_by_key.get((clothing, part))

    def _mask_source_for(self, clothing: str, part: str) -> Path | None:
        if not self.chk_clip_mask.isChecked():
            return None
        return self.mask_paths_by_key.get((clothing, part))

    def _uses_mask(self, clothing: str, part: str) -> bool:
        return self.chk_clip_mask.isChecked() and (
            (clothing, part) in self.mask_paths_by_key
            or PART_MASKS.get(clothing, {}).get(part, "none") != "none"
        )

    def _is_exact_part_template_path(self, path: Path, clothing: str, part: str) -> bool:
        name = path.name.lower()
        markers = ("__clothing_template__", "__dress_template__", "__tshirt_template__")
        if not any(marker in name for marker in markers):
            return False
        try:
            with Image.open(path) as img:
                return img.size == CLOTHING_TYPES[clothing][part]
        except Exception:
            return False

    def _content_rect_for(self, clothing: str, part: str) -> tuple[float, float, float, float]:
        w, h = CLOTHING_TYPES[clothing][part]
        s = self._settings_for(clothing, part)
        scale = max(0.25, min(3.0, float(s.scale)))
        cx = 0.5 + (float(s.offset_x) / max(1, w))
        cy = 0.5 + (float(s.offset_y) / max(1, h))
        return (cx - (scale / 2.0), cy - (scale / 2.0), scale, scale)

    def _mask_content_rect_for(self, clothing: str, part: str) -> tuple[float, float, float, float] | None:
        if self._mask_source_for(clothing, part) is None:
            return None

        w, h = CLOTHING_TYPES[clothing][part]
        c = self._mask_calibration_for(clothing, part)
        scale_x = max(0.5, min(1.5, float(c.scale_x)))
        scale_y = max(0.5, min(1.5, float(c.scale_y)))
        cx = 0.5 + (float(c.offset_x) / max(1, w))
        cy = 0.5 + (float(c.offset_y) / max(1, h))
        if abs(scale_x - 1.0) < 0.0001 and abs(scale_y - 1.0) < 0.0001 and abs(c.offset_x) < 0.0001 and abs(c.offset_y) < 0.0001:
            return None
        return (cx - (scale_x / 2.0), cy - (scale_y / 2.0), scale_x, scale_y)

    def _prep_for(self, clothing: str, part: str) -> ImagePrepOptions:
        source = self._source_for(clothing, part)
        is_exact = source is not None and self._is_exact_part_template_path(source, clothing, part)
        uses_mask = self._uses_mask(clothing, part)
        mask_source = self._mask_source_for(clothing, part)
        skeleton = self._skeleton_mapping_for(clothing, part)
        return ImagePrepOptions(
            fit_mode="Stretch" if is_exact else self._fit_mode(),
            auto_crop=False if is_exact else bool(self.chk_auto_crop.isChecked()),
            palette_map=False,
            dither=False,
            background_rgb=self.background_rgb,
            content_rect=None if is_exact else self._content_rect_for(clothing, part),
            paint_mask_shape=self._mask_for(clothing, part),
            mask_image_path=str(mask_source) if mask_source is not None else None,
            mask_content_rect=self._mask_content_rect_for(clothing, part),
            ignore_source_alpha=not uses_mask,
            skeleton_row_warp=bool(skeleton.enabled and uses_mask),
            skeleton_warp_strength=float(skeleton.strength),
            skeleton_edge_padding=int(skeleton.edge_padding),
        )

    def _render_grid(self, clothing: str, part: str) -> PixelGrid | None:
        source = self._source_for(clothing, part)
        if source is None:
            return None
        w, h = CLOTHING_TYPES[clothing][part]
        return load_and_resize_to_grid(
            str(source),
            w=w,
            h=h,
            prep=self._prep_for(clothing, part),
        )

    def _grid_to_qpixmap(self, grid: PixelGrid, target_size: QtCore.QSize) -> QtGui.QPixmap:
        img = self._grid_to_image(grid, transparent_outside=True)
        data = img.tobytes("raw", "RGBA")
        qimg = QtGui.QImage(data, img.width, img.height, QtGui.QImage.Format.Format_RGBA8888).copy()
        pix = QtGui.QPixmap.fromImage(qimg)
        bg = _checkerboard((max(1, target_size.width()), max(1, target_size.height())))
        painter = QtGui.QPainter(bg)
        scaled = pix.scaled(
            target_size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
        x = int((target_size.width() - scaled.width()) / 2)
        y = int((target_size.height() - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return bg

    def _grid_to_image(self, grid: PixelGrid, transparent_outside: bool) -> Image.Image:
        img = Image.new("RGBA", (int(grid.w), int(grid.h)))
        data = []
        mask = grid.paint_mask
        for idx, (r, g, b) in enumerate(grid.pixels):
            alpha = 255
            if transparent_outside and mask is not None and idx < len(mask) and not mask[idx]:
                alpha = 0
            data.append((int(r), int(g), int(b), alpha))
        img.putdata(data)
        return img

    def _sync_part_combo(self) -> None:
        parts = list(self._parts_for_current_type().keys())
        current = self.cbo_part.currentText()
        self.cbo_part.blockSignals(True)
        try:
            self.cbo_part.clear()
            self.cbo_part.addItems(parts)
            if current in parts:
                self.cbo_part.setCurrentText(current)
        finally:
            self.cbo_part.blockSignals(False)
        self._rebuild_thumbnails()

    def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.deleteLater()

    def _rebuild_thumbnails(self) -> None:
        self._clear_layout(self.thumbs_layout)
        self.thumb_labels = {}
        for part in self._parts_for_current_type():
            box = QtWidgets.QVBoxLayout()
            label = QtWidgets.QLabel(part)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            thumb = QtWidgets.QLabel()
            thumb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            thumb.setFixedSize(150, 190)
            thumb.setStyleSheet("QLabel { background: #333; border: 1px solid #666; }")
            box.addWidget(label)
            box.addWidget(thumb)
            self.thumbs_layout.addLayout(box)
            self.thumb_labels[part] = thumb

    def _sync_part_controls(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        s = self._settings_for(clothing, part)
        c = self._mask_calibration_for(clothing, part)
        skel = self._skeleton_mapping_for(clothing, part)
        widgets = (
            self.spin_scale,
            self.spin_offset_x,
            self.spin_offset_y,
            self.spin_mask_scale_x,
            self.spin_mask_scale_y,
            self.spin_mask_offset_x,
            self.spin_mask_offset_y,
            self.chk_skeleton_warp,
            self.spin_skeleton_strength,
            self.spin_skeleton_padding,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.spin_scale.setValue(int(round(float(s.scale) * 100.0)))
            self.spin_offset_x.setValue(int(round(float(s.offset_x))))
            self.spin_offset_y.setValue(int(round(float(s.offset_y))))
            self.spin_mask_scale_x.setValue(int(round(float(c.scale_x) * 100.0)))
            self.spin_mask_scale_y.setValue(int(round(float(c.scale_y) * 100.0)))
            self.spin_mask_offset_x.setValue(int(round(float(c.offset_x))))
            self.spin_mask_offset_y.setValue(int(round(float(c.offset_y))))
            self.chk_skeleton_warp.setChecked(bool(skel.enabled))
            self.spin_skeleton_strength.setValue(int(round(float(skel.strength) * 100.0)))
            self.spin_skeleton_padding.setValue(int(skel.edge_padding))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._sync_skeleton_control_state()

    def _sync_skeleton_control_state(self) -> None:
        has_mask = self._uses_mask(self._current_clothing(), self._current_part())
        enabled = bool(self.chk_skeleton_warp.isChecked() and has_mask)
        self.spin_skeleton_strength.setEnabled(enabled)
        self.spin_skeleton_padding.setEnabled(enabled)
        self.btn_reset_skeleton.setEnabled(bool(self.chk_skeleton_warp.isChecked()))
        if has_mask:
            self.chk_skeleton_warp.setToolTip("Warp each image row into the active clothing mask.")
        else:
            self.chk_skeleton_warp.setToolTip("Enable Clip to mask or import/extract a mask before skeleton mapping has an effect.")

    def _on_clothing_changed(self) -> None:
        self._save_current_preset_options()
        self._sync_preset_view()
        self._sync_part_combo()
        self._sync_part_controls()
        self._update_source_label()
        self._update_preview()

    def _on_preset_option_changed(self) -> None:
        self._save_current_preset_options()
        self._sync_skeleton_control_state()
        self._update_preview()

    def _on_part_changed(self) -> None:
        self._sync_part_controls()
        self._update_source_label()
        self._update_preview()

    def _on_current_setting_changed(self) -> None:
        s = self._settings_for(self._current_clothing(), self._current_part())
        s.scale = self.spin_scale.value() / 100.0
        s.offset_x = float(self.spin_offset_x.value())
        s.offset_y = float(self.spin_offset_y.value())
        self._update_preview()

    def _on_mask_calibration_changed(self) -> None:
        c = self._mask_calibration_for(self._current_clothing(), self._current_part())
        c.scale_x = self.spin_mask_scale_x.value() / 100.0
        c.scale_y = self.spin_mask_scale_y.value() / 100.0
        c.offset_x = float(self.spin_mask_offset_x.value())
        c.offset_y = float(self.spin_mask_offset_y.value())
        self._update_preview()

    def _on_reset_mask_calibration(self) -> None:
        self.mask_calibrations[(self._current_clothing(), self._current_part())] = MaskCalibration()
        self._sync_part_controls()
        self._update_preview()

    def _on_skeleton_mapping_changed(self) -> None:
        skel = self._skeleton_mapping_for(self._current_clothing(), self._current_part())
        skel.enabled = bool(self.chk_skeleton_warp.isChecked())
        skel.strength = self.spin_skeleton_strength.value() / 100.0
        skel.edge_padding = int(self.spin_skeleton_padding.value())
        self._sync_skeleton_control_state()
        self._update_preview()

    def _on_reset_skeleton_mapping(self) -> None:
        self.skeleton_mappings[(self._current_clothing(), self._current_part())] = SkeletonMapping()
        self._sync_part_controls()
        self._update_preview()

    def _preview_scale_factor(self) -> float:
        if self._current_grid is None:
            return 1.0
        size = self.lbl_preview.size()
        return max(0.01, min(size.width() / max(1, self._current_grid.w), size.height() / max(1, self._current_grid.h)))

    def _on_preview_dragged(self, dx: int, dy: int) -> None:
        if self._source_for(self._current_clothing(), self._current_part()) is None:
            return
        factor = self._preview_scale_factor()
        self.spin_offset_x.setValue(self.spin_offset_x.value() + int(round(dx / factor)))
        self.spin_offset_y.setValue(self.spin_offset_y.value() + int(round(dy / factor)))

    def _on_preview_wheel_scaled(self, step: int) -> None:
        if self._source_for(self._current_clothing(), self._current_part()) is None:
            return
        self.spin_scale.setValue(self.spin_scale.value() + int(step))

    def _on_reset_part(self) -> None:
        self.part_settings[(self._current_clothing(), self._current_part())] = PartSettings()
        self._sync_part_controls()
        self._update_preview()

    def _on_copy_to_all_parts(self) -> None:
        clothing = self._current_clothing()
        current = self._settings_for(clothing, self._current_part())
        for part in CLOTHING_TYPES[clothing]:
            self.part_settings[(clothing, part)] = PartSettings(
                scale=float(current.scale),
                offset_x=float(current.offset_x),
                offset_y=float(current.offset_y),
            )
        self._sync_part_controls()
        self._update_preview()

    def _on_copy_to_all(self) -> None:
        current = self._settings_for(self._current_clothing(), self._current_part())
        for clothing, parts in CLOTHING_TYPES.items():
            for part in parts:
                self.part_settings[(clothing, part)] = PartSettings(
                    scale=float(current.scale),
                    offset_x=float(current.offset_x),
                    offset_y=float(current.offset_y),
                )
        self._sync_part_controls()
        self._update_preview()

    def _on_open(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Import image for {clothing} / {part}",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not path:
            return
        selected = Path(path)
        self.source_path = selected
        self.source_paths_by_key[(clothing, part)] = selected
        self.output_dir = selected.parent
        self.lbl_output.setText(str(self.output_dir))
        self._update_source_label()
        self._update_preview()

    def _on_use_current_source_for_type(self) -> None:
        clothing = self._current_clothing()
        source = self._source_for(clothing, self._current_part())
        if source is None:
            QtWidgets.QMessageBox.information(self, "No image", "Import an image for the current part first.")
            return
        for part in CLOTHING_TYPES[clothing]:
            self.source_paths_by_key[(clothing, part)] = source
        self.source_path = source
        self._update_source_label()
        self._update_preview()

    def _on_clear_current_part_source(self) -> None:
        key = (self._current_clothing(), self._current_part())
        self.source_paths_by_key.pop(key, None)
        if not self.source_paths_by_key:
            self.source_path = None
        self._update_source_label()
        self._update_preview()

    def _export_artpia_guide_for(self, clothing: str, part: str) -> dict[str, Path]:
        paths = save_artpia_template_files(clothing, part, self.output_dir, scale=10)
        self.mask_paths_by_key[(clothing, part)] = paths["mask"]
        return paths

    def _on_export_artpia_guide_current(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        if find_artpia_part_template(clothing, part) is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Art-pia guide",
                f"No Art-pia template data for {clothing} / {part}.",
            )
            return
        try:
            paths = self._export_artpia_guide_for(clothing, part)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Art-pia guide export failed", str(e))
            return
        self.chk_clip_mask.setChecked(True)
        self._update_mask_label()
        self._update_preview()
        QtWidgets.QMessageBox.information(
            self,
            "Art-pia guide exported",
            "Created exact template files:\n\n"
            f"GPT guide: {paths['guide']}\n"
            f"Mask: {paths['mask']}",
        )

    def _on_export_artpia_guide_type(self) -> None:
        clothing = self._current_clothing()
        created: list[Path] = []
        missing: list[str] = []
        try:
            for part in CLOTHING_TYPES[clothing]:
                if find_artpia_part_template(clothing, part) is None:
                    missing.append(part)
                    continue
                paths = self._export_artpia_guide_for(clothing, part)
                created.extend([paths["guide"], paths["mask"]])
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Art-pia guide export failed", str(e))
            return
        if created:
            self.chk_clip_mask.setChecked(True)
            self._update_mask_label()
            self._update_preview()
        detail = "\n".join(str(path) for path in created)
        if missing:
            detail += "\n\nMissing Art-pia data for: " + ", ".join(missing)
        QtWidgets.QMessageBox.information(
            self,
            "Art-pia guides exported",
            f"Created {len(created)} files for {clothing}:\n\n{detail}",
        )

    def _on_import_mask(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Import real mask/template for {clothing} / {part}",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not path:
            return
        self.mask_paths_by_key[(clothing, part)] = Path(path)
        self.chk_clip_mask.setChecked(True)
        self._update_mask_label()
        self._update_preview()

    def _on_extract_mask_from_screenshot(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        target_size = CLOTHING_TYPES[clothing][part]
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Extract real game mask for {clothing} / {part}",
            str(Path.home() / "Pictures"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not path:
            return

        try:
            mask, info = _extract_game_mask_from_screenshot(Path(path), target_size)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Mask extraction failed", str(e))
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        type_stem = _safe_stem(clothing)
        part_stem = _safe_stem(part)
        out_path = self.output_dir / f"{Path(path).stem}__real_game_mask__{type_stem}__{part_stem}__{target_size[0]}x{target_size[1]}.png"
        try:
            mask.save(out_path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Mask save failed", str(e))
            return

        self.mask_paths_by_key[(clothing, part)] = out_path
        self.chk_clip_mask.setChecked(True)
        self._update_mask_label()
        self._update_preview()
        QtWidgets.QMessageBox.information(
            self,
            "Mask extracted",
            f"Created and applied mask:\n{out_path}\n\n{info}",
        )

    def _on_clear_current_part_mask(self) -> None:
        self.mask_paths_by_key.pop((self._current_clothing(), self._current_part()), None)
        self._update_mask_label()
        self._update_preview()

    def _update_source_label(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        source = self.source_paths_by_key.get((clothing, part))
        if source is not None:
            self.lbl_source.setText(f"{clothing} / {part}: {source}")
        else:
            self.lbl_source.setText(f"{clothing} / {part}: no image assigned in this preset")
        self._update_mask_label()

    def _update_mask_label(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        if not self.chk_clip_mask.isChecked():
            self.lbl_mask.setText("Mask: off, exporting full exact-size rectangle")
            return
        mask = self.mask_paths_by_key.get((clothing, part))
        if mask is not None:
            calib = self._mask_calibration_for(clothing, part)
            calib_text = (
                ""
                if abs(calib.scale_x - 1.0) < 0.0001
                and abs(calib.scale_y - 1.0) < 0.0001
                and abs(calib.offset_x) < 0.0001
                and abs(calib.offset_y) < 0.0001
                else f" | calibration sx={calib.scale_x:.2f}, sy={calib.scale_y:.2f}, ox={calib.offset_x:.0f}, oy={calib.offset_y:.0f}"
            )
            self.lbl_mask.setText(f"Mask: custom {mask}{calib_text}")
            return
        builtin = PART_MASKS.get(clothing, {}).get(part, "none")
        if builtin == "none":
            self.lbl_mask.setText("Mask: none for this part")
        else:
            self.lbl_mask.setText(f"Mask: built-in approximate {builtin}; calibration applies to custom masks")

    def _on_background(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(*self.background_rgb),
            self,
            "Template background color",
        )
        if not color.isValid():
            return
        self.background_rgb = (int(color.red()), int(color.green()), int(color.blue()))
        self.btn_bg.setText(f"Background: #{color.red():02X}{color.green():02X}{color.blue():02X}")
        self._update_preview()

    def _on_choose_output(self) -> None:
        out = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose output folder",
            str(self.output_dir),
        )
        if not out:
            return
        self.output_dir = Path(out)
        self.lbl_output.setText(str(self.output_dir))

    def _on_open_output(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.output_dir))  # type: ignore[attr-defined]

    def _update_preview(self) -> None:
        clothing = self._current_clothing()
        part = self._current_part()
        w, h = CLOTHING_TYPES[clothing][part]
        skeleton = self._skeleton_mapping_for(clothing, part)
        skeleton_text = (
            f", skeleton={int(round(skeleton.strength * 100))}% pad={skeleton.edge_padding}px"
            if skeleton.enabled and self._uses_mask(clothing, part)
            else ""
        )
        self.lbl_part_info.setText(f"{clothing} / {part}: {w}x{h} px, mask={self._mask_for(clothing, part)}{skeleton_text}")
        self._update_source_label()

        if self._source_for(clothing, part) is None:
            self.lbl_preview.setText("Import an image for this part first")
            self.lbl_preview.setPixmap(QtGui.QPixmap())
            for p, thumb in self.thumb_labels.items():
                thumb.setText("No image" if self._source_for(clothing, p) is None else "Switch part")
                thumb.setPixmap(QtGui.QPixmap())
            return

        try:
            current = self._render_grid(clothing, part)
            self._current_grid = current
            if current is not None:
                self.lbl_preview.setPixmap(self._grid_to_qpixmap(current, self.lbl_preview.size()))
            for p, thumb in self.thumb_labels.items():
                grid = self._render_grid(clothing, p)
                if grid is None:
                    thumb.setText("No image")
                else:
                    thumb.setPixmap(self._grid_to_qpixmap(grid, thumb.size()))
            self.status.showMessage("Preview updated", 1500)
        except Exception as e:
            self.lbl_preview.setText(str(e))
            self.status.showMessage(f"Preview failed: {e}", 5000)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._update_preview)

    def _export_part(self, clothing: str, part: str) -> Path:
        source = self._source_for(clothing, part)
        if source is None:
            raise RuntimeError(f"Import an image for {clothing} / {part} first.")
        grid = self._render_grid(clothing, part)
        if grid is None:
            raise RuntimeError("Preview grid is empty.")
        w, h = CLOTHING_TYPES[clothing][part]
        source_stem = _safe_stem(source.stem)
        type_stem = _safe_stem(clothing)
        part_stem = _safe_stem(part)
        marker = "__clothing_template_masked__" if self._uses_mask(clothing, part) else "__clothing_template__"
        out_path = self.output_dir / f"{source_stem}{marker}{type_stem}__{part_stem}__{w}x{h}.png"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._grid_to_image(grid, transparent_outside=self._uses_mask(clothing, part)).save(out_path)
        return out_path

    def _on_export_current(self) -> None:
        try:
            out = self._export_part(self._current_clothing(), self._current_part())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(e))
            return
        QtWidgets.QMessageBox.information(self, "Exported", f"Created:\n{out}")

    def _on_export_type(self) -> None:
        clothing = self._current_clothing()
        try:
            paths = [self._export_part(clothing, part) for part in CLOTHING_TYPES[clothing]]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(e))
            return
        QtWidgets.QMessageBox.information(
            self,
            "Exported",
            f"Created {clothing} templates:\n\n" + "\n".join(str(p) for p in paths),
        )

    def _on_export_all(self) -> None:
        try:
            paths = [
                self._export_part(clothing, part)
                for clothing, parts in CLOTHING_TYPES.items()
                for part in parts
            ]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(e))
            return
        QtWidgets.QMessageBox.information(
            self,
            "Exported",
            "Created all clothing templates:\n\n" + "\n".join(str(p) for p in paths),
        )


def run() -> None:
    app = QtWidgets.QApplication([])
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    w = DressTemplateManager()
    w.show()
    raise SystemExit(app.exec())
