"""Session persistence: save/restore open projects across runs.

Each open project becomes a directory under `session/`:
  proj_NNN/
    meta.json     # name, path, dimensions, active layer index, dirty flag
    layer_NNN.png # one PNG per layer (RGBA)

Layers, blend modes, opacity, visibility, and offsets round-trip. History,
selections, and clipboard do not — they're treated as ephemeral.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

from .layer import Layer, LayerStack
from .project import Project


def _wipe(session_dir: Path) -> None:
    if not session_dir.exists():
        return
    for child in session_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def save_session(projects: list[Project], session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    _wipe(session_dir)
    for i, proj in enumerate(projects):
        d = session_dir / f"proj_{i:03d}"
        d.mkdir(exist_ok=True)
        layers_meta = []
        for j, layer in enumerate(proj.stack.layers):
            img_name = f"layer_{j:03d}.png"
            img = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
            img.save(d / img_name, "PNG")
            layers_meta.append({
                "name": layer.name,
                "visible": bool(layer.visible),
                "opacity": float(layer.opacity),
                "blend_mode": layer.blend_mode,
                "offset": [int(layer.offset[0]), int(layer.offset[1])],
                "locked": bool(layer.locked),
                "group": layer.group,
                "image_file": img_name,
            })
        meta = {
            "name": proj.name,
            "path": str(proj.path) if proj.path else None,
            "width": int(proj.stack.width),
            "height": int(proj.stack.height),
            "active_index": int(proj.stack.active_index),
            "dirty": bool(proj.dirty),
            "layers": layers_meta,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_session(session_dir: Path) -> list[Project]:
    if not session_dir.exists():
        return []
    out: list[Project] = []
    for d in sorted(session_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stack = LayerStack(int(meta["width"]), int(meta["height"]))
            for ldata in meta.get("layers", []):
                img_path = d / ldata["image_file"]
                if not img_path.exists():
                    continue
                img = Image.open(img_path).convert("RGBA")
                img.load()  # detach from file
                offset = ldata.get("offset") or [0, 0]
                layer = Layer(
                    name=str(ldata.get("name", "Layer")),
                    image=img,
                    visible=bool(ldata.get("visible", True)),
                    opacity=float(ldata.get("opacity", 1.0)),
                    blend_mode=str(ldata.get("blend_mode", "Normal")),
                    offset=(int(offset[0]), int(offset[1])),
                    locked=bool(ldata.get("locked", False)),
                    group=ldata.get("group"),
                )
                stack.layers.append(layer)
            stack.invalidate_cache()
            ai = int(meta.get("active_index", len(stack.layers) - 1))
            stack.active_index = ai if 0 <= ai < len(stack.layers) else len(stack.layers) - 1
            path_str = meta.get("path")
            proj = Project(
                name=str(meta.get("name", "Untitled")),
                stack=stack,
                path=Path(path_str) if path_str else None,
                dirty=bool(meta.get("dirty", False)),
            )
            proj.history.commit("Restore session", stack)
            out.append(proj)
        except Exception:
            continue
    return out


def clear_session(session_dir: Path) -> None:
    _wipe(session_dir)
