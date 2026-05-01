"""Layer + LayerStack model.

Each layer holds a Pillow RGBA image and metadata. LayerStack composites
bottom-to-top with a "below the active layer" PIL cache so drawing strokes
only have to re-blend the active layer and anything above it.

For Normal blend with full opacity, we use Pillow's `Image.alpha_composite`
(C-implemented, fast). For other blend modes / partial opacity we fall back
to NumPy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np
from PIL import Image

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

    def to_array(self) -> np.ndarray:
        if self.image.mode != "RGBA":
            self.image = self.image.convert("RGBA")
        return np.asarray(self.image, dtype=np.float32) / 255.0

    def replace_image(self, new_image: Image.Image) -> None:
        self.image = new_image.convert("RGBA")


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
        """Return a canvas-sized RGBA image with the layer pasted at its offset."""
        if layer.offset == (0, 0) and layer.image.size == (self.width, self.height):
            if layer.image.mode != "RGBA":
                return layer.image.convert("RGBA")
            return layer.image
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        canvas.paste(src, layer.offset, src)
        return canvas

    def _blend_onto(self, base: Image.Image, layer: Layer) -> Image.Image:
        if not layer.visible or layer.opacity <= 0.0:
            return base
        top = self._positioned(layer)

        if layer.blend_mode == "Normal":
            scaled = _scale_alpha(top, layer.opacity)
            return Image.alpha_composite(base, scaled)

        base_arr = np.asarray(base, dtype=np.float32) / 255.0
        top_arr = np.asarray(top, dtype=np.float32) / 255.0
        out = np_composite(base_arr, top_arr, layer.blend_mode, layer.opacity)
        return Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGBA")

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

    def resize_canvas(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        for layer in self.layers:
            new_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            new_img.paste(layer.image, (0, 0))
            layer.image = new_img
        self.invalidate_cache()
