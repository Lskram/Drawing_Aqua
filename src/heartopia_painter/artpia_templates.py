from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw


RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]


DATA_PATH = Path(__file__).resolve().parent / "resources" / "artpia_template_data.json"


LOCAL_PRESET_ALIASES: dict[str, tuple[str, ...]] = {
    "Hoodie": ("Sweatshirt",),
    "Baseball Cap": ("Cap",),
    "Canvas Shoes": ("Shoes",),
    "Mary Jane Shoes": ("Mary Jane",),
    "Wooden Single Bed": ("Single Bed",),
    "Wooden Double Bed": ("Double Bed",),
    "Wooden Wardrobe": ("Closet",),
    "Wooden Nightstand": ("Nightstand",),
    "Wooden Table Lamp": ("Table Lamp",),
    "Wooden Chair": ("Chair",),
    "Wooden Tea Table": ("Low Table",),
    "Wooden Loveseat": ("Double Sofa",),
    "Wooden Armchair": ("Single Sofa",),
    "Wooden Floor Lamp": ("Floor Lamp",),
}


LOCAL_PART_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("Bucket Hat", "Crown"): ("Top",),
    ("Dress", "Innerwear"): ("Inner",),
    ("Baseball Cap", "Back and Side"): ("Back + Side",),
    ("Baseball Cap", "Brim"): ("Front Brim",),
    ("Canvas Shoes", "Toe and Laces"): ("Toe + Laces",),
    ("Wooden Single Bed", "Quilt"): ("Bedding Front",),
    ("Wooden Double Bed", "Quilt"): ("Bedding Front",),
    ("Wooden Wardrobe", "Cabinet Doors"): ("Default",),
    ("Wooden Table Lamp", "Lampshade Front"): ("Shade Front",),
    ("Wooden Table Lamp", "Lampshade Back"): ("Shade Back",),
    ("Wooden Table Lamp", "Base Edge"): ("Base Rim",),
    ("Wooden Chair", "Chair Back Front"): ("Backrest Front",),
    ("Wooden Chair", "Chair Back Back"): ("Backrest Back",),
    ("Wooden Chair", "Seat Surface"): ("Seat",),
    ("Wooden Tea Table", "Table Top"): ("Default",),
    ("Wooden Loveseat", "Sofa Back"): ("Backrest",),
    ("Wooden Loveseat", "Sofa Seat"): ("Seat",),
    ("Wooden Armchair", "Sofa Back"): ("Backrest",),
    ("Wooden Armchair", "Sofa Seat"): ("Seat",),
    ("Wooden Floor Lamp", "Lampshade Front"): ("Shade Front",),
    ("Wooden Floor Lamp", "Lampshade Back"): ("Shade Back",),
    ("Wooden Floor Lamp", "Base Edge"): ("Base Rim",),
}


@dataclass(frozen=True)
class ArtPiaPartTemplate:
    preset_name: str
    part_name: str
    width: int
    height: int
    disabled_row_ranges: tuple[tuple[tuple[int, int], ...], ...]
    mask_lines: tuple[Any, ...]
    source_preset_id: str
    source_part_id: str
    source_preset_name: str
    source_part_name: str

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())


