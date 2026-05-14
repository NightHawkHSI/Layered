"""Unit tests for app.image_ops placement helpers."""
from __future__ import annotations

import pytest
from PIL import Image

from app.core.image_ops import centered_offset, fit_to_canvas, place_on_canvas


# --- fit_to_canvas ---

def test_fit_to_canvas_passes_through_when_already_fits():
    img = Image.new("RGBA", (4, 4))
    out = fit_to_canvas(img, 8, 8)
    assert out is img


def test_fit_to_canvas_passes_through_at_exact_size():
    img = Image.new("RGBA", (8, 8))
    out = fit_to_canvas(img, 8, 8)
    assert out is img


def test_fit_to_canvas_scales_down_preserving_aspect():
    img = Image.new("RGBA", (200, 100))  # 2:1
    out = fit_to_canvas(img, 50, 50)
    # min(50/200, 50/100) = 0.25 → (50, 25)
    assert out.size == (50, 25)


def test_fit_to_canvas_minimum_dimension_of_one():
    img = Image.new("RGBA", (1000, 1))
    out = fit_to_canvas(img, 10, 10)
    # scale = 10/1000 = 0.01 → (10, max(1, round(0.01)))
    assert out.size[0] == 10
    assert out.size[1] >= 1


# --- centered_offset ---

def test_centered_offset_basic():
    assert centered_offset((4, 4), 10, 10) == (3, 3)


def test_centered_offset_image_larger_than_canvas_negative():
    assert centered_offset((20, 20), 10, 10) == (-5, -5)


def test_centered_offset_zero_when_equal():
    assert centered_offset((10, 10), 10, 10) == (0, 0)


# --- place_on_canvas ---

def test_place_on_canvas_returns_canvas_size():
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    out = place_on_canvas(img, 10, 10)
    assert out.size == (10, 10)
    assert out.mode == "RGBA"


def test_place_on_canvas_centers_by_default():
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    out = place_on_canvas(img, 10, 10)
    # centered at offset (3, 3); pixel (3,3) is image, (0,0) is transparent.
    assert out.getpixel((3, 3)) == (255, 0, 0, 255)
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)


def test_place_on_canvas_anchors_top_left_when_not_centered():
    img = Image.new("RGBA", (4, 4), (0, 255, 0, 255))
    out = place_on_canvas(img, 10, 10, center=False)
    assert out.getpixel((0, 0)) == (0, 255, 0, 255)
    assert out.getpixel((9, 9)) == (0, 0, 0, 0)


def test_place_on_canvas_scales_oversized_when_scale_to_fit():
    img = Image.new("RGBA", (40, 20), (0, 0, 255, 255))
    out = place_on_canvas(img, 10, 10, scale_to_fit=True)
    assert out.size == (10, 10)
    # scaled to (10, 5), centered → vertical offset = 2
    # pixel within scaled image area should be blue/opaque
    assert out.getpixel((5, 4))[3] == 255


def test_place_on_canvas_converts_non_rgba_input():
    img = Image.new("RGB", (4, 4), (10, 20, 30))
    out = place_on_canvas(img, 10, 10)
    assert out.mode == "RGBA"
    px = out.getpixel((5, 5))
    assert px == (10, 20, 30, 255)
