from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw


RGB = Tuple[int, int, int]


@dataclass
class PixelGrid:
    w: int
    h: int
    pixels: List[RGB]  # row-major
    paint_mask: Optional[List[bool]] = None

    def get(self, x: int, y: int) -> RGB:
        return self.pixels[y * self.w + x]

    def should_paint(self, x: int, y: int) -> bool:
        if self.paint_mask is None:
            return True
        idx = y * self.w + x
        return 0 <= idx < len(self.paint_mask) and bool(self.paint_mask[idx])

    @property
    def paint_count(self) -> int:
        if self.paint_mask is None:
            return self.w * self.h
        return sum(1 for v in self.paint_mask if v)


@dataclass
class ImagePrepOptions:
    fit_mode: str = "Stretch"
    auto_crop: bool = False
    palette_map: bool = False
    dither: bool = False
    background_rgb: RGB = (255, 255, 255)
    content_rect: Optional[Tuple[float, float, float, float]] = None
    paint_mask_shape: str = "none"
    mask_image_path: Optional[str] = None
    mask_content_rect: Optional[Tuple[float, float, float, float]] = None
    ignore_source_alpha: bool = False
    skeleton_row_warp: bool = False
    skeleton_warp_strength: float = 1.0
    skeleton_edge_padding: int = 0


def _clamp_channel(v: float) -> int:
    return max(0, min(255, int(round(v))))


def _normalize_fit_mode(mode: str) -> str:
    mode = (mode or "Stretch").strip().lower()
    if mode in {"smart", "stretch", "contain", "cover"}:
        return mode
    return "stretch"


def _composite_over_background(img: Image.Image, background_rgb: RGB) -> Image.Image:
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (*background_rgb, 255))
    return Image.alpha_composite(bg, rgba).convert("RGB")


