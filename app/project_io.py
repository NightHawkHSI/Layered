"""Project file I/O — save/load a Project as a single portable archive.

Format: ZIP container with extension `.layered`:
  manifest.json    # project name + description + canvas + layer metadata
  layer_NNN.png    # one PNG per layer in stack order

Layers, blend modes, opacity, visibility, offsets, locks, and groups
round-trip. History and clipboard are treated as ephemeral. Selection
is saved (canvas-sized L mask PNG) so the marching ants survive a
save/load cycle.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Optional

from PIL import Image

from .layer import Layer, LayerStack
from .project import Project, Selection


PROJECT_EXT = ".layered"
PROJECT_FILTER = "Layered project (*.layered)"
MANIFEST_VERSION = 1


def save_project(proj: Project, path: Path, *, description: str = "") -> None:
    path = Path(path)
    layers_meta = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for j, layer in enumerate(proj.stack.layers):
            img_name = f"layer_{j:03d}.png"
            img = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, "PNG")
            zf.writestr(img_name, buf.getvalue())
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
        sel_file: Optional[str] = None
        if proj.selection is not None and getattr(proj.selection, "mask", None) is not None:
            mask = proj.selection.mask if proj.selection.mask.mode == "L" else proj.selection.mask.convert("L")
            buf = io.BytesIO()
            mask.save(buf, "PNG")
            sel_file = "selection.png"
            zf.writestr(sel_file, buf.getvalue())

        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "name": proj.name,
            "description": description,
            "width": int(proj.stack.width),
            "height": int(proj.stack.height),
            "active_index": int(proj.stack.active_index),
            "layers": layers_meta,
            "selection_file": sel_file,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))


def load_project(path: Path) -> Project:
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        stack = LayerStack(int(manifest["width"]), int(manifest["height"]))
        for ldata in manifest.get("layers", []):
            img_name = ldata["image_file"]
            img = Image.open(io.BytesIO(zf.read(img_name))).convert("RGBA")
            img.load()
            offset = ldata.get("offset") or [0, 0]
            stack.layers.append(Layer(
                name=str(ldata.get("name", "Layer")),
                image=img,
                visible=bool(ldata.get("visible", True)),
                opacity=float(ldata.get("opacity", 1.0)),
                blend_mode=str(ldata.get("blend_mode", "Normal")),
                offset=(int(offset[0]), int(offset[1])),
                locked=bool(ldata.get("locked", False)),
                group=ldata.get("group"),
            ))
        ai = int(manifest.get("active_index", len(stack.layers) - 1))
        stack.active_index = ai if 0 <= ai < len(stack.layers) else len(stack.layers) - 1
        stack.invalidate_cache()

        sel = None
        sel_file = manifest.get("selection_file")
        if sel_file:
            try:
                mask = Image.open(io.BytesIO(zf.read(sel_file))).convert("L")
                mask.load()
                bb = mask.getbbox()
                if bb is not None:
                    sel = Selection(bbox=bb, mask=mask)
            except KeyError:
                sel = None

    proj = Project(
        name=str(manifest.get("name", path.stem)),
        stack=stack,
        path=path,
        dirty=False,
    )
    proj.selection = sel
    proj.history.commit(f"Open {path.name}", stack)
    return proj
