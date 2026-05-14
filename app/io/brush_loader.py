"""Brush preset loader.

Scans the top-level ``Brushes/`` folder for ``.json`` preset files.
Each subfolder is treated as a *category*; the folder name becomes the
submenu label in the brush picker.  Files at the root of ``Brushes/``
fall into an implicit "Basic" category.

Preset JSON schema (all keys optional except ``name``):

    {
        "name":     "Soft Round",   // display label
        "icon":     "?",            // single emoji / char shown in menu
        "size":     30,             // brush_size  (px, default 20)
        "hardness": 0.0,            // 0-1, default 0.8
        "opacity":  0.8,            // 0-1, default 1.0
        "spacing":  0.05            // fraction of size, default 0.05
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BrushPreset:
    name: str
    category: str
    icon: str = "???"
    size: int = 20
    hardness: float = 0.8
    opacity: float = 1.0
    spacing: float = 0.05
    tool: str = ""  # empty = default Brush tool; otherwise the tool name to activate


def load_brush_presets(brushes_dir: Path) -> dict[str, list[BrushPreset]]:
    """Return ``{category: [BrushPreset, ...]}`` ordered by subfolder then filename.

    Files directly inside ``brushes_dir`` (not in a subfolder) are placed
    in a category named ``"Basic"``.
    """
    result: dict[str, list[BrushPreset]] = {}
    if not brushes_dir.exists():
        return result

    def _load_file(path: Path, category: str) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        preset = BrushPreset(
            name=data.get("name", path.stem.replace("_", " ").title()),
            category=category,
            icon=data.get("icon", "???"),
            size=max(1, int(data.get("size", 20))),
            hardness=max(0.0, min(1.0, float(data.get("hardness", 0.8)))),
            opacity=max(0.01, min(1.0, float(data.get("opacity", 1.0)))),
            spacing=max(0.01, min(5.0, float(data.get("spacing", 0.05)))),
            tool=str(data.get("tool", "")),
        )
        result.setdefault(category, []).append(preset)

    for entry in sorted(brushes_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() == ".json":
            _load_file(entry, "Basic")
        elif entry.is_dir():
            category = entry.name
            for f in sorted(entry.iterdir()):
                if f.is_file() and f.suffix.lower() == ".json":
                    _load_file(f, category)

    return result
