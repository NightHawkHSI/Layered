"""Layer + LayerStack model.

Each layer holds a Pillow RGBA image and metadata. LayerStack composites
bottom-to-top with a "below the active layer" PIL cache so drawing strokes
only have to re-blend the active layer and anything above it.

For Normal blend with full opacity, we use Pillow's `Image.alpha_composite`
(C-implemented, fast). For other blend modes / partial opacity we fall back
to NumPy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional

import numpy as np
from PIL import Image, ImageChops

from .adjustments import apply_adjustment, default_params
from .blending import composite as np_composite


@dataclass
class Layer:
    name: str
    image: Image.Image  # RGBA, full canvas size
    visible: bool = True
    opacity: float = 1.0
    blend_mode: str = "Normal"
    offset: tuple[int, int] = (0, 0)
    locked: bool = False
    group: Optional[str] = None
    # Grayscale ("L" mode) mask, same size as `image`. White = fully
    # visible, black = fully hidden, intermediate = partial. None = no
    # mask (layer renders as before). Foundation for adjustment layers.
    mask: Optional[Image.Image] = None
    mask_enabled: bool = True
    # Adjustment layers — when `adjustment` is non-empty the layer has
    # no pixels of its own; instead the named filter from `adjustments`
    # is applied to the running composite below it. `image` is kept as
    # a transparent placeholder so existing code that touches it (size,
    # offset, etc.) keeps working.
    adjustment: Optional[str] = None
    adjustment_params: dict = field(default_factory=dict)

    # Smart Object — when `source_path` is set the layer's pixels are
    # rasterized from an external file (image or .layered project) and
    # refreshed when the source's mtime changes. The image attribute
    # holds the most recent raster.
    source_path: Optional[str] = None
    source_mtime: Optional[float] = None

    @property
    def is_adjustment(self) -> bool:
        return bool(self.adjustment)

    @property
    def is_smart_object(self) -> bool:
        return bool(self.source_path)

    def to_array(self) -> np.ndarray:
        if self.image.mode != "RGBA":
            self.image = self.image.convert("RGBA")
        return np.asarray(self.image, dtype=np.float32) / 255.0

    def replace_image(self, new_image: Image.Image) -> None:
        self.image = new_image.convert("RGBA")

    # ------------------------------------------------------------------
    # Mask operations
    # ------------------------------------------------------------------

    def add_mask(self, *, reveal_all: bool = True) -> Image.Image:
        """Attach a fresh layer mask sized to the layer image.

        reveal_all=True fills the mask white (everything visible).
        reveal_all=False fills black (everything hidden).
        """
        fill = 255 if reveal_all else 0
        self.mask = Image.new("L", self.image.size, fill)
        self.mask_enabled = True
        return self.mask

    def remove_mask(self) -> None:
        self.mask = None

    def apply_mask(self) -> None:
        """Bake the mask permanently into the layer's alpha channel and discard it."""
        if self.mask is None:
            return
        m = self.mask
        if m.size != self.image.size:
            m = m.resize(self.image.size)
        if self.image.mode != "RGBA":
            self.image = self.image.convert("RGBA")
        r, g, b, a = self.image.split()
        a = ImageChops.multiply(a, m)
        self.image = Image.merge("RGBA", (r, g, b, a))
        self.mask = None


def _rasterize_source(path, width: int, height: int) -> Image.Image:
    """Open a smart-object source and return an RGBA canvas-sized image.

    Image files (PNG/JPG/etc): load and paste at (0, 0).
    `.layered` project files: load via project_io and composite the stack.
    Unknown / failed: returns a transparent canvas-sized image.
    """
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    suffix = path.suffix.lower()
    if suffix == ".layered":
        try:
            from .project_io import load_project
            sub = load_project(path)
            comp = sub.stack.composite()
            if comp.size != (width, height):
                # Centre fit the embedded project into our canvas.
                pasted = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                pasted.paste(comp, ((width - comp.width) // 2,
                                    (height - comp.height) // 2), comp)
                return pasted
            return comp
        except Exception:
            return canvas
    try:
        src = Image.open(path).convert("RGBA")
        src.load()
        canvas.paste(src, (0, 0), src)
    except Exception:
        pass
    return canvas


def _scale_alpha(img: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return img
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * opacity))
    return Image.merge("RGBA", (r, g, b, a))


class LayerStack:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.layers: list[Layer] = []
        self.active_index: int = -1
        self._below_cache: Optional[Image.Image] = None
        self._below_cache_for: int = -2

    def __iter__(self) -> Iterator[Layer]:
        return iter(self.layers)

    def __len__(self) -> int:
        return len(self.layers)

    def invalidate_cache(self) -> None:
        self._below_cache = None
        self._below_cache_for = -2

    def add_layer(self, layer: Optional[Layer] = None, name: Optional[str] = None) -> Layer:
        if layer is None:
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            layer = Layer(name=name or f"Layer {len(self.layers) + 1}", image=img)
        self.layers.append(layer)
        self.active_index = len(self.layers) - 1
        self.invalidate_cache()
        return layer

    def add_adjustment(self, name: str, params: Optional[dict] = None,
                       label: Optional[str] = None) -> Layer:
        """Append an adjustment layer that filters the composite below it.

        `name` must match a key in `adjustments.ADJUSTMENTS`. `params`
        overrides default slider values; missing keys fall back to
        defaults at apply time.
        """
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        merged = default_params(name)
        if params:
            merged.update(params)
        layer = Layer(
            name=label or name,
            image=img,
            adjustment=name,
            adjustment_params=merged,
        )
        return self.add_layer(layer)

    def remove_active(self) -> Optional[Layer]:
        if not self.layers or self.active_index < 0:
            return None
        layer = self.layers.pop(self.active_index)
        self.active_index = min(self.active_index, len(self.layers) - 1)
        self.invalidate_cache()
        return layer

    def move(self, src: int, dst: int) -> None:
        if not (0 <= src < len(self.layers)):
            return
        dst = max(0, min(dst, len(self.layers) - 1))
        layer = self.layers.pop(src)
        self.layers.insert(dst, layer)
        self.active_index = dst
        self.invalidate_cache()

    @property
    def active(self) -> Optional[Layer]:
        if 0 <= self.active_index < len(self.layers):
            return self.layers[self.active_index]
        return None

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.layers):
            self.active_index = index
            self.invalidate_cache()

    def _positioned(self, layer: Layer) -> Image.Image:
        """Return a canvas-sized RGBA image with the layer pasted at its offset.

        If the layer has an enabled mask, the mask is multiplied into the
        layer's alpha channel before positioning.
        """
        has_mask = layer.mask is not None and layer.mask_enabled
        if (not has_mask) and layer.offset == (0, 0) and layer.image.size == (self.width, self.height):
            if layer.image.mode != "RGBA":
                return layer.image.convert("RGBA")
            return layer.image

        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        if has_mask:
            m = layer.mask
            if m.size != src.size:
                m = m.resize(src.size)
            r, g, b, a = src.split()
            a = ImageChops.multiply(a, m)
            src = Image.merge("RGBA", (r, g, b, a))

        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        canvas.paste(src, layer.offset, src)
        return canvas

    def _blend_onto(self, base: Image.Image, layer: Layer) -> Image.Image:
        if not layer.visible or layer.opacity <= 0.0:
            return base

        # Adjustment layer: filter the current composite rather than
        # stamping pixels. Mask + opacity gate the effect zone.
        if layer.is_adjustment:
            filtered = apply_adjustment(base, layer.adjustment, layer.adjustment_params)
            return self._blend_adjustment_result(base, filtered, layer)

        top = self._positioned(layer)

        if layer.blend_mode == "Normal":
            scaled = _scale_alpha(top, layer.opacity)
            return Image.alpha_composite(base, scaled)

        base_arr = np.asarray(base, dtype=np.float32) / 255.0
        top_arr = np.asarray(top, dtype=np.float32) / 255.0
        out = np_composite(base_arr, top_arr, layer.blend_mode, layer.opacity)
        return Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGBA")

    def _blend_adjustment_result(
        self, base: Image.Image, filtered: Image.Image, layer: Layer,
    ) -> Image.Image:
        """Composite an adjustment filter result back over the base.

        Respects layer mask (canvas-space) and layer opacity. Where the
        mask is black or opacity is zero, the base shows through unchanged.
        """
        if filtered.size != base.size:
            filtered = filtered.resize(base.size)
        # Build canvas-sized mask: start from layer mask if present, else
        # fully white. Multiply by opacity scalar.
        mask_canvas = Image.new("L", (self.width, self.height), 255)
        if layer.mask is not None and layer.mask_enabled:
            m = layer.mask
            if m.size != layer.image.size:
                m = m.resize(layer.image.size)
            mask_canvas = Image.new("L", (self.width, self.height), 0)
            mask_canvas.paste(m, layer.offset)
        if layer.opacity < 0.999:
            mask_canvas = mask_canvas.point(lambda v: int(v * layer.opacity))
        return Image.composite(filtered, base, mask_canvas)

    def composite(self) -> Image.Image:
        """Composite visible layers, caching everything below the active layer."""
        active_idx = self.active_index if 0 <= self.active_index < len(self.layers) else len(self.layers)

        if self._below_cache is None or self._below_cache_for != active_idx \
                or self._below_cache.size != (self.width, self.height):
            below = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            for layer in self.layers[:active_idx]:
                below = self._blend_onto(below, layer)
            self._below_cache = below
            self._below_cache_for = active_idx

        result = self._below_cache.copy()
        if 0 <= active_idx < len(self.layers):
            result = self._blend_onto(result, self.layers[active_idx])
            for layer in self.layers[active_idx + 1:]:
                result = self._blend_onto(result, layer)
        return result

    def merge_down(self, index: int) -> Optional[int]:
        """Merge layer at `index` onto layer at `index-1`. Returns new active index or None."""
        if not (1 <= index < len(self.layers)):
            return None
        below = self.layers[index - 1]
        top = self.layers[index]
        if below.locked:
            return None
        base = self._positioned(below)
        merged = self._blend_onto(base, top)
        below.image = merged
        below.offset = (0, 0)
        below.blend_mode = "Normal"
        below.opacity = 1.0
        below.visible = True
        below.mask = None
        self.layers.pop(index)
        self.active_index = index - 1
        self.invalidate_cache()
        return self.active_index

    def merge_up(self, index: int) -> Optional[int]:
        """Merge layer at `index` onto layer at `index+1`. Returns new active index or None."""
        if not (0 <= index < len(self.layers) - 1):
            return None
        above = self.layers[index + 1]
        bottom = self.layers[index]
        if above.locked:
            return None
        base = self._positioned(bottom)
        merged = self._blend_onto(base, above)
        above.image = merged
        above.offset = (0, 0)
        above.blend_mode = "Normal"
        above.opacity = 1.0
        above.visible = True
        above.mask = None
        self.layers.pop(index)
        self.active_index = index
        self.invalidate_cache()
        return self.active_index

    # ------------------------------------------------------------------
    # Smart Objects
    # ------------------------------------------------------------------

    def add_smart_object(self, source_path: str, name: Optional[str] = None) -> Layer:
        """Create a smart-object layer linked to `source_path`.

        The source is rasterized immediately; subsequent calls to
        `refresh_smart_objects()` re-rasterize when the file's mtime
        changes.
        """
        from pathlib import Path as _P
        p = _P(source_path)
        img = _rasterize_source(p, self.width, self.height)
        layer = Layer(
            name=name or p.stem,
            image=img,
            source_path=str(p),
            source_mtime=p.stat().st_mtime if p.exists() else None,
        )
        return self.add_layer(layer)

    def refresh_smart_objects(self) -> int:
        """Re-rasterize any smart-object layer whose source mtime changed.

        Returns the number of layers updated.
        """
        from pathlib import Path as _P
        n = 0
        for layer in self.layers:
            if not layer.is_smart_object:
                continue
            p = _P(layer.source_path)
            if not p.exists():
                continue
            mtime = p.stat().st_mtime
            if layer.source_mtime is not None and mtime <= layer.source_mtime:
                continue
            try:
                layer.image = _rasterize_source(p, self.width, self.height)
                layer.source_mtime = mtime
                n += 1
            except Exception:
                continue
        if n:
            self.invalidate_cache()
        return n

    def resize_canvas(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        for layer in self.layers:
            new_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            new_img.paste(layer.image, (0, 0))
            layer.image = new_img
            if layer.mask is not None:
                # Pad mask with black (hidden) outside the original area.
                new_mask = Image.new("L", (width, height), 0)
                new_mask.paste(layer.mask, (0, 0))
                layer.mask = new_mask
        self.invalidate_cache()
