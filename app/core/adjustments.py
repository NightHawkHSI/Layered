"""Adjustment filters for adjustment layers.

Each filter takes an RGBA uint8 PIL Image and a params dict, returns a
new RGBA PIL Image of the same size. Filters are pure functions — no
state, no side effects.

Adjustment layers reference a filter by name (`Layer.adjustment`) and
store slider values in `Layer.adjustment_params`. The compositor applies
the filter to the running composite below the adjustment layer at blend
time, optionally constrained by the layer mask.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
from PIL import Image, ImageOps


FilterFn = Callable[[Image.Image, dict[str, Any]], Image.Image]


def _to_arr(img: Image.Image) -> np.ndarray:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return np.asarray(img, dtype=np.float32) / 255.0


def _from_arr(arr: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGBA")


def _brightness(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    amount = float(params.get("amount", 0.0))   # -1.0 .. 1.0
    arr = _to_arr(img)
    arr[..., :3] = np.clip(arr[..., :3] + amount, 0.0, 1.0)
    return _from_arr(arr)


def _contrast(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    amount = float(params.get("amount", 0.0))   # -1.0 .. 1.0
    arr = _to_arr(img)
    factor = 1.0 + amount
    arr[..., :3] = np.clip((arr[..., :3] - 0.5) * factor + 0.5, 0.0, 1.0)
    return _from_arr(arr)


def _invert(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    arr = _to_arr(img)
    arr[..., :3] = 1.0 - arr[..., :3]
    return _from_arr(arr)


def _grayscale(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    amount = float(params.get("amount", 1.0))   # 0..1 blend back to color
    arr = _to_arr(img)
    luma = (arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722)
    gray = np.stack([luma, luma, luma], axis=-1)
    arr[..., :3] = arr[..., :3] * (1.0 - amount) + gray * amount
    return _from_arr(arr)


def _levels(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    black = float(params.get("black", 0.0))     # 0..1 input black point
    white = float(params.get("white", 1.0))     # 0..1 input white point
    gamma = max(0.01, float(params.get("gamma", 1.0)))
    arr = _to_arr(img)
    span = max(1e-6, white - black)
    x = np.clip((arr[..., :3] - black) / span, 0.0, 1.0)
    arr[..., :3] = np.power(x, 1.0 / gamma)
    return _from_arr(arr)


def _hue_saturation(img: Image.Image, params: dict[str, Any]) -> Image.Image:
    hue_shift = float(params.get("hue", 0.0))        # -0.5 .. 0.5 (turns)
    sat_scale = float(params.get("saturation", 1.0)) # 0 .. 2
    light_add = float(params.get("lightness", 0.0))  # -1 .. 1
    rgba = _to_arr(img)
    rgb = rgba[..., :3]
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    diff = mx - mn
    # Value
    v = mx
    # Saturation
    s = np.where(mx > 0, diff / np.maximum(mx, 1e-9), 0.0)
    # Hue (0..1)
    h = np.zeros_like(mx)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    nz = diff > 1e-9
    rc = np.where(nz, (mx - r) / np.maximum(diff, 1e-9), 0.0)
    gc = np.where(nz, (mx - g) / np.maximum(diff, 1e-9), 0.0)
    bc = np.where(nz, (mx - b) / np.maximum(diff, 1e-9), 0.0)
    h = np.where(r == mx, bc - gc, h)
    h = np.where(g == mx, 2.0 + rc - bc, h)
    h = np.where(b == mx, 4.0 + gc - rc, h)
    h = (h / 6.0) % 1.0
    # Adjust
    h = (h + hue_shift) % 1.0
    s = np.clip(s * sat_scale, 0.0, 1.0)
    v = np.clip(v + light_add, 0.0, 1.0)
    # HSV -> RGB
    i = np.floor(h * 6.0).astype(np.int32)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    out_r = np.choose(i, [v, q, p, p, t, v])
    out_g = np.choose(i, [t, v, v, q, p, p])
    out_b = np.choose(i, [p, p, t, v, v, q])
    rgba[..., 0] = out_r
    rgba[..., 1] = out_g
    rgba[..., 2] = out_b
    return _from_arr(rgba)


# Filter registry: name -> (callable, default_params_dict)
ADJUSTMENTS: dict[str, tuple[FilterFn, dict[str, Any]]] = {
    "Brightness":     (_brightness,     {"amount": 0.0}),
    "Contrast":       (_contrast,       {"amount": 0.0}),
    "Invert":         (_invert,         {}),
    "Grayscale":      (_grayscale,      {"amount": 1.0}),
    "Levels":         (_levels,         {"black": 0.0, "white": 1.0, "gamma": 1.0}),
    "Hue/Saturation": (_hue_saturation, {"hue": 0.0, "saturation": 1.0, "lightness": 0.0}),
}


def apply_adjustment(img: Image.Image, name: str, params: dict[str, Any] | None = None) -> Image.Image:
    """Apply named adjustment to `img`. Unknown name returns image unchanged."""
    entry = ADJUSTMENTS.get(name)
    if entry is None:
        return img
    fn, defaults = entry
    merged = dict(defaults)
    if params:
        merged.update(params)
    return fn(img, merged)


def default_params(name: str) -> dict[str, Any]:
    entry = ADJUSTMENTS.get(name)
    return dict(entry[1]) if entry else {}
