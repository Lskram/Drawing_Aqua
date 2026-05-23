from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class GameDrawPart:
    id: int
    name: str
    raw_name: str
    width: int
    height: int
    line: int
    row: int
    mask: str = ""


@dataclass(frozen=True)
class GameDrawPreset:
    id: int
    name: str
    raw_name: str
    icon: str
    mask: str
    apply_type: int
    static_id: int
    visible: bool
    parts: Tuple[GameDrawPart, ...]


FALLBACK_PRESETS: Tuple[GameDrawPreset, ...] = (
    GameDrawPreset(
        id=1,
        name="T-Shirt",
        raw_name="T-Shirt",
        icon="",
        mask="",
        apply_type=3,
        static_id=0,
        visible=True,
        parts=(
            GameDrawPart(1, "Front", "Front", 64, 80, 0, 0),
            GameDrawPart(2, "Back", "Back", 64, 80, 64, 0),
            GameDrawPart(3, "Left Sleeve", "Left Sleeve", 64, 48, 0, 80),
            GameDrawPart(4, "Right Sleeve", "Right Sleeve", 64, 48, 64, 80),
        ),
    ),
    GameDrawPreset(
        id=2,
        name="Tank Top",
        raw_name="Tank Top",
        icon="",
        mask="",
        apply_type=3,
        static_id=0,
        visible=True,
        parts=(
            GameDrawPart(5, "Front", "Front", 64, 64, 0, 0),
            GameDrawPart(6, "Back", "Back", 64, 64, 64, 0),
        ),
    ),
)


def _resource_candidates() -> Iterable[Path]:
    module_dir = Path(__file__).resolve().parent
    yield module_dir / "resources" / "heartopia_draw_data.json"
    yield module_dir.parent.parent / "heartopia_draw_data.json"
    yield Path.cwd() / "heartopia_draw_data.json"


def _read_json_file() -> Dict[str, Any] | None:
    for path in _resource_candidates():
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _part_from_dict(data: Dict[str, Any]) -> GameDrawPart:
    return GameDrawPart(
        id=int(data.get("id", 0)),
        name=str(data.get("name") or data.get("raw_name") or "Part"),
        raw_name=str(data.get("raw_name") or data.get("name") or "Part"),
        width=max(1, int(data.get("width", 64))),
        height=max(1, int(data.get("height", 64))),
        line=max(0, int(data.get("line", 0))),
        row=max(0, int(data.get("row", 0))),
        mask=str(data.get("mask", "")),
    )


def _preset_from_dict(data: Dict[str, Any]) -> GameDrawPreset:
    parts = tuple(_part_from_dict(p) for p in data.get("parts", []) if isinstance(p, dict))
    return GameDrawPreset(
        id=int(data.get("id", 0)),
        name=str(data.get("name") or data.get("raw_name") or "Draw Item"),
        raw_name=str(data.get("raw_name") or data.get("name") or "Draw Item"),
        icon=str(data.get("icon", "")),
        mask=str(data.get("mask", "")),
        apply_type=int(data.get("apply_type", 0)),
        static_id=int(data.get("static_id", 0)),
        visible=bool(data.get("visible", True)),
        parts=parts,
    )


def load_game_draw_presets(include_hidden: bool = True) -> Tuple[GameDrawPreset, ...]:
    data = _read_json_file()
    if not data:
        return FALLBACK_PRESETS
    raw_presets = data.get("presets", [])
    presets: List[GameDrawPreset] = []
    for raw in raw_presets:
        if not isinstance(raw, dict):
            continue
        preset = _preset_from_dict(raw)
        if not preset.parts:
            continue
        if not include_hidden and not preset.visible:
            continue
        presets.append(preset)
    return tuple(presets) or FALLBACK_PRESETS


GAME_DRAW_PRESETS: Tuple[GameDrawPreset, ...] = load_game_draw_presets()
GAME_DRAW_PRESET_NAMES: Tuple[str, ...] = tuple(p.name for p in GAME_DRAW_PRESETS)
GAME_DRAW_PRESETS_BY_NAME: Dict[str, GameDrawPreset] = {p.name: p for p in GAME_DRAW_PRESETS}
GAME_DRAW_PARTS_BY_PRESET: Dict[str, Dict[str, Tuple[int, int]]] = {
    preset.name: {part.name: (part.width, part.height) for part in preset.parts}
    for preset in GAME_DRAW_PRESETS
}


def is_game_draw_preset(name: str) -> bool:
    return name in GAME_DRAW_PRESETS_BY_NAME


def game_draw_part_names(preset_name: str) -> List[str]:
    preset = GAME_DRAW_PRESETS_BY_NAME.get(preset_name)
    if not preset:
        return []
    return [part.name for part in preset.parts]


def game_draw_part_size(preset_name: str, part_name: str) -> Tuple[int, int] | None:
    preset = GAME_DRAW_PRESETS_BY_NAME.get(preset_name)
    if not preset:
        return None
    for part in preset.parts:
        if part.name == part_name:
            return (part.width, part.height)
    return None

