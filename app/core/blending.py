"""Blend mode math.

All ops take two RGBA float arrays in [0, 1] and return RGBA float in [0, 1].
Alpha compositing follows the standard Porter-Duff "over" using each blend's
color result.

If `numba` is installed, the fused `composite()` path runs a parallel JIT
kernel (10x-50x speedup on big arrays). Otherwise the numpy path runs.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

try:
    from numba import njit, prange  # type: ignore
    _HAS_NUMBA = True
except Exception:
    _HAS_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore[no-redef]
        def deco(fn):
            return fn
        return deco if not args else (deco(args[0]) if callable(args[0]) else deco)

    prange = range  # type: ignore[assignment]

BlendFn = Callable[[np.ndarray, np.ndarray], np.ndarray]

# Mode ids for the JIT path (kept in sync with BLEND_MODES below).
_MODE_NORMAL     = 0
_MODE_MULTIPLY   = 1
_MODE_SCREEN     = 2
_MODE_OVERLAY    = 3
_MODE_DARKEN     = 4
_MODE_LIGHTEN    = 5
_MODE_ADD        = 6
_MODE_SUBTRACT   = 7
_MODE_DIFFERENCE = 8
_MODE_SOFT_LIGHT = 9

# Modes listed here run on the JIT path. Non-separable HSL modes (Color,
# Saturation) are numpy-only — composite() routes them past the kernel.
_MODE_IDS: dict[str, int] = {
    "Normal":     _MODE_NORMAL,
    "Multiply":   _MODE_MULTIPLY,
    "Screen":     _MODE_SCREEN,
    "Overlay":    _MODE_OVERLAY,
    "Darken":     _MODE_DARKEN,
    "Lighten":    _MODE_LIGHTEN,
    "Add":        _MODE_ADD,
    "Subtract":   _MODE_SUBTRACT,
    "Difference": _MODE_DIFFERENCE,
    "Soft Light": _MODE_SOFT_LIGHT,
}


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


def soft_light(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    """W3C soft-light: a gentle dodge/burn driven by the top layer."""
    br, _ = _split(base)
    tr, ta = _split(top)
    d = np.where(br <= 0.25, ((16.0 * br - 12.0) * br + 4.0) * br, np.sqrt(br))
    out = np.where(
        tr <= 0.5,
        br - (1.0 - 2.0 * tr) * br * (1.0 - br),
        br + (2.0 * tr - 1.0) * (d - br),
    )
    return _combine(out, ta)


# --- non-separable (HSL) blend helpers, per the W3C compositing spec ---

def _luma(rgb: np.ndarray) -> np.ndarray:
    return 0.3 * rgb[..., 0:1] + 0.59 * rgb[..., 1:2] + 0.11 * rgb[..., 2:3]


def _sat(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=-1, keepdims=True) - rgb.min(axis=-1, keepdims=True)


def _clip_color(rgb: np.ndarray) -> np.ndarray:
    """Pull any out-of-gamut channel back toward the pixel's luma."""
    l = _luma(rgb)
    n = rgb.min(axis=-1, keepdims=True)
    x = rgb.max(axis=-1, keepdims=True)
    out = rgb
    lo = l + (rgb - l) * l / np.where((l - n) != 0.0, l - n, 1.0)
    out = np.where(n < 0.0, lo, out)
    hi = l + (rgb - l) * (1.0 - l) / np.where((x - l) != 0.0, x - l, 1.0)
    out = np.where(x > 1.0, hi, out)
    return out


def _set_luma(rgb: np.ndarray, target_l: np.ndarray) -> np.ndarray:
    return _clip_color(rgb + (target_l - _luma(rgb)))


def _set_sat(rgb: np.ndarray, target_s: np.ndarray) -> np.ndarray:
    """Rescale a pixel's channels to the given saturation, keeping order."""
    order = np.argsort(rgb, axis=-1)
    srt = np.take_along_axis(rgb, order, axis=-1)
    cmin = srt[..., 0:1]
    cmid = srt[..., 1:2]
    cmax = srt[..., 2:3]
    span = cmax - cmin
    has = span > 1e-6
    new = np.zeros_like(srt)
    new[..., 1:2] = np.where(has, (cmid - cmin) * target_s / np.where(has, span, 1.0), 0.0)
    new[..., 2:3] = np.where(has, target_s, 0.0)
    out = np.empty_like(rgb)
    np.put_along_axis(out, order, new, axis=-1)
    return out


