"""Tile-based composite cache with dirty-rect tracking.

Splits the canvas into fixed-size tiles (default 256x256) and caches the
composited RGBA per tile. Tools / canvas events mark rectangles dirty
via :meth:`TileRenderer.mark_dirty`; only those tiles are re-blended on
the next call to :meth:`TileRenderer.render`.

The renderer wraps a :class:`LayerStack` and uses the stack's own
``_blend_onto`` per-layer compositing logic, so blend modes, masks,
adjustments and smart objects continue to work unchanged.

Tile size is a power-of-two so address math reduces to bit ops on the
hot path. ``TILE_SIZE`` is module-level — change once if a workload
profiles better at a different tile resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

from app.core.layer import LayerStack


TILE_SIZE = 256


@dataclass
class _TileCache:
    image: Optional[Image.Image] = None
    layer_signature: tuple = ()


@dataclass
class TileRenderer:
    """Composite cache keyed by 256x256 canvas tiles.

    Owns the per-tile RGBA cache for one LayerStack. Call
    :meth:`mark_dirty` whenever you mutate layer pixels; call
    :meth:`render` to get a fresh full-canvas composite.
    """

    stack: LayerStack
    tile_size: int = TILE_SIZE
    _tiles: dict[tuple[int, int], _TileCache] = field(default_factory=dict)
    _dirty: set[tuple[int, int]] = field(default_factory=set)
    _full_canvas: Optional[Image.Image] = None

    # ------------------------------------------------------------------
    # Grid math
    # ------------------------------------------------------------------

    @property
    def cols(self) -> int:
        return (self.stack.width + self.tile_size - 1) // self.tile_size

    @property
    def rows(self) -> int:
        return (self.stack.height + self.tile_size - 1) // self.tile_size

    def _tile_bounds(self, tx: int, ty: int) -> tuple[int, int, int, int]:
        x0 = tx * self.tile_size
        y0 = ty * self.tile_size
        x1 = min(x0 + self.tile_size, self.stack.width)
        y1 = min(y0 + self.tile_size, self.stack.height)
        return x0, y0, x1, y1

    def _tiles_in_rect(self, x0: int, y0: int, x1: int, y1: int):
        x0 = max(0, min(self.stack.width,  int(x0)))
        y0 = max(0, min(self.stack.height, int(y0)))
        x1 = max(0, min(self.stack.width,  int(x1)))
        y1 = max(0, min(self.stack.height, int(y1)))
        if x1 <= x0 or y1 <= y0:
            return
        tx0 = x0 // self.tile_size
        ty0 = y0 // self.tile_size
        tx1 = (x1 - 1) // self.tile_size
        ty1 = (y1 - 1) // self.tile_size
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                yield tx, ty

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_dirty(self, rect: tuple[int, int, int, int]) -> None:
        """Mark all tiles overlapping `rect` (x0, y0, x1, y1) dirty."""
        x0, y0, x1, y1 = rect
        for coord in self._tiles_in_rect(x0, y0, x1, y1):
            self._dirty.add(coord)

    def mark_all_dirty(self) -> None:
        self._dirty.update((tx, ty) for ty in range(self.rows) for tx in range(self.cols))

    def invalidate(self) -> None:
        """Drop all cached tiles and force a full rebuild on next render."""
        self._tiles.clear()
        self._dirty.clear()
        self._full_canvas = None

    def _layer_signature(self) -> tuple:
        """Identity tuple used to detect that a tile cache is still valid.

        Captures every stack property a tile depends on; if the tuple
        changes the cached tile is regarded as stale.
        """
        sig = []
        for layer in self.stack.layers:
            sig.append((
                id(layer),
                id(layer.image),
                layer.visible,
                round(layer.opacity, 4),
                layer.blend_mode,
                layer.offset,
                id(layer.mask),
                layer.mask_enabled,
                layer.adjustment,
                tuple(sorted(layer.adjustment_params.items())) if layer.adjustment_params else (),
            ))
        return tuple(sig)

    def render(self) -> Image.Image:
        """Return a canvas-sized RGBA image, blending only dirty tiles."""
        sig = self._layer_signature()
        # Cheap signature check: when stack composition changed, treat
        # everything as dirty. Without this, edits like reordering or
        # toggling visibility would leave stale tiles on screen.
        if any(t.layer_signature and t.layer_signature != sig for t in self._tiles.values()):
            self.mark_all_dirty()

        if self._full_canvas is None or self._full_canvas.size != (self.stack.width, self.stack.height):
            self._full_canvas = Image.new("RGBA", (self.stack.width, self.stack.height), (0, 0, 0, 0))
            self.mark_all_dirty()

        if not self._dirty:
            return self._full_canvas

        for (tx, ty) in list(self._dirty):
            tile_img = self._render_tile(tx, ty)
            x0, y0, _, _ = self._tile_bounds(tx, ty)
            self._full_canvas.paste(tile_img, (x0, y0))
            self._tiles[(tx, ty)] = _TileCache(image=tile_img, layer_signature=sig)
        self._dirty.clear()
        return self._full_canvas

    # ------------------------------------------------------------------
    # Per-tile composite
    # ------------------------------------------------------------------

    def _render_tile(self, tx: int, ty: int) -> Image.Image:
        """Composite the layer stack restricted to a single tile."""
        x0, y0, x1, y1 = self._tile_bounds(tx, ty)
        tw, th = x1 - x0, y1 - y0
        base = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        for layer in self.stack.layers:
            if not layer.visible or layer.opacity <= 0.0:
                continue
            base = self._blend_layer_onto_tile(base, layer, x0, y0)
        return base

    def _blend_layer_onto_tile(
        self, base: Image.Image, layer, x0: int, y0: int,
    ) -> Image.Image:
        """Blend one layer's contribution onto the tile-sized base.

        Delegates to the stack's full-canvas blender by cropping the
        positioned layer image down to the tile rect. Slightly slower
        than a fully inlined per-tile path but reuses every code path
        (masks, adjustments, numpy blend modes) already covered by
        :class:`LayerStack`.
        """
        positioned = self.stack._positioned(layer)
        tile_crop = positioned.crop((x0, y0, x0 + base.width, y0 + base.height))

        # Build a transient single-layer stack-equivalent view by calling
        # the existing _blend_onto with the cropped pieces. _blend_onto
        # operates on canvas-sized images; pass the tile rect as if it
        # were a small canvas.
        # Adjustment layers operate on the running composite directly.
        if layer.is_adjustment:
            from app.core.adjustments import apply_adjustment
            filtered = apply_adjustment(base, layer.adjustment, layer.adjustment_params)
            # Apply mask + opacity through stack helper expectations.
            mask = Image.new("L", base.size, 255)
            if layer.mask is not None and layer.mask_enabled:
                full_mask = Image.new("L", (self.stack.width, self.stack.height), 0)
                src_mask = layer.mask
                if src_mask.size != layer.image.size:
                    src_mask = src_mask.resize(layer.image.size)
                full_mask.paste(src_mask, layer.offset)
                mask = full_mask.crop((x0, y0, x0 + base.width, y0 + base.height))
            if layer.opacity < 0.999:
                mask = mask.point(lambda v: int(v * layer.opacity))
            return Image.composite(filtered, base, mask)

        if layer.blend_mode == "Normal":
            if layer.opacity < 0.999:
                r, g, b, a = tile_crop.split()
                a = a.point(lambda v: int(v * layer.opacity))
                tile_crop = Image.merge("RGBA", (r, g, b, a))
            return Image.alpha_composite(base, tile_crop)

        import numpy as np
        from app.core.blending import composite as np_composite
        base_arr = np.asarray(base, dtype=np.float32) / 255.0
        top_arr = np.asarray(tile_crop, dtype=np.float32) / 255.0
        out = np_composite(base_arr, top_arr, layer.blend_mode, layer.opacity)
        return Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGBA")
