"""Export composite + per-layer images.

Supports several formats and an alpha policy for formats that can't carry
transparency. Layers are exported at canvas size with offsets applied so the
output drops into game pipelines without alignment work. A `manifest.json`
records every layer's offset, opacity, blend mode, and visibility.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PIL import Image

from .layer import LayerStack
from .logger import get_logger

log = get_logger("export")


# Format -> (Pillow save format, supports alpha)
FORMATS: dict[str, tuple[str, bool]] = {
    "PNG":  ("PNG",  True),
    "WEBP": ("WEBP", True),
    "TIFF": ("TIFF", True),
    "DDS":  ("DDS",  True),
    "BMP":  ("BMP",  False),
    "JPG":  ("JPEG", False),
}


def _safe_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return cleaned or "layer"


def _unique_name(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    n = 2
    while f"{base} ({n})" in used:
        n += 1
    final = f"{base} ({n})"
    used.add(final)
    return final


def flatten_alpha(image: Image.Image, bg: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Composite an RGBA image over a solid background, returning RGB."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    base = Image.new("RGB", image.size, bg)
    base.paste(image, mask=image.split()[3])
    return base


def _save(image: Image.Image, path: Path, fmt: str, *, keep_alpha: bool, flatten_bg) -> None:
    pil_fmt, supports_alpha = FORMATS[fmt]
    out = image.convert("RGBA")
    if not supports_alpha or not keep_alpha:
        out = flatten_alpha(out, flatten_bg)
    save_kwargs: dict = {}
    if pil_fmt == "JPEG":
        save_kwargs["quality"] = 95
    out.save(path, format=pil_fmt, **save_kwargs)


def export_composite(
    stack: LayerStack,
    path: str | Path,
    *,
    fmt: str = "PNG",
    keep_alpha: bool = True,
    flatten_bg: tuple[int, int, int] = (255, 255, 255),
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = stack.composite()
    _save(image, path, fmt, keep_alpha=keep_alpha, flatten_bg=flatten_bg)
    log.info("Exported composite %s as %s", path, fmt)
    return path


def export_layers(
    stack: LayerStack,
    out_dir: str | Path,
    *,
    fmt: str = "PNG",
    keep_alpha: bool = True,
    flatten_bg: tuple[int, int, int] = (255, 255, 255),
    include_composite: bool = True,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pil_fmt, _ = FORMATS[fmt]
    ext = fmt.lower()

    manifest: dict = {
        "canvas": {"width": stack.width, "height": stack.height},
        "format": fmt,
        "keep_alpha": keep_alpha and FORMATS[fmt][1],
        "layers": [],
    }

    used: set[str] = set()
    for idx, layer in enumerate(stack.layers):
        base = _unique_name(_safe_name(layer.name), used)
        fname = base + f".{ext}"
        fpath = out / fname

        canvas = Image.new("RGBA", (stack.width, stack.height), (0, 0, 0, 0))
        ox, oy = layer.offset
        canvas.paste(layer.image, (ox, oy), layer.image)
        _save(canvas, fpath, fmt, keep_alpha=keep_alpha, flatten_bg=flatten_bg)

        manifest["layers"].append({
            "index": idx,
            "name": layer.name,
            "file": fname,
            "visible": layer.visible,
            "opacity": layer.opacity,
            "blend_mode": layer.blend_mode,
            "offset": list(layer.offset),
            "locked": layer.locked,
            "group": layer.group,
        })
        log.info("Exported layer %s -> %s", layer.name, fpath)

    if include_composite:
        composite_name = f"composite.{ext}"
        export_composite(stack, out / composite_name, fmt=fmt, keep_alpha=keep_alpha, flatten_bg=flatten_bg)
        manifest["composite"] = composite_name

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote manifest %s", manifest_path)
    return manifest