def color(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Hue + saturation of the top layer, luma of the base."""
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(_set_luma(tr, _luma(br)), ta)


def saturation(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Saturation of the top layer, hue + luma of the base."""
    br, _ = _split(base)
    tr, ta = _split(top)
    return _combine(_set_luma(_set_sat(br, _sat(tr)), _luma(br)), ta)


BLEND_MODES: dict[str, BlendFn] = {
    "Normal": normal,
    "Multiply": multiply,
    "Screen": screen,
    "Overlay": overlay,
    "Soft Light": soft_light,
    "Darken": darken,
    "Lighten": lighten,
    "Add": add,
    "Subtract": subtract,
    "Difference": difference,
    "Color": color,
    "Saturation": saturation,
}


@njit(cache=True, parallel=True, fastmath=True)
def _composite_kernel(base: np.ndarray, top: np.ndarray,
                      mode_id: int, opacity: float) -> np.ndarray:
    """Fused per-pixel composite for the numba JIT path.

    Performs blend + Porter-Duff "over" alpha compositing in one pass with
    no intermediate HxWx4 allocations.
    """
    h, w, _ = base.shape
    out = np.empty_like(base)
    for y in prange(h):
        for x in range(w):
            br = base[y, x, 0]; bg = base[y, x, 1]; bb = base[y, x, 2]; ba = base[y, x, 3]
            tr = top[y, x, 0];  tg = top[y, x, 1];  tb = top[y, x, 2];  ta = top[y, x, 3]

            if mode_id == 0:        # Normal
                cr, cg, cb = tr, tg, tb
            elif mode_id == 1:      # Multiply
                cr, cg, cb = br * tr, bg * tg, bb * tb
            elif mode_id == 2:      # Screen
                cr = 1.0 - (1.0 - br) * (1.0 - tr)
                cg = 1.0 - (1.0 - bg) * (1.0 - tg)
                cb = 1.0 - (1.0 - bb) * (1.0 - tb)
            elif mode_id == 3:      # Overlay
                cr = 2.0 * br * tr if br < 0.5 else 1.0 - 2.0 * (1.0 - br) * (1.0 - tr)
                cg = 2.0 * bg * tg if bg < 0.5 else 1.0 - 2.0 * (1.0 - bg) * (1.0 - tg)
                cb = 2.0 * bb * tb if bb < 0.5 else 1.0 - 2.0 * (1.0 - bb) * (1.0 - tb)
            elif mode_id == 4:      # Darken
                cr = br if br < tr else tr
                cg = bg if bg < tg else tg
                cb = bb if bb < tb else tb
            elif mode_id == 5:      # Lighten
                cr = br if br > tr else tr
                cg = bg if bg > tg else tg
                cb = bb if bb > tb else tb
            elif mode_id == 6:      # Add
                cr, cg, cb = br + tr, bg + tg, bb + tb
            elif mode_id == 7:      # Subtract
                cr, cg, cb = br - tr, bg - tg, bb - tb
            elif mode_id == 8:      # Difference
                cr = abs(br - tr); cg = abs(bg - tg); cb = abs(bb - tb)
            elif mode_id == 9:      # Soft Light
                dr = ((16.0 * br - 12.0) * br + 4.0) * br if br <= 0.25 else math.sqrt(br)
                dg = ((16.0 * bg - 12.0) * bg + 4.0) * bg if bg <= 0.25 else math.sqrt(bg)
                db = ((16.0 * bb - 12.0) * bb + 4.0) * bb if bb <= 0.25 else math.sqrt(bb)
                cr = br - (1.0 - 2.0 * tr) * br * (1.0 - br) if tr <= 0.5 else br + (2.0 * tr - 1.0) * (dr - br)
                cg = bg - (1.0 - 2.0 * tg) * bg * (1.0 - bg) if tg <= 0.5 else bg + (2.0 * tg - 1.0) * (dg - bg)
                cb = bb - (1.0 - 2.0 * tb) * bb * (1.0 - bb) if tb <= 0.5 else bb + (2.0 * tb - 1.0) * (db - bb)
            else:
                cr, cg, cb = tr, tg, tb

            if cr < 0.0: cr = 0.0
            elif cr > 1.0: cr = 1.0
            if cg < 0.0: cg = 0.0
            elif cg > 1.0: cg = 1.0
            if cb < 0.0: cb = 0.0
            elif cb > 1.0: cb = 1.0

            src_a = ta * opacity
            out_a = src_a + ba * (1.0 - src_a)
            safe = out_a if out_a > 1e-6 else 1.0
            inv = 1.0 - src_a
            out[y, x, 0] = (cr * src_a + br * ba * inv) / safe
            out[y, x, 1] = (cg * src_a + bg * ba * inv) / safe
            out[y, x, 2] = (cb * src_a + bb * ba * inv) / safe
            out[y, x, 3] = out_a
    return out


def _composite_numpy(base: np.ndarray, top: np.ndarray,
                     mode: str, opacity: float) -> np.ndarray:
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


def composite(base: np.ndarray, top: np.ndarray, mode: str, opacity: float) -> np.ndarray:
    """Composite `top` onto `base` using `mode` then alpha-over with `opacity`.

    Both arrays are HxWx4 float32 in [0, 1]. JIT path used when numba is
    available, else numpy path.
    """
    if _HAS_NUMBA and mode in _MODE_IDS:
        b = np.ascontiguousarray(base, dtype=np.float32)
        t = np.ascontiguousarray(top,  dtype=np.float32)
        if b.shape == t.shape and b.ndim == 3 and b.shape[2] == 4:
            return _composite_kernel(b, t, _MODE_IDS[mode], float(opacity))
    return _composite_numpy(base, top, mode, float(opacity))
