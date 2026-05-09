"""Shared fixtures for app/* unit tests."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def solid_rgba():
    """Factory: build a solid-color RGBA PIL image."""
    def _make(size=(8, 8), color=(255, 0, 0, 255)) -> Image.Image:
        return Image.new("RGBA", size, color)
    return _make


@pytest.fixture
def solid_arr():
    """Factory: build a solid HxWx4 float32 array in [0, 1]."""
    def _make(size=(4, 4), color=(0.5, 0.5, 0.5, 1.0)) -> np.ndarray:
        h, w = size
        arr = np.zeros((h, w, 4), dtype=np.float32)
        arr[..., 0] = color[0]
        arr[..., 1] = color[1]
        arr[..., 2] = color[2]
        arr[..., 3] = color[3]
        return arr
    return _make
