"""Unit tests for app.blending pure-function blend math."""
from __future__ import annotations

import numpy as np
import pytest

from app import blending
from app.blending import (
    BLEND_MODES,
    add,
    composite,
    darken,
    difference,
    lighten,
    multiply,
    normal,
    overlay,
    screen,
    subtract,
)


def _rgba(r, g, b, a, size=(2, 2)):
    h, w = size
    arr = np.zeros((h, w, 4), dtype=np.float32)
    arr[..., 0] = r
    arr[..., 1] = g
    arr[..., 2] = b
    arr[..., 3] = a
    return arr


# --- helpers ---

def test_split_returns_rgb_and_alpha():
    img = _rgba(0.1, 0.2, 0.3, 0.5)
    rgb, a = blending._split(img)
    assert rgb.shape == (2, 2, 3)
    assert a.shape == (2, 2, 1)
    np.testing.assert_allclose(rgb[..., 0], 0.1)
    np.testing.assert_allclose(a[..., 0], 0.5)


def test_combine_clips_to_unit_range():
    rgb = np.full((2, 2, 3), 1.5, dtype=np.float32)
    a = np.full((2, 2, 1), -0.2, dtype=np.float32)
    out = blending._combine(rgb, a)
    assert out.shape == (2, 2, 4)
    assert out.max() <= 1.0
    assert out.min() >= 0.0


# --- per-mode identities ---

def test_normal_returns_top_unchanged():
    base = _rgba(0.3, 0.3, 0.3, 1.0)
    top = _rgba(0.7, 0.0, 0.0, 1.0)
    np.testing.assert_array_equal(normal(base, top), top)


def test_multiply_with_white_is_identity():
    base = _rgba(1.0, 1.0, 1.0, 1.0)
    top = _rgba(0.4, 0.5, 0.6, 1.0)
    out = multiply(base, top)
    np.testing.assert_allclose(out[..., :3], top[..., :3])


def test_multiply_with_black_is_black():
    base = _rgba(0.0, 0.0, 0.0, 1.0)
    top = _rgba(0.4, 0.5, 0.6, 1.0)
    out = multiply(base, top)
    np.testing.assert_allclose(out[..., :3], 0.0)


def test_screen_with_black_is_top():
    base = _rgba(0.0, 0.0, 0.0, 1.0)
    top = _rgba(0.2, 0.4, 0.6, 1.0)
    out = screen(base, top)
    np.testing.assert_allclose(out[..., :3], top[..., :3])


def test_screen_with_white_is_white():
    base = _rgba(1.0, 1.0, 1.0, 1.0)
    top = _rgba(0.2, 0.4, 0.6, 1.0)
    out = screen(base, top)
    np.testing.assert_allclose(out[..., :3], 1.0)


def test_overlay_at_half_grey_doubles_top():
    base = _rgba(0.5, 0.5, 0.5, 1.0)
    top = _rgba(0.25, 0.25, 0.25, 1.0)
    out = overlay(base, top)
    # base < 0.5 branch → 2 * 0.5 * 0.25 = 0.25 (matches top here)
    # but at 0.5 boundary numpy.where(False) takes high branch:
    # 1 - 2*(1-0.5)*(1-0.25) = 1 - 0.75 = 0.25
    np.testing.assert_allclose(out[..., :3], 0.25)


def test_darken_returns_min():
    base = _rgba(0.7, 0.2, 0.5, 1.0)
    top = _rgba(0.3, 0.8, 0.5, 1.0)
    out = darken(base, top)
    np.testing.assert_allclose(out[..., 0], 0.3)
    np.testing.assert_allclose(out[..., 1], 0.2)
    np.testing.assert_allclose(out[..., 2], 0.5)


def test_lighten_returns_max():
    base = _rgba(0.7, 0.2, 0.5, 1.0)
    top = _rgba(0.3, 0.8, 0.5, 1.0)
    out = lighten(base, top)
    np.testing.assert_allclose(out[..., 0], 0.7)
    np.testing.assert_allclose(out[..., 1], 0.8)
    np.testing.assert_allclose(out[..., 2], 0.5)


def test_add_clips_to_one():
    base = _rgba(0.7, 0.7, 0.7, 1.0)
    top = _rgba(0.6, 0.6, 0.6, 1.0)
    out = add(base, top)
    assert out[..., :3].max() <= 1.0


def test_subtract_clips_to_zero():
    base = _rgba(0.3, 0.3, 0.3, 1.0)
    top = _rgba(0.6, 0.6, 0.6, 1.0)
    out = subtract(base, top)
    assert out[..., :3].min() >= 0.0


def test_difference_is_abs_diff():
    base = _rgba(0.7, 0.2, 0.5, 1.0)
    top = _rgba(0.3, 0.8, 0.5, 1.0)
    out = difference(base, top)
    np.testing.assert_allclose(out[..., 0], 0.4, atol=1e-6)
    np.testing.assert_allclose(out[..., 1], 0.6, atol=1e-6)
    np.testing.assert_allclose(out[..., 2], 0.0, atol=1e-6)


# --- BLEND_MODES registry ---

def test_blend_modes_registry_has_expected_keys():
    expected = {
        "Normal", "Multiply", "Screen", "Overlay",
        "Darken", "Lighten", "Add", "Subtract", "Difference",
    }
    assert set(BLEND_MODES.keys()) == expected


@pytest.mark.parametrize("name,fn", [
    ("Normal", normal), ("Multiply", multiply), ("Screen", screen),
    ("Overlay", overlay), ("Darken", darken), ("Lighten", lighten),
    ("Add", add), ("Subtract", subtract), ("Difference", difference),
])
def test_registry_maps_to_correct_function(name, fn):
    assert BLEND_MODES[name] is fn


# --- composite() top-level ---

def test_composite_zero_opacity_keeps_base():
    base = _rgba(0.4, 0.4, 0.4, 1.0)
    top = _rgba(0.9, 0.0, 0.0, 1.0)
    out = composite(base, top, "Normal", opacity=0.0)
    np.testing.assert_allclose(out[..., :3], base[..., :3], atol=1e-6)
    np.testing.assert_allclose(out[..., 3], base[..., 3], atol=1e-6)


def test_composite_full_opacity_normal_replaces_base():
    base = _rgba(0.4, 0.4, 0.4, 1.0)
    top = _rgba(0.9, 0.1, 0.2, 1.0)
    out = composite(base, top, "Normal", opacity=1.0)
    np.testing.assert_allclose(out[..., :3], top[..., :3], atol=1e-6)


def test_composite_unknown_mode_falls_back_to_normal():
    base = _rgba(0.4, 0.4, 0.4, 1.0)
    top = _rgba(0.9, 0.1, 0.2, 1.0)
    out_unknown = composite(base, top, "NotAMode", opacity=1.0)
    out_normal = composite(base, top, "Normal", opacity=1.0)
    np.testing.assert_allclose(out_unknown, out_normal)


def test_composite_transparent_top_keeps_base():
    base = _rgba(0.4, 0.4, 0.4, 1.0)
    top = _rgba(0.9, 0.1, 0.2, 0.0)
    out = composite(base, top, "Normal", opacity=1.0)
    np.testing.assert_allclose(out[..., :3], base[..., :3], atol=1e-6)


def test_composite_output_alpha_clamped():
    base = _rgba(0.5, 0.5, 0.5, 1.0)
    top = _rgba(0.5, 0.5, 0.5, 1.0)
    out = composite(base, top, "Normal", opacity=1.0)
    assert out[..., 3].max() <= 1.0
    assert out[..., 3].min() >= 0.0
