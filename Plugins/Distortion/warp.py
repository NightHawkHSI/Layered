"""
warp.py — Distortion & Warp for Layered.

Displaces pixels using a mathematical warp field. No other mainstream paint
app ships these as a live-preview filter.

Modes
─────
  wave      Sinusoidal ripple along X, Y, or both axes. Classic liquid effect.
  twirl     Rotates pixels around the centre — more at the middle, less at
            the edge. Strength = max rotation angle in degrees.
  bulge     Pushes pixels outward (bulge > 0) or inward / pinch (bulge < 0)
            from the centre.
  displace  Radial noise displacement — uses a simple procedural hash so each
            pixel gets a unique random-ish offset. Seed controls the pattern.
"""
from __future__ import annotations

import math
import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


def _map_coords(src: np.ndarray, map_x: np.ndarray, map_y: np.ndarray) -> np.ndarray:
    """Bilinear sample src at float coords map_x, map_y (both H×W)."""
    h, w = src.shape[:2]
    x0 = np.floor(map_x).astype(np.int32).clip(0, w - 1)
    y0 = np.floor(map_y).astype(np.int32).clip(0, h - 1)
    x1 = (x0 + 1).clip(0, w - 1)
    y1 = (y0 + 1).clip(0, h - 1)
    fx = (map_x - np.floor(map_x))[..., np.newaxis]
    fy = (map_y - np.floor(map_y))[..., np.newaxis]

    tl = src[y0, x0].astype(np.float32)
    tr = src[y0, x1].astype(np.float32)
    bl = src[y1, x0].astype(np.float32)
    br = src[y1, x1].astype(np.float32)

    return (tl * (1 - fx) * (1 - fy) +
            tr * fx * (1 - fy) +
            bl * (1 - fx) * fy +
            br * fx * fy).clip(0, 255).astype(np.uint8)


def _hash2(ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
    """Cheap deterministic hash → float 0..1, shape of ix."""
    n = ix * 1619 + iy * 31337
    n = (n ^ (n >> 8)) * 0x27d4eb2d
    return ((n ^ (n >> 15)) & 0xFFFFFFFF).astype(np.float32) / 0xFFFFFFFF


def _filter_fn(
    img: Image.Image,
    *,
    mode: str = "wave",
    strength: float = 20.0,
    frequency: float = 0.05,
    twirl_radius: float = 0.5,
    axis: str = "both",
    seed: int = 0,
) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]

    # Base coordinate grids
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    cx, cy = w / 2.0, h / 2.0

    map_x = xg.copy()
    map_y = yg.copy()

    if mode == "wave":
        if axis in ("x", "both"):
            map_x += np.sin(yg * frequency * 2 * math.pi) * strength
        if axis in ("y", "both"):
            map_y += np.sin(xg * frequency * 2 * math.pi) * strength

    elif mode == "twirl":
        dx = xg - cx
        dy = yg - cy
        dist = np.sqrt(dx ** 2 + dy ** 2) + 1e-7
        radius_px = min(w, h) * twirl_radius
        angle = np.where(
            dist < radius_px,
            (1.0 - dist / radius_px) ** 2 * math.radians(strength),
            0.0,
        )
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        map_x = cx + dx * cos_a - dy * sin_a
        map_y = cy + dx * sin_a + dy * cos_a

    elif mode == "bulge":
        dx = xg - cx
        dy = yg - cy
        dist = np.sqrt(dx ** 2 + dy ** 2) + 1e-7
        max_dist = math.sqrt(cx ** 2 + cy ** 2)
        t = (dist / max_dist).clip(0, 1)
        factor = 1.0 + (strength / 100.0) * (1.0 - t)
        map_x = cx + dx / factor
        map_y = cy + dy / factor

    elif mode == "displace":
        scale = int(max(4, min(w, h) // 8))
        ix = (xg / scale).astype(np.int32)
        iy = (yg / scale).astype(np.int32)
        hx = _hash2(ix + seed * 7, iy) * 2.0 - 1.0
        hy = _hash2(ix, iy + seed * 13) * 2.0 - 1.0
        map_x = xg + hx * strength
        map_y = yg + hy * strength

    map_x = map_x.clip(0, w - 1)
    map_y = map_y.clip(0, h - 1)
    result = _map_coords(arr, map_x, map_y)
    return Image.fromarray(result, "RGBA")


class WarpPlugin(Plugin):
    name = "Warp & Distort"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Warp & Distort",
            _filter_fn,
            settings=[
                Setting(name="mode", type="choice", default="wave",
                        label="Mode", choices=["wave", "twirl", "bulge", "displace"]),
                Setting(name="strength", type="float", default=20.0,
                        label="Strength", min=-200.0, max=200.0, step=0.5),
                Setting(name="frequency", type="float", default=0.05,
                        label="Frequency  (wave)", min=0.001, max=0.5, step=0.001),
                Setting(name="axis", type="choice", default="both",
                        label="Axis  (wave)", choices=["x", "y", "both"]),
                Setting(name="twirl_radius", type="float", default=0.5,
                        label="Twirl Radius  (0–1)", min=0.05, max=1.5, step=0.01),
                Setting(name="seed", type="int", default=0,
                        label="Seed  (displace)", min=0, max=9999, step=1),
            ],
            category="Distort",
        )