from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


DRAW_CANVAS = 237
DRAW_CUSTOM = 238
DRAW_SEGMENT = 244

DEFAULT_BUNDLES = (
    Path.home() / "AppData/LocalLow/xd/Heartopia/AssetBundle/46df6d27adea_oversea.ab",
    Path("D:/TapTapGlobal/Apps/231364/xdt_Data/StreamingAssets/AssetBundle/46df6d27adea_oversea.ab"),
)

PRESET_NAME_MAP = {
    "短袖T恤": "T-Shirt",
    "背心": "Tank Top",
    "短裙": "Mini Skirt",
    "短裤": "Shorts",
    "渔夫帽": "Bucket Hat",
    "卫衣": "Hoodie",
    "长裤": "Pants",
    "连衣裙": "Dress",
    "棒球帽": "Baseball Cap",
    "帆布鞋": "Canvas Shoes",
    "玛丽珍鞋": "Mary Jane Shoes",
    "拼木单人床": "Wooden Single Bed",
    "拼木双人床": "Wooden Double Bed",
    "拼木衣柜": "Wooden Wardrobe",
    "拼木床头柜": "Wooden Nightstand",
    "拼木台灯": "Wooden Table Lamp",
    "拼木椅子": "Wooden Chair",
    "拼木茶几": "Wooden Tea Table",
    "拼木双人沙发": "Wooden Loveseat",
    "拼木单人沙发": "Wooden Armchair",
    "拼木落地灯": "Wooden Floor Lamp",
    "圣诞袜": "Christmas Stocking",
    "手绘彩蛋": "Painted Egg",
}

PART_NAME_MAP = {
    "前片": "Front",
    "后片": "Back",
    "左袖": "Left Sleeve",
    "右袖": "Right Sleeve",
    "袖子": "Sleeve",
    "前帽檐": "Front Brim",
    "后帽檐": "Back Brim",
    "帽顶": "Crown",
    "内搭": "Innerwear",
    "后片与侧片": "Back and Side",
    "帽檐": "Brim",
    "鞋身": "Upper",
    "鞋头与鞋带": "Toe and Laces",
    "鞋底": "Sole",
    "被面": "Quilt",
    "床沿": "Bed Frame",
    "柜门": "Cabinet Doors",
    "柜面": "Cabinet Front",
    "灯罩前片": "Lampshade Front",
    "灯罩后片": "Lampshade Back",
    "底座边缘": "Base Edge",
    "椅背前片": "Chair Back Front",
    "椅背后片": "Chair Back Back",
    "座椅表面": "Seat Surface",
    "茶几台面": "Table Top",
    "沙发靠背": "Sofa Back",
    "沙发座面": "Sofa Seat",
}


class Reader:
    def __init__(self, data: bytes):
        self.data = data

    def u8(self, offset: int) -> Tuple[int, int]:
        return self.data[offset], offset + 1

    def bool(self, offset: int) -> Tuple[bool, int]:
        value, offset = self.u8(offset)
        return bool(value), offset

    def u16(self, offset: int) -> Tuple[int, int]:
        return struct.unpack_from("<H", self.data, offset)[0], offset + 2

    def i32(self, offset: int) -> Tuple[int, int]:
        return struct.unpack_from("<i", self.data, offset)[0], offset + 4

    def u32(self, offset: int) -> Tuple[int, int]:
        return struct.unpack_from("<I", self.data, offset)[0], offset + 4

    def utf8(self, offset: int) -> Tuple[str, int]:
        size, offset = self.u16(offset)
        raw = self.data[offset : offset + size]
        return raw.decode("utf-8", errors="replace"), offset + size

    def expression_by_index(self, offset: int) -> int:
        flag, offset = self.u8(offset)
        if flag == 1:
            _, offset = self.u32(offset)
        return offset


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _install_unity_patch() -> None:
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import heartopia_unitycn

    heartopia_unitycn.install_unitycn_patch()


def _find_bundle(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Bundle not found: {path}")
    for path in DEFAULT_BUNDLES:
        if path.exists():
            return path
    raise FileNotFoundError("Could not find Heartopia oversea table bundle.")


def _load_table_bytes(bundle_path: Path) -> bytes:
    _install_unity_patch()
    import UnityPy

    env = UnityPy.load(str(bundle_path))
    for obj in env.objects:
        data = obj.read()
        if getattr(data, "m_Name", "") == "oversea" and hasattr(data, "m_Script"):
            script = data.m_Script
            if isinstance(script, bytes):
                return script
            return script.encode("utf-8", errors="surrogateescape")
    raise RuntimeError("TextAsset 'oversea' was not found in bundle.")


def _skip_expression_pool(reader: Reader) -> Tuple[str, int]:
    offset = 0
    version, offset = reader.utf8(offset)
    count, offset = reader.i32(offset)
    for _ in range(count):
        _, offset = reader.utf8(offset)
    return version, offset


def _section_header(reader: Reader, offset: int, expected_type: int) -> Tuple[int, int]:
    table_type, offset = reader.u16(offset)
    if table_type != expected_type:
        raise ValueError(f"Unexpected table type {table_type}; expected {expected_type}")
    count, offset = reader.u16(offset)
    has_key, offset = reader.bool(offset)
    if has_key:
        _, offset = reader.i32(offset)
    return count, offset


def parse_draw_canvas(reader: Reader, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    count, offset = _section_header(reader, offset, DRAW_CANVAS)
    rows: List[Dict[str, Any]] = []
    for _ in range(count):
        row_id, offset = reader.i32(offset)
        canvas_type, offset = reader.utf8(offset)
        custom_id, offset = reader.i32(offset)
        width, offset = reader.u16(offset)
        height, offset = reader.u16(offset)
        icon, offset = reader.utf8(offset)
        stage, offset = reader.u8(offset)
        rows.append(
            {
                "id": row_id,
                "canvas_type": canvas_type,
                "custom_id": custom_id,
                "width": width,
                "height": height,
                "icon": icon,
                "stage": stage,
            }
        )
    return rows, offset


def parse_draw_custom(reader: Reader, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    count, offset = _section_header(reader, offset, DRAW_CUSTOM)
    rows: List[Dict[str, Any]] = []
    for _ in range(count):
        row_id, offset = reader.i32(offset)
        describe, offset = reader.utf8(offset)
        offset = reader.expression_by_index(offset)
        appear_date_id, offset = reader.i32(offset)
        static_id, offset = reader.i32(offset)
        visible, offset = reader.bool(offset)
        cost_count, offset = reader.u8(offset)
        offset += int(cost_count) * 12
        apply_type, offset = reader.u8(offset)
        custom_type, offset = reader.utf8(offset)
        icon, offset = reader.utf8(offset)
        mask, offset = reader.utf8(offset)
        part_count, offset = reader.u8(offset)
        part_ids: List[int] = []
        for _ in range(part_count):
            part_id, offset = reader.i32(offset)
            part_ids.append(part_id)
        meshfile, offset = reader.utf8(offset)
        rows.append(
            {
                "id": row_id,
                "raw_name": custom_type or describe,
                "raw_describe": describe,
                "name": PRESET_NAME_MAP.get(custom_type or describe, custom_type or describe),
                "icon": icon,
                "mask": mask,
                "part_ids": part_ids,
                "static_id": static_id,
                "meshfile": meshfile,
                "visible": visible,
                "appear_date_id": appear_date_id,
                "apply_type": apply_type,
            }
        )
    return rows, offset


def parse_draw_segment(reader: Reader, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    count, offset = _section_header(reader, offset, DRAW_SEGMENT)
    rows: List[Dict[str, Any]] = []
    for _ in range(count):
        row_id, offset = reader.i32(offset)
        raw_name, offset = reader.utf8(offset)
        width, offset = reader.u16(offset)
        height, offset = reader.u8(offset)
        line, offset = reader.u8(offset)
        row, offset = reader.u8(offset)
        mask, offset = reader.utf8(offset)
        rows.append(
            {
                "id": row_id,
                "raw_name": raw_name,
                "name": PART_NAME_MAP.get(raw_name, raw_name),
                "width": width,
                "height": height,
                "line": line,
                "row": row,
                "mask": mask,
            }
        )
    return rows, offset


def _next_table_type(reader: Reader, offset: int) -> int | None:
    if offset + 2 > len(reader.data):
        return None
    return struct.unpack_from("<H", reader.data, offset)[0]


def _scan_section(reader: Reader, start_offset: int, table_type: int, parser, expected_next: int | None = None) -> Tuple[List[Dict[str, Any]], int, int]:
    marker = struct.pack("<H", table_type)
    pos = max(0, start_offset)
    while True:
        found = reader.data.find(marker, pos)
        if found < 0:
            raise RuntimeError(f"Could not locate table type {table_type}")
        try:
            rows, end = parser(reader, found)
            if rows and (expected_next is None or _next_table_type(reader, end) == expected_next):
                return rows, found, end
        except Exception:
            pass
        pos = found + 1


def _unique_part_names(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for part in parts:
        item = dict(part)
        name = str(item.get("name") or item.get("raw_name") or "Part")
        count = seen.get(name, 0) + 1
        seen[name] = count
        if count > 1:
            item["name"] = f"{name} {count}"
        out.append(item)
    return out


def extract_draw_data(bundle_path: Path) -> Dict[str, Any]:
    raw = _load_table_bytes(bundle_path)
    reader = Reader(raw)
    version, data_start = _skip_expression_pool(reader)
    canvases, canvas_offset, canvas_end = _scan_section(reader, data_start, DRAW_CANVAS, parse_draw_canvas, DRAW_CUSTOM)
    customs, custom_offset, custom_end = _scan_section(reader, canvas_end, DRAW_CUSTOM, parse_draw_custom, 239)
    segments, segment_offset, segment_end = _scan_section(reader, custom_end, DRAW_SEGMENT, parse_draw_segment, 245)

    segment_by_id = {int(segment["id"]): segment for segment in segments}
    presets: List[Dict[str, Any]] = []
    for custom in customs:
        parts = []
        for part_id in custom["part_ids"]:
            part = segment_by_id.get(int(part_id))
            if part:
                parts.append(part)
        preset = dict(custom)
        preset["parts"] = _unique_part_names(parts)
        del preset["part_ids"]
        presets.append(preset)

    return {
        "schema": 1,
        "source_bundle": str(bundle_path),
        "table_asset": "Assets/resource_index/binary/table/oversea.bytes",
        "table_version": version,
        "offsets": {
            "data_start": data_start,
            "draw_canvas": canvas_offset,
            "draw_custom": custom_offset,
            "draw_segment": segment_offset,
            "draw_canvas_end": canvas_end,
            "draw_custom_end": custom_end,
            "draw_segment_end": segment_end,
        },
        "canvas": canvases,
        "segments": segments,
        "presets": presets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Heartopia drawing canvas and clothing sizes from game tables.")
    parser.add_argument("--bundle", help="Path to 46df6d27adea_oversea.ab")
    parser.add_argument("--output", default=str(_project_root() / "src/heartopia_painter/resources/heartopia_draw_data.json"))
    args = parser.parse_args()

    bundle_path = _find_bundle(args.bundle)
    data = extract_draw_data(bundle_path)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Presets: {len(data['presets'])}, segments: {len(data['segments'])}, canvas rows: {len(data['canvas'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

