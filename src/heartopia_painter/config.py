from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


Point = Tuple[int, int]
RGB = Tuple[int, int, int]
Rect = Tuple[int, int, int, int]


@dataclass
class ShadeButton:
    name: str
    pos: Point
    rgb: RGB


@dataclass
class MainColor:
    name: str
    pos: Point
    rgb: RGB
    shades: List[ShadeButton] = field(default_factory=list)


@dataclass
class ClothingPartSpec:
    name: str
    w: int
    h: int


def default_custom_clothing_parts() -> List[ClothingPartSpec]:
    return [ClothingPartSpec(name="Part 1", w=64, h=80)]


@dataclass
class AppConfig:
    # Store the UI preset key (e.g. "1:1" or "T-Shirt") so it can be restored on startup.
    canvas_preset: str = "1:1"

    # For 1:1 preset
    one_to_one_precision: str = "Small"

    # For 16:9 preset
    sixteen_nine_precision: str = "Small"

    # For 9:16 preset
    nine_sixteen_precision: str = "Small"

    # For 4:3 preset
    four_three_precision: str = "Small"

    # For 3:4 preset
    three_four_precision: str = "Small"

    # Convenience: restore last session state
    last_image_path: Optional[str] = None
    last_canvas_rect: Optional[Rect] = None

    # Per-selection persistence (used for multi-part presets like T-Shirt)
    last_image_path_by_key: Dict[str, str] = field(default_factory=dict)
    last_canvas_rect_by_key: Dict[str, Rect] = field(default_factory=dict)

    # Per-game-preset selected part, loaded from extracted Heartopia draw tables.
    game_draw_part_by_preset: Dict[str, str] = field(default_factory=dict)

    # For T-Shirt preset
    tshirt_part: str = "Front"

    # For Tank Top preset
    tank_top_part: str = "Front"

    # For Dress preset
    dress_part: str = "Front"
    dress_mapping_scale_by_part: Dict[str, float] = field(default_factory=dict)
    dress_mapping_offset_x_by_part: Dict[str, float] = field(default_factory=dict)
    dress_mapping_offset_y_by_part: Dict[str, float] = field(default_factory=dict)

    # Flexible clothing preset. Each part behaves like a T-Shirt part, but users
    # can define the grid size themselves for future clothing items.
    custom_clothing_part: str = "Part 1"
    custom_clothing_parts: List[ClothingPartSpec] = field(default_factory=default_custom_clothing_parts)

    # Image preparation before painting.
    # - Smart: auto-crop then contain-fit to avoid accidentally cutting artwork.
    # - Stretch: legacy behavior.
    # - Contain: preserve full artwork with background padding.
    # - Cover: fill the full grid and crop the excess.
    image_fit_mode: str = "Smart"
    image_auto_crop: bool = True
    image_palette_map_enabled: bool = False
    image_dither_enabled: bool = False
    image_background_rgb: RGB = (255, 255, 255)
    artpia_exact_mask_enabled: bool = False

    # Painting timing (seconds). These defaults are conservative to improve click reliability.
    move_duration_s: float = 0.03
    mouse_down_s: float = 0.02
    after_click_delay_s: float = 0.06
    panel_open_delay_s: float = 0.12
    shade_select_delay_s: float = 0.06
    row_delay_s: float = 0.10

    # Optional: drag strokes across adjacent same-color pixels.
    # Disabled by default because some games/canvases may not support drag painting.
    enable_drag_strokes: bool = False
    drag_step_duration_s: float = 0.01
    after_drag_delay_s: float = 0.02

    # Verification (row-by-row repaint until correct)
    verify_rows: bool = True
    verify_tolerance: int = 35  # max per-channel-ish RGB distance tolerance (used as Euclidean threshold)
    verify_max_passes: int = 10
    verify_settle_s: float = 0.05

    # Optional: verify while painting by checking cells a few clicks behind.
    # This can catch missed clicks sooner and reduce long verify loops.
    verify_streaming_enabled: bool = False
    verify_streaming_lag: int = 10

    # Optional: if verification appears stuck (no improvement), auto-recover by
    # resyncing UI state and skipping the failing verify segment instead of
    # raising an error.
    verify_auto_recover_loops: bool = False
    verify_auto_recover_after_passes: int = 2

    # Optional: show an always-on-top, click-through status overlay over the game
    # during painting/verification.
    status_overlay_enabled: bool = True

    # Painting mode
    # - "row": iterate pixels in row/column order
    # - "color": group by shade and paint one shade at a time
    paint_mode: str = "row"

    # Optional speed-up: bucket-fill the most used shade first.
    bucket_fill_enabled: bool = False
    bucket_fill_min_cells: int = 50

    # Optional extra speed-up (Paint-by-Color): detect large connected regions of a shade,
    # outline them, then bucket-fill the inside. Works best when the canvas started from
    # a uniform base fill.
    bucket_fill_regions_enabled: bool = False
    bucket_fill_regions_min_cells: int = 200

    # Buttons that are global (same regardless of which color is selected)
    shades_panel_button_pos: Optional[Point] = None
    back_button_pos: Optional[Point] = None

    # Tool buttons
    paint_tool_button_pos: Optional[Point] = None
    bucket_tool_button_pos: Optional[Point] = None
    eraser_tool_button_pos: Optional[Point] = None
    eraser_thickness_up_button_pos: Optional[Point] = None

    main_colors: List[MainColor] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json_dict(data: dict) -> "AppConfig":
        def to_tuple2(v):
            if v is None:
                return None
            return (int(v[0]), int(v[1]))

        def to_rgb(v):
            return (int(v[0]), int(v[1]), int(v[2]))

        def to_tuple4(v):
            if v is None:
                return None
            return (int(v[0]), int(v[1]), int(v[2]), int(v[3]))

        def to_rect_map(v) -> Dict[str, Rect]:
            if not isinstance(v, dict):
                return {}
            out: Dict[str, Rect] = {}
            for k, rv in v.items():
                r = to_tuple4(rv)
                if r is not None:
                    out[str(k)] = r
            return out

        def to_str_map(v) -> Dict[str, str]:
            if not isinstance(v, dict):
                return {}
            out: Dict[str, str] = {}
            for k, sv in v.items():
                if sv is None:
                    continue
                out[str(k)] = str(sv)
            return out

        def to_float_map(v) -> Dict[str, float]:
            if not isinstance(v, dict):
                return {}
            out: Dict[str, float] = {}
            for k, fv in v.items():
                try:
                    out[str(k)] = float(fv)
                except Exception:
                    continue
            return out

        cfg = AppConfig()
        preset_raw = data.get("canvas_preset", "1:1")
        preset_raw = str(preset_raw)

        # Backward compatibility:
        # - early configs stored "30x30"
        # - later configs stored "1:1 (30x30)"
        if preset_raw == "30x30":
            cfg.canvas_preset = "1:1"
            cfg.one_to_one_precision = "Small"
        elif preset_raw.startswith("1:1") and "(" in preset_raw and "30x30" in preset_raw:
            cfg.canvas_preset = "1:1"
            cfg.one_to_one_precision = "Small"
        elif preset_raw == "Custom Clothing":
            cfg.canvas_preset = "Dress"
        else:
            cfg.canvas_preset = preset_raw

        cfg.one_to_one_precision = str(data.get("one_to_one_precision", cfg.one_to_one_precision))
        cfg.sixteen_nine_precision = str(data.get("sixteen_nine_precision", cfg.sixteen_nine_precision))
        cfg.nine_sixteen_precision = str(data.get("nine_sixteen_precision", cfg.nine_sixteen_precision))
        cfg.four_three_precision = str(data.get("four_three_precision", cfg.four_three_precision))
        cfg.three_four_precision = str(data.get("three_four_precision", cfg.three_four_precision))

        cfg.last_image_path = data.get("last_image_path")
        if cfg.last_image_path is not None:
            cfg.last_image_path = str(cfg.last_image_path)
        cfg.last_canvas_rect = to_tuple4(data.get("last_canvas_rect"))

        cfg.last_image_path_by_key = to_str_map(data.get("last_image_path_by_key"))
        cfg.last_canvas_rect_by_key = to_rect_map(data.get("last_canvas_rect_by_key"))
        cfg.game_draw_part_by_preset = to_str_map(data.get("game_draw_part_by_preset"))

        cfg.tshirt_part = str(data.get("tshirt_part", cfg.tshirt_part))
        cfg.tank_top_part = str(data.get("tank_top_part", cfg.tank_top_part))
        cfg.dress_part = str(data.get("dress_part", cfg.dress_part))
        if not cfg.dress_part or cfg.dress_part in {"Full Body", "Front Part"}:
            cfg.dress_part = "Front"
        elif cfg.dress_part == "Back Part":
            cfg.dress_part = "Back"
        cfg.dress_mapping_scale_by_part = to_float_map(data.get("dress_mapping_scale_by_part"))
        cfg.dress_mapping_offset_x_by_part = to_float_map(data.get("dress_mapping_offset_x_by_part"))
        cfg.dress_mapping_offset_y_by_part = to_float_map(data.get("dress_mapping_offset_y_by_part"))

        cfg.custom_clothing_part = str(data.get("custom_clothing_part", cfg.custom_clothing_part))
        cfg.custom_clothing_parts = []
        raw_parts = data.get("custom_clothing_parts", None)
        if isinstance(raw_parts, list):
            for raw in raw_parts:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name", "")).strip() or "Part"
                try:
                    w = max(1, int(raw.get("w", 64)))
                    h = max(1, int(raw.get("h", 80)))
                except Exception:
                    w, h = 64, 80
                cfg.custom_clothing_parts.append(ClothingPartSpec(name=name, w=w, h=h))
        if not cfg.custom_clothing_parts:
            cfg.custom_clothing_parts = default_custom_clothing_parts()
        if cfg.custom_clothing_part not in {p.name for p in cfg.custom_clothing_parts}:
            cfg.custom_clothing_part = cfg.custom_clothing_parts[0].name

        fit_mode = str(data.get("image_fit_mode", cfg.image_fit_mode)).strip()
        if fit_mode.lower() in {"smart", "stretch", "contain", "cover"}:
            cfg.image_fit_mode = fit_mode.title()
        cfg.image_auto_crop = bool(data.get("image_auto_crop", cfg.image_auto_crop))
        cfg.image_palette_map_enabled = bool(
            data.get("image_palette_map_enabled", cfg.image_palette_map_enabled)
        )
        cfg.image_dither_enabled = bool(data.get("image_dither_enabled", cfg.image_dither_enabled))
        try:
            cfg.image_background_rgb = to_rgb(data.get("image_background_rgb", cfg.image_background_rgb))
        except Exception:
            cfg.image_background_rgb = (255, 255, 255)
        cfg.artpia_exact_mask_enabled = bool(
            data.get("artpia_exact_mask_enabled", cfg.artpia_exact_mask_enabled)
        )

        # Migrate older per-key naming schemes to the new keys.
        # Old: "1:1 (30x30)" -> New: "1:1::Small"
        if "1:1 (30x30)" in cfg.last_image_path_by_key and "1:1::Small" not in cfg.last_image_path_by_key:
            cfg.last_image_path_by_key["1:1::Small"] = cfg.last_image_path_by_key["1:1 (30x30)"]
        if "1:1 (30x30)" in cfg.last_canvas_rect_by_key and "1:1::Small" not in cfg.last_canvas_rect_by_key:
            cfg.last_canvas_rect_by_key["1:1::Small"] = cfg.last_canvas_rect_by_key["1:1 (30x30)"]

        # Migrate legacy single-value fields into the per-key maps.
        if cfg.last_image_path and "1:1::Small" not in cfg.last_image_path_by_key:
            cfg.last_image_path_by_key["1:1::Small"] = cfg.last_image_path
        if cfg.last_canvas_rect and "1:1::Small" not in cfg.last_canvas_rect_by_key:
            cfg.last_canvas_rect_by_key["1:1::Small"] = cfg.last_canvas_rect

        def to_float(v, default: float) -> float:
            try:
                return float(v)
            except Exception:
                return default

        cfg.move_duration_s = to_float(data.get("move_duration_s"), cfg.move_duration_s)
        cfg.mouse_down_s = to_float(data.get("mouse_down_s"), cfg.mouse_down_s)
        cfg.after_click_delay_s = to_float(data.get("after_click_delay_s"), cfg.after_click_delay_s)
        cfg.panel_open_delay_s = to_float(data.get("panel_open_delay_s"), cfg.panel_open_delay_s)
        cfg.shade_select_delay_s = to_float(data.get("shade_select_delay_s"), cfg.shade_select_delay_s)
        cfg.row_delay_s = to_float(data.get("row_delay_s"), cfg.row_delay_s)

        cfg.enable_drag_strokes = bool(data.get("enable_drag_strokes", cfg.enable_drag_strokes))
        cfg.drag_step_duration_s = to_float(data.get("drag_step_duration_s"), cfg.drag_step_duration_s)
        cfg.after_drag_delay_s = to_float(data.get("after_drag_delay_s"), cfg.after_drag_delay_s)

        cfg.verify_rows = bool(data.get("verify_rows", cfg.verify_rows))
        try:
            cfg.verify_tolerance = int(data.get("verify_tolerance", cfg.verify_tolerance))
        except Exception:
            pass
        try:
            cfg.verify_max_passes = int(data.get("verify_max_passes", cfg.verify_max_passes))
        except Exception:
            pass
        cfg.verify_settle_s = to_float(data.get("verify_settle_s"), cfg.verify_settle_s)

        cfg.verify_streaming_enabled = bool(data.get("verify_streaming_enabled", cfg.verify_streaming_enabled))
        try:
            cfg.verify_streaming_lag = int(data.get("verify_streaming_lag", cfg.verify_streaming_lag))
        except Exception:
            pass

        cfg.verify_auto_recover_loops = bool(
            data.get("verify_auto_recover_loops", cfg.verify_auto_recover_loops)
        )
        try:
            cfg.verify_auto_recover_after_passes = int(
                data.get("verify_auto_recover_after_passes", cfg.verify_auto_recover_after_passes)
            )
        except Exception:
            pass

        cfg.status_overlay_enabled = bool(data.get("status_overlay_enabled", cfg.status_overlay_enabled))

        pm = data.get("paint_mode", cfg.paint_mode)
        if isinstance(pm, str):
            pm = pm.strip().lower()
            # Back-compat: allow friendly UI strings
            if pm in {"paint by row", "row"}:
                cfg.paint_mode = "row"
            elif pm in {"paint by color", "color", "colour"}:
                cfg.paint_mode = "color"
        else:
            cfg.paint_mode = cfg.paint_mode
        cfg.shades_panel_button_pos = to_tuple2(data.get("shades_panel_button_pos"))
        cfg.back_button_pos = to_tuple2(data.get("back_button_pos"))

        cfg.bucket_fill_enabled = bool(data.get("bucket_fill_enabled", cfg.bucket_fill_enabled))
        try:
            cfg.bucket_fill_min_cells = int(data.get("bucket_fill_min_cells", cfg.bucket_fill_min_cells))
        except Exception:
            pass

        cfg.bucket_fill_regions_enabled = bool(
            data.get("bucket_fill_regions_enabled", cfg.bucket_fill_regions_enabled)
        )
        try:
            cfg.bucket_fill_regions_min_cells = int(
                data.get("bucket_fill_regions_min_cells", cfg.bucket_fill_regions_min_cells)
            )
        except Exception:
            pass

        cfg.paint_tool_button_pos = to_tuple2(data.get("paint_tool_button_pos"))
        cfg.bucket_tool_button_pos = to_tuple2(data.get("bucket_tool_button_pos"))
        cfg.eraser_tool_button_pos = to_tuple2(data.get("eraser_tool_button_pos"))
        cfg.eraser_thickness_up_button_pos = to_tuple2(data.get("eraser_thickness_up_button_pos"))

        cfg.main_colors = []
        for mc in data.get("main_colors", []):
            main = MainColor(
                name=str(mc.get("name", "Unnamed")),
                pos=to_tuple2(mc.get("pos")) or (0, 0),
                rgb=to_rgb(mc.get("rgb", (0, 0, 0))),
                shades=[],
            )
            for sh in mc.get("shades", []):
                main.shades.append(
                    ShadeButton(
                        name=str(sh.get("name", "Shade")),
                        pos=to_tuple2(sh.get("pos")) or (0, 0),
                        rgb=to_rgb(sh.get("rgb", (0, 0, 0))),
                    )
                )
            cfg.main_colors.append(main)
        return cfg


def default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"

    # Keep config next to the repo for now.
    return Path.cwd() / "config.json"


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig.from_json_dict(data)


def save_config(path: Path, cfg: AppConfig) -> None:
    path.write_text(json.dumps(cfg.to_json_dict(), indent=2), encoding="utf-8")