def _safe_stem(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(text).strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "template"


@lru_cache(maxsize=1)
def _load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {"presets": []}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _localized_names(item: dict[str, Any]) -> Iterable[str]:
    yield str(item.get("name") or "")
    yield str(item.get("raw_name") or "")
    names = item.get("names")
    if isinstance(names, dict):
        for value in names.values():
            yield str(value)


def _target_names(name: str, aliases: dict[str, tuple[str, ...]]) -> set[str]:
    return {_norm(value) for value in (name, *aliases.get(name, ())) if value}


def _matches(item: dict[str, Any], targets: set[str]) -> bool:
    return any(_norm(name) in targets for name in _localized_names(item))


def _ranges_to_tuple(rows: Iterable[Iterable[Iterable[int]]]) -> tuple[tuple[tuple[int, int], ...], ...]:
    out: list[tuple[tuple[int, int], ...]] = []
    for row in rows:
        row_ranges: list[tuple[int, int]] = []
        for pair in row:
            try:
                start, end = int(pair[0]), int(pair[1])
            except Exception:
                continue
            row_ranges.append((start, end))
        out.append(tuple(row_ranges))
    return tuple(out)


def find_artpia_part_template(preset_name: str, part_name: str) -> ArtPiaPartTemplate | None:
    data = _load_data()
    preset_targets = _target_names(preset_name, LOCAL_PRESET_ALIASES)
    part_targets = _target_names(part_name, LOCAL_PART_ALIASES)
    for alias in LOCAL_PART_ALIASES.get((preset_name, part_name), ()):
        part_targets.add(_norm(alias))

    for preset in data.get("presets", []):
        if not isinstance(preset, dict) or not _matches(preset, preset_targets):
            continue
        for part in preset.get("parts", []):
            if not isinstance(part, dict) or not _matches(part, part_targets):
                continue
            try:
                width, height = int(part["width"]), int(part["height"])
            except Exception:
                continue
            return ArtPiaPartTemplate(
                preset_name=str(preset_name),
                part_name=str(part_name),
                width=width,
                height=height,
                disabled_row_ranges=_ranges_to_tuple(part.get("disabled_row_ranges") or []),
                mask_lines=tuple(part.get("mask_lines") or ()),
                source_preset_id=str(preset.get("id") or ""),
                source_part_id=str(part.get("id") or ""),
                source_preset_name=str(preset.get("name") or preset_name),
                source_part_name=str(part.get("name") or part_name),
            )
    return None


def _enabled_bitmap(template: ArtPiaPartTemplate) -> list[bool]:
    w, h = template.width, template.height
    enabled = [True] * (w * h)
    for y, ranges in enumerate(template.disabled_row_ranges[:h]):
        for start, end in ranges:
            for x in range(max(0, start), min(w - 1, end) + 1):
                enabled[y * w + x] = False
    return enabled


def build_artpia_mask_image(template: ArtPiaPartTemplate) -> Image.Image:
    enabled = _enabled_bitmap(template)
    data = [
        (255, 255, 255, 255) if value else (255, 255, 255, 0)
        for value in enabled
    ]
    img = Image.new("RGBA", template.size, (255, 255, 255, 0))
    img.putdata(data)
    return img


def _draw_drawable_fill(draw: ImageDraw.ImageDraw, template: ArtPiaPartTemplate, scale: int, fill: RGBA) -> None:
    w, h = template.width, template.height
    disabled_by_row = [list(row) for row in template.disabled_row_ranges]
    for y in range(h):
        x = 0
        disabled = disabled_by_row[y] if y < len(disabled_by_row) else []
        for start, end in disabled:
            if x < start:
                draw.rectangle((x * scale, y * scale, start * scale - 1, (y + 1) * scale - 1), fill=fill)
            x = max(x, end + 1)
        if x < w:
            draw.rectangle((x * scale, y * scale, w * scale - 1, (y + 1) * scale - 1), fill=fill)


def _draw_pixel_boundary(
    draw: ImageDraw.ImageDraw,
    template: ArtPiaPartTemplate,
    enabled: list[bool],
    scale: int,
    fill: RGBA,
) -> None:
    w, h = template.width, template.height
    line_w = max(1, scale // 5)

    def active(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h and enabled[y * w + x]

    for y in range(h):
        for x in range(w):
            if not active(x, y):
                continue
            x0, y0 = x * scale, y * scale
            x1, y1 = (x + 1) * scale - 1, (y + 1) * scale - 1
            if not active(x, y - 1):
                draw.rectangle((x0, y0, x1, y0 + line_w - 1), fill=fill)
            if not active(x, y + 1):
                draw.rectangle((x0, y1 - line_w + 1, x1, y1), fill=fill)
            if not active(x - 1, y):
                draw.rectangle((x0, y0, x0 + line_w - 1, y1), fill=fill)
            if not active(x + 1, y):
                draw.rectangle((x1 - line_w + 1, y0, x1, y1), fill=fill)


def _draw_mask_lines(draw: ImageDraw.ImageDraw, template: ArtPiaPartTemplate, scale: int, fill: RGBA) -> None:
    width = max(1, scale // 4)
    for segment in template.mask_lines:
        points: list[tuple[int, int]] = []
        if not isinstance(segment, list):
            continue
        for point in segment:
            if not isinstance(point, dict):
                continue
            try:
                x = int(round(float(point.get("x", 0)) * scale))
                y = int(round(float(point.get("y", 0)) * scale))
            except Exception:
                continue
            points.append((x, y))
        if len(points) >= 2:
            draw.line(points, fill=fill, width=width)


def build_artpia_guide_image(
    template: ArtPiaPartTemplate,
    scale: int = 10,
    fill: RGBA = (246, 246, 246, 255),
    outline: RGBA = (18, 18, 18, 255),
) -> Image.Image:
    scale = max(1, int(scale))
    img = Image.new("RGBA", (template.width * scale, template.height * scale), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    enabled = _enabled_bitmap(template)
    _draw_drawable_fill(draw, template, scale, fill)
    _draw_pixel_boundary(draw, template, enabled, scale, outline)
    _draw_mask_lines(draw, template, scale, outline)
    return img


def save_artpia_mask_file(template: ArtPiaPartTemplate, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    build_artpia_mask_image(template).save(path)
    return path


def save_artpia_template_files(
    preset_name: str,
    part_name: str,
    output_dir: Path,
    scale: int = 10,
) -> dict[str, Path]:
    template = find_artpia_part_template(preset_name, part_name)
    if template is None:
        raise RuntimeError(f"No Art-pia template data for {preset_name} / {part_name}.")

    output_dir.mkdir(parents=True, exist_ok=True)
    native_name = f"{_safe_stem(preset_name)}__{_safe_stem(part_name)}__{template.width}x{template.height}"
    scaled_name = (
        f"{_safe_stem(preset_name)}__{_safe_stem(part_name)}__"
        f"{template.width * scale}x{template.height * scale}"
    )
    mask_path = output_dir / f"{native_name}__artpia_mask.png"
    guide_path = output_dir / f"{scaled_name}__artpia_guide.png"
    save_artpia_mask_file(template, mask_path)
    build_artpia_guide_image(template, scale=scale).save(guide_path)
    return {"mask": mask_path, "guide": guide_path}