def _auto_crop(img: Image.Image, background_rgb: RGB) -> Image.Image:
    rgba = img.convert("RGBA")

    alpha = rgba.getchannel("A")
    has_transparency = alpha.getextrema()[0] < 250
    if has_transparency:
        mask = alpha.point(lambda a: 255 if a > 8 else 0)
        bbox = mask.getbbox()
        if bbox is not None:
            return rgba.crop(bbox)
        return rgba

    # Opaque images often have large white borders. Trim only near the configured
    # background color, and only when the trim is meaningful.
    rgb = rgba.convert("RGB")
    bg = Image.new("RGB", rgb.size, background_rgb)
    diff = ImageChops.difference(rgb, bg).convert("L")
    mask = diff.point(lambda v: 255 if v > 10 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return rgba

    old_area = rgba.size[0] * rgba.size[1]
    new_area = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    if new_area < old_area * 0.98:
        return rgba.crop(bbox)
    return rgba


def _resize_with_fit(img: Image.Image, w: int, h: int, fit_mode: str, background_rgb: RGB) -> Image.Image:
    fit_mode = _normalize_fit_mode(fit_mode)
    if fit_mode == "smart":
        fit_mode = "contain"

    rgba = img.convert("RGBA")
    if fit_mode == "stretch":
        return rgba.resize((w, h), resample=Image.Resampling.LANCZOS)

    sw, sh = rgba.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGBA", (w, h), (*background_rgb, 255))

    if fit_mode == "cover":
        scale = max(w / sw, h / sh)
    else:
        scale = min(w / sw, h / sh)

    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = rgba.resize((nw, nh), resample=Image.Resampling.LANCZOS)

    if fit_mode == "cover":
        left = max(0, int(round((nw - w) / 2)))
        top = max(0, int(round((nh - h) / 2)))
        return resized.crop((left, top, left + w, top + h))

    canvas = Image.new("RGBA", (w, h), (*background_rgb, 255))
    x = int(round((w - nw) / 2))
    y = int(round((h - nh) / 2))
    canvas.alpha_composite(resized, (x, y))
    return canvas


def _ratio_rect_to_pixels(
    w: int,
    h: int,
    rect: Optional[Tuple[float, float, float, float]],
) -> Tuple[int, int, int, int]:
    if rect is None:
        return (0, 0, int(w), int(h))
    rx, ry, rw, rh = rect
    x = int(round(float(rx) * w))
    y = int(round(float(ry) * h))
    ww = int(round(max(0.01, float(rw)) * w))
    hh = int(round(max(0.01, float(rh)) * h))
    return (x, y, max(1, ww), max(1, hh))


def _resize_into_content_rect(
    img: Image.Image,
    w: int,
    h: int,
    fit_mode: str,
    background_rgb: RGB,
    content_rect: Optional[Tuple[float, float, float, float]],
) -> Image.Image:
    if content_rect is None:
        return _resize_with_fit(img, w, h, fit_mode, background_rgb)

    x, y, ww, hh = _ratio_rect_to_pixels(w, h, content_rect)
    fitted = _resize_with_fit(img, ww, hh, fit_mode, background_rgb)
    canvas = Image.new("RGBA", (w, h), (*background_rgb, 0))
    fitted = fitted.convert("RGBA")
    canvas.paste(fitted, (x, y), fitted)
    return canvas


def _part_mask(w: int, h: int, shape: str) -> Image.Image:
    shape = (shape or "none").strip().lower()
    mask = Image.new("L", (w, h), 255)
    if shape in {"", "none", "rect", "rectangle"}:
        return mask

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    def pts(items: Sequence[Tuple[float, float]]) -> List[Tuple[int, int]]:
        return [(int(round(x * (w - 1))), int(round(y * (h - 1)))) for x, y in items]

    if shape in {"dress_front", "dress_back"}:
        # Front/back dress outline calibrated from an in-game 438x660 canvas
        # screenshot mapped back to the 128x160 part grid. The top straps sit
        # at x=31..43 and x=84..96; the previous approximation used x=38..50
        # and x=77..89, which clipped the shoulder/strap areas inward.
        draw.polygon(
            pts(
                [
                    (0.09, 0.96),
                    (0.09, 0.28),
                    (0.24, 0.28),
                    (0.24, 0.24),
                    (0.24, 0.04),
                    (0.34, 0.04),
                    (0.34, 0.10),
                    (0.43, 0.15),
                    (0.48, 0.18),
                    (0.50, 0.08),
                    (0.52, 0.18),
                    (0.57, 0.15),
                    (0.66, 0.10),
                    (0.66, 0.04),
                    (0.76, 0.04),
                    (0.76, 0.24),
                    (0.76, 0.28),
                    (0.91, 0.28),
                    (0.91, 0.96),
                ]
            ),
            fill=255,
        )
    elif shape == "dress_innerwear":
        draw.polygon(
            pts(
                [
                    (0.34, 0.06),
                    (0.66, 0.06),
                    (0.74, 0.28),
                    (0.70, 0.94),
                    (0.30, 0.94),
                    (0.26, 0.28),
                ]
            ),
            fill=255,
        )
    else:
        mask = Image.new("L", (w, h), 255)
    return mask


def _resize_mask_into_content_rect(
    mask: Image.Image,
    w: int,
    h: int,
    content_rect: Optional[Tuple[float, float, float, float]],
) -> Image.Image:
    mask = mask.convert("L")
    if content_rect is None:
        if mask.size != (w, h):
            mask = mask.resize((w, h), resample=Image.Resampling.LANCZOS)
        return mask.point(lambda v: 255 if v > 8 else 0)

    x, y, ww, hh = _ratio_rect_to_pixels(w, h, content_rect)
    resized = mask.resize((ww, hh), resample=Image.Resampling.LANCZOS)
    canvas = Image.new("L", (w, h), 0)
    canvas.paste(resized, (x, y))
    return canvas.point(lambda v: 255 if v > 8 else 0)


def _mask_from_image(
    path: str,
    w: int,
    h: int,
    background_rgb: RGB,
    mask_content_rect: Optional[Tuple[float, float, float, float]] = None,
) -> Image.Image:
    src = Image.open(path).convert("RGBA")
    alpha = src.getchannel("A")
    if alpha.getextrema()[0] < 250:
        return _resize_mask_into_content_rect(
            alpha.point(lambda a: 255 if a > 8 else 0),
            w,
            h,
            mask_content_rect,
        )

    # Fallback for non-transparent mask images: treat pixels that differ from
    # the configured background color as drawable.
    rgb = src.convert("RGB")
    bg = Image.new("RGB", rgb.size, background_rgb)
    diff = ImageChops.difference(rgb, bg).convert("L")
    return _resize_mask_into_content_rect(
        diff.point(lambda v: 255 if v > 10 else 0),
        w,
        h,
        mask_content_rect,
    )


def _apply_paint_mask(
    img: Image.Image,
    shape: str,
    mask_image_path: Optional[str],
    mask_content_rect: Optional[Tuple[float, float, float, float]],
    background_rgb: RGB,
    ignore_source_alpha: bool,
    skeleton_row_warp: bool = False,
    skeleton_warp_strength: float = 1.0,
    skeleton_edge_padding: int = 0,
) -> Tuple[Image.Image, List[bool]]:
    rgba = img.convert("RGBA")
    alpha = Image.new("L", rgba.size, 255) if ignore_source_alpha else rgba.getchannel("A")
    shape_mask = _part_mask(rgba.width, rgba.height, shape)
    combined = ImageChops.multiply(alpha, shape_mask)
    if mask_image_path:
        try:
            image_mask = _mask_from_image(
                mask_image_path,
                rgba.width,
                rgba.height,
                background_rgb,
                mask_content_rect,
            )
            combined = ImageChops.multiply(combined, image_mask)
        except Exception:
            pass
    if skeleton_row_warp:
        rgba = _apply_skeleton_row_warp(
            rgba,
            combined,
            background_rgb,
            strength=float(skeleton_warp_strength),
            edge_padding=int(skeleton_edge_padding),
        )
    rgba.putalpha(combined)
    paint_mask = [a > 8 for a in combined.getdata()]
    return rgba, paint_mask


def _apply_skeleton_row_warp(
    img: Image.Image,
    mask: Image.Image,
    background_rgb: RGB,
    strength: float,
    edge_padding: int,
) -> Image.Image:
    src = img.convert("RGBA")
    active = mask.convert("L")
    w, h = src.size
    if w <= 1 or h <= 0:
        return src

    strength = max(0.0, min(1.0, float(strength)))
    pad = int(edge_padding)
    out = Image.new("RGBA", (w, h), (*background_rgb, 0))
    src_px = src.load()
    mask_px = active.load()
    out_px = out.load()

    for y in range(h):
        left = None
        right = None
        for x in range(w):
            if mask_px[x, y] > 8:
                if left is None:
                    left = x
                right = x
        if left is None or right is None:
            continue

        left = max(0, min(w - 1, left + pad))
        right = max(0, min(w - 1, right - pad))
        if right < left:
            mid = max(0, min(w - 1, int(round((left + right) / 2))))
            left = right = mid
        span = max(1, right - left)

        for x in range(w):
            if mask_px[x, y] <= 8:
                continue
            if x <= left:
                mapped_x = 0.0
            elif x >= right:
                mapped_x = float(w - 1)
            else:
                mapped_x = ((x - left) / span) * (w - 1)
            sample_x = int(round((float(x) * (1.0 - strength)) + (mapped_x * strength)))
            sample_x = max(0, min(w - 1, sample_x))
            out_px[x, y] = src_px[sample_x, y]

    return out


def _nearest_palette_color(rgb: Sequence[float], palette: Sequence[RGB]) -> RGB:
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    best = palette[0]
    best_d = None
    for pr, pg, pb in palette:
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_d is None or d < best_d:
            best_d = d
            best = (int(pr), int(pg), int(pb))
    return best


def _palette_map_image(img: Image.Image, palette: Sequence[RGB], dither: bool) -> Image.Image:
    if not palette:
        return img.convert("RGB")

    src = img.convert("RGB")
    w, h = src.size

    if not dither:
        out = Image.new("RGB", (w, h))
        out.putdata([_nearest_palette_color(px, palette) for px in src.getdata()])
        return out

    pixels = [
        [[float(r), float(g), float(b)] for (r, g, b) in src.crop((0, y, w, y + 1)).getdata()]
        for y in range(h)
    ]

    out_rows: List[List[RGB]] = [[(0, 0, 0) for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            old = pixels[y][x]
            new = _nearest_palette_color(old, palette)
            out_rows[y][x] = new
            err = [old[i] - new[i] for i in range(3)]

            def add_err(xx: int, yy: int, factor: float) -> None:
                if 0 <= xx < w and 0 <= yy < h:
                    for i in range(3):
                        pixels[yy][xx][i] = max(0.0, min(255.0, pixels[yy][xx][i] + err[i] * factor))

            add_err(x + 1, y, 7 / 16)
            add_err(x - 1, y + 1, 3 / 16)
            add_err(x, y + 1, 5 / 16)
            add_err(x + 1, y + 1, 1 / 16)

    out = Image.new("RGB", (w, h))
    out.putdata([px for row in out_rows for px in row])
    return out


def load_and_resize_to_grid(
    path: str,
    w: int,
    h: int,
    prep: Optional[ImagePrepOptions] = None,
    palette_rgbs: Optional[Sequence[RGB]] = None,
) -> PixelGrid:
    prep = prep or ImagePrepOptions()
    bg_rgb = tuple(int(c) for c in getattr(prep, "background_rgb", (255, 255, 255)))  # type: ignore[arg-type]
    img = Image.open(path).convert("RGBA")

    if bool(getattr(prep, "auto_crop", False)):
        img = _auto_crop(img, bg_rgb)  # type: ignore[arg-type]

    img = _resize_into_content_rect(
        img,
        w,
        h,
        str(getattr(prep, "fit_mode", "Stretch")),
        bg_rgb,  # type: ignore[arg-type]
        getattr(prep, "content_rect", None),
    )
    img, paint_mask = _apply_paint_mask(
        img,
        str(getattr(prep, "paint_mask_shape", "none")),
        getattr(prep, "mask_image_path", None),
        getattr(prep, "mask_content_rect", None),
        bg_rgb,  # type: ignore[arg-type]
        bool(getattr(prep, "ignore_source_alpha", False)),
        bool(getattr(prep, "skeleton_row_warp", False)),
        float(getattr(prep, "skeleton_warp_strength", 1.0)),
        int(getattr(prep, "skeleton_edge_padding", 0)),
    )
    img = _composite_over_background(img, bg_rgb)  # type: ignore[arg-type]

    if bool(getattr(prep, "palette_map", False)) and palette_rgbs:
        img = _palette_map_image(img, palette_rgbs, bool(getattr(prep, "dither", False)))

    pixels = list(img.getdata())
    return PixelGrid(
        w=w,
        h=h,
        pixels=[(int(r), int(g), int(b)) for (r, g, b) in pixels],
        paint_mask=paint_mask,
    )
