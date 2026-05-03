"""
pixel_sort.py — Pixel Sort for Layered.

Sorts pixels within rows or columns by a chosen metric — brightness, hue,
saturation, or a single RGB channel — producing the iconic "data-melt" look
made famous by artist Kim Asendorf.

A low/high threshold limits *which* pixels participate, so you can sort only
the bright midtones while leaving shadows and highlights untouched.

Chunk Size breaks each row into fixed-length segments instead of sorting the
entire span at once, giving a "staircase" corruption feel.

Sprite-friendly: fully transparent pixels (alpha == 0) are never moved.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


# ──────────────────────────────────────────────────────────────────────────────
# Sorting key helpers
# ──────────────────────────────────────────────────────────────────────────────

def _luminance(arr: np.ndarray) -> np.ndarray:
    return (
        0.299 * arr[..., 0].astype(np.float32)
        + 0.587 * arr[..., 1].astype(np.float32)
        + 0.114 * arr[..., 2].astype(np.float32)
    )


def _hue(arr: np.ndarray) -> np.ndarray:
    r = arr[..., 0].astype(np.float32) / 255.0
    g = arr[..., 1].astype(np.float32) / 255.0
    b = arr[..., 2].astype(np.float32) / 255.0
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc + 1e-7
    hue = np.zeros_like(r)
    mask_r = (maxc == r) & (delta > 1e-7)
    mask_g = (maxc == g) & (delta > 1e-7)
    mask_b = (maxc == b) & (delta > 1e-7)
    hue[mask_r] = ((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6
    hue[mask_g] = (b[mask_g] - r[mask_g]) / delta[mask_g] + 2
    hue[mask_b] = (r[mask_b] - g[mask_b]) / delta[mask_b] + 4
    return hue * (255.0 / 6.0)


def _saturation(arr: np.ndarray) -> np.ndarray:
    r = arr[..., 0].astype(np.float32)
    g = arr[..., 1].astype(np.float32)
    b = arr[..., 2].astype(np.float32)
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    sat = np.where(maxc > 0, (maxc - minc) / (maxc + 1e-7), 0.0)
    return sat * 255.0


_KEY_FNS = {
    "brightness": _luminance,
    "hue":        _hue,
    "saturation": _saturation,
    "red":        lambda a: a[..., 0].astype(np.float32),
    "green":      lambda a: a[..., 1].astype(np.float32),
    "blue":       lambda a: a[..., 2].astype(np.float32),
}


# ──────────────────────────────────────────────────────────────────────────────
# Core sort routine
# ──────────────────────────────────────────────────────────────────────────────

def _sort_spans(
    arr: np.ndarray,
    key: np.ndarray,
    threshold_low: float,
    threshold_high: float,
    chunk_size: int,
    reverse: bool,
) -> np.ndarray:
    """Sort participating pixel spans inside every row of `arr` in-place."""
    h, w = arr.shape[:2]
    alpha = arr[..., 3]

    for y in range(h):
        row_key   = key[y]
        row_alpha = alpha[y]

        # Pixels eligible for sorting: opaque + within threshold band
        participate = (
            (row_alpha > 0) &
            (row_key >= threshold_low) &
            (row_key <= threshold_high)
        )
        indices = np.where(participate)[0]
        if len(indices) < 2:
            continue

        if chunk_size > 0:
            for start in range(0, len(indices), chunk_size):
                seg = indices[start : start + chunk_size]
                if len(seg) < 2:
                    continue
                order = np.argsort(row_key[seg])
                if reverse:
                    order = order[::-1]
                arr[y][seg] = arr[y][seg[order]]
        else:
            order = np.argsort(row_key[indices])
            if reverse:
                order = order[::-1]
            arr[y][indices] = arr[y][indices[order]]

    return arr


# ──────────────────────────────────────────────────────────────────────────────
# Filter entry point
# ──────────────────────────────────────────────────────────────────────────────

def _filter_fn(
    img: Image.Image,
    *,
    direction: str = "horizontal",
    sort_by: str = "brightness",
    threshold_low: int = 30,
    threshold_high: int = 220,
    chunk_size: int = 0,
    reverse: bool = False,
) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    arr = np.array(img, dtype=np.uint8).copy()

    # Vertical sort: just transpose so columns become rows, sort, transpose back
    if direction == "vertical":
        arr = arr.transpose(1, 0, 2).copy()

    key = _KEY_FNS.get(sort_by, _luminance)(arr)
    arr = _sort_spans(arr, key, float(threshold_low), float(threshold_high), chunk_size, reverse)

    if direction == "vertical":
        arr = arr.transpose(1, 0, 2)

    return Image.fromarray(arr, "RGBA")


# ──────────────────────────────────────────────────────────────────────────────
# Plugin registration
# ──────────────────────────────────────────────────────────────────────────────

class PixelSortPlugin(Plugin):
    name    = "Pixel Sort"
    version = "1.0.0"
    author  = ""

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Pixel Sort",
            _filter_fn,
            settings=[
                Setting(
                    name="direction", type="choice", default="horizontal",
                    label="Direction",
                    choices=["horizontal", "vertical"],
                ),
                Setting(
                    name="sort_by", type="choice", default="brightness",
                    label="Sort Key",
                    choices=["brightness", "hue", "saturation", "red", "green", "blue"],
                ),
                Setting(
                    name="threshold_low", type="int", default=30,
                    label="Threshold Low  (0–255)",
                    min=0, max=255, step=1,
                ),
                Setting(
                    name="threshold_high", type="int", default=220,
                    label="Threshold High (0–255)",
                    min=0, max=255, step=1,
                ),
                Setting(
                    name="chunk_size", type="int", default=0,
                    label="Chunk Size  (0 = full span)",
                    min=0, max=1000, step=1,
                ),
                Setting(
                    name="reverse", type="bool", default=False,
                    label="Reverse Sort Direction",
                ),
            ],
            category="Stylize",
        )
        ctx.logger.info("Pixel Sort registered.")