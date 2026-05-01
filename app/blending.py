"""Blend mode math.

All ops take two RGBA float arrays in [0, 1] and return RGBA float in [0, 1].
Alpha compositing follows the standard Porter-Duff "over" using each blend's
color result.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

BlendFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _split(img: np.ndarray):
    return img[..., :3], img[..., 3:4]


def _combine(rgb: np.ndarray, a: np.ndarray) -> np.ndarray:
    return np.concatenate([np.clip(rgb, 0.0, 1.0), np.clip(a, 0.0, 1.0)], axis=-1)


def normal(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    return top


def multiply(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(br * tr, ta)


def screen(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(1.0 - (1.0 - br) * (1.0 - tr), ta)


def overlay(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    low = 2.0 * br * tr
    high = 1.0 - 2.0 * (1.0 - br) * (1.0 - tr)
    out = np.where(br < 0.5, low, high)
    return _combine(out, ta)


def darken(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(np.minimum(br, tr), ta)


def lighten(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(np.maximum(br, tr), ta)


def add(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(br + tr, ta)


def subtract(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(br - tr, ta)


def difference(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(np.abs(br - tr), ta)


BLEND_MODES: dict[str, BlendFn] = {
    "Normal": normal,
    "Multiply": multiply,
    "Screen": screen,
    "Overlay": overlay,
    "Darken": darken,
    "Lighten": lighten,
    "Add": add,
    "Subtract": subtract,
    "Difference": difference,
}


def composite(base: np.ndarray, top: np.ndarray, mode: str, opacity: float) -> np.ndarray:
    """Composite `top` onto `base` using `mode` then alpha-over with `opacity`.

    Both arrays are HxWx4 float32 in [0, 1].
    """
    fn = BLEND_MODES.get(mode, normal)
    blended = fn(base, top)

    _, ba = _split(base)
    blended_rgb, ta = _split(blended)
    src_a = ta * float(opacity)

    out_a = src_a + ba * (1.0 - src_a)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    base_rgb, _ = _split(base)
    out_rgb = (blended_rgb * src_a + base_rgb * ba * (1.0 - src_a)) / safe
    return _combine(out_rgb, out_a)
