"""Unit tests for app.layer Layer / LayerStack."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.layer import Layer, LayerStack, _scale_alpha


# --- Layer ---

def test_layer_to_array_shape_and_dtype():
    img = Image.new("RGBA", (4, 3), (128, 0, 0, 255))
    layer = Layer(name="x", image=img)
    arr = layer.to_array()
    assert arr.shape == (3, 4, 4)
    assert arr.dtype == np.float32
    assert arr.max() <= 1.0
    assert arr.min() >= 0.0


def test_layer_to_array_converts_non_rgba():
    img = Image.new("RGB", (2, 2), (100, 100, 100))
    layer = Layer(name="x", image=img)
    arr = layer.to_array()
    assert arr.shape == (2, 2, 4)
    assert layer.image.mode == "RGBA"


def test_replace_image_converts_to_rgba():
    layer = Layer(name="x", image=Image.new("RGBA", (2, 2)))
    layer.replace_image(Image.new("RGB", (2, 2), (50, 50, 50)))
    assert layer.image.mode == "RGBA"


# --- _scale_alpha ---

def test_scale_alpha_passthrough_at_full_opacity():
    img = Image.new("RGBA", (2, 2), (255, 0, 0, 200))
    out = _scale_alpha(img, 1.0)
    assert out is img


def test_scale_alpha_halves_alpha_channel():
    img = Image.new("RGBA", (2, 2), (255, 0, 0, 200))
    out = _scale_alpha(img, 0.5)
    _, _, _, a = out.split()
    assert a.getpixel((0, 0)) == 100


# --- LayerStack basic ops ---

def test_empty_stack_has_no_active():
    s = LayerStack(8, 8)
    assert s.active is None
    assert len(s) == 0


def test_add_layer_creates_blank_at_canvas_size():
    s = LayerStack(8, 6)
    layer = s.add_layer()
    assert layer.image.size == (8, 6)
    assert layer.image.mode == "RGBA"
    assert s.active is layer
    assert s.active_index == 0


def test_add_layer_uses_provided_name():
    s = LayerStack(4, 4)
    s.add_layer(name="custom")
    assert s.layers[0].name == "custom"


def test_remove_active_returns_removed_layer():
    s = LayerStack(4, 4)
    s.add_layer(name="a")
    s.add_layer(name="b")
    removed = s.remove_active()
    assert removed.name == "b"
    assert len(s) == 1
    assert s.active.name == "a"


def test_remove_active_on_empty_returns_none():
    s = LayerStack(4, 4)
    assert s.remove_active() is None


def test_move_clamps_destination():
    s = LayerStack(4, 4)
    s.add_layer(name="a")
    s.add_layer(name="b")
    s.add_layer(name="c")
    s.move(0, 99)
    assert [l.name for l in s.layers] == ["b", "c", "a"]
    assert s.active_index == 2


def test_move_invalid_source_is_noop():
    s = LayerStack(4, 4)
    s.add_layer(name="a")
    before = list(s.layers)
    s.move(99, 0)
    assert s.layers == before


def test_set_active_ignores_out_of_range():
    s = LayerStack(4, 4)
    s.add_layer(name="a")
    s.set_active(5)
    assert s.active_index == 0


# --- composite ---

def test_composite_empty_stack_returns_transparent():
    s = LayerStack(4, 4)
    out = s.composite()
    assert out.size == (4, 4)
    arr = np.asarray(out)
    assert arr[..., 3].max() == 0


def test_composite_single_normal_layer_returns_layer_pixels():
    s = LayerStack(4, 4)
    s.add_layer()
    s.layers[0].image = Image.new("RGBA", (4, 4), (200, 50, 25, 255))
    out = s.composite()
    assert out.getpixel((0, 0)) == (200, 50, 25, 255)


def test_composite_invalidates_after_active_change():
    s = LayerStack(4, 4)
    s.add_layer()
    s.add_layer()
    s.composite()
    assert s._below_cache is not None
    s.set_active(0)
    assert s._below_cache is None


def test_composite_uses_below_cache_when_active_unchanged():
    s = LayerStack(4, 4)
    s.add_layer()
    s.add_layer()
    s.composite()
    cached = s._below_cache
    s.composite()
    assert s._below_cache is cached


# --- merge ---

def test_merge_down_combines_two_layers():
    s = LayerStack(4, 4)
    s.add_layer()
    s.layers[0].image = Image.new("RGBA", (4, 4), (50, 50, 50, 255))
    s.add_layer()
    s.layers[1].image = Image.new("RGBA", (4, 4), (100, 0, 0, 255))
    new_idx = s.merge_down(1)
    assert new_idx == 0
    assert len(s) == 1
    # top was opaque, full-cover → result equals top color
    assert s.layers[0].image.getpixel((0, 0)) == (100, 0, 0, 255)


def test_merge_down_refuses_locked_below():
    s = LayerStack(4, 4)
    s.add_layer()
    s.layers[0].locked = True
    s.add_layer()
    assert s.merge_down(1) is None
    assert len(s) == 2


def test_merge_down_invalid_index_returns_none():
    s = LayerStack(4, 4)
    s.add_layer()
    assert s.merge_down(0) is None
    assert s.merge_down(99) is None


def test_merge_up_combines_two_layers():
    s = LayerStack(4, 4)
    s.add_layer()
    s.layers[0].image = Image.new("RGBA", (4, 4), (100, 0, 0, 255))
    s.add_layer()
    s.layers[1].image = Image.new("RGBA", (4, 4), (50, 50, 50, 255))
    new_idx = s.merge_up(0)
    assert new_idx == 0
    assert len(s) == 1


def test_merge_up_refuses_locked_above():
    s = LayerStack(4, 4)
    s.add_layer()
    s.add_layer()
    s.layers[1].locked = True
    assert s.merge_up(0) is None
    assert len(s) == 2


# --- resize_canvas ---

def test_resize_canvas_updates_dims_and_extends_layers():
    s = LayerStack(4, 4)
    s.add_layer()
    s.layers[0].image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    s.resize_canvas(8, 8)
    assert s.width == 8
    assert s.height == 8
    assert s.layers[0].image.size == (8, 8)
    # original pixels preserved at (0,0)
    assert s.layers[0].image.getpixel((0, 0)) == (255, 0, 0, 255)
    # new area transparent
    assert s.layers[0].image.getpixel((7, 7)) == (0, 0, 0, 0)
