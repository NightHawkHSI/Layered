"""Project document.

A `Project` is one open canvas: name, optional file path, layer stack, dirty
flag. The main window holds a list of projects and switches the canvas /
panels to the active project's stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .history import History
from .layer import Layer, LayerStack


@dataclass
class Selection:
    """Per-project selection mask in canvas coordinates.

    `mask` is an L-mode image the size of the canvas: 255 = inside,
    0 = outside. `bbox` is the tight bounding box for fast clipping.
    """
    bbox: tuple[int, int, int, int]
    mask: Image.Image

    @classmethod
    def rect(cls, x0: int, y0: int, x1: int, y1: int, canvas_w: int, canvas_h: int) -> "Selection":
        x0, x1 = sorted((max(0, min(canvas_w, int(x0))), max(0, min(canvas_w, int(x1)))))
        y0, y1 = sorted((max(0, min(canvas_h, int(y0))), max(0, min(canvas_h, int(y1)))))
        mask = Image.new("L", (canvas_w, canvas_h), 0)
        ImageDraw.Draw(mask).rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
        return cls(bbox=(x0, y0, x1, y1), mask=mask)

    @classmethod
    def from_mask(cls, mask: Image.Image) -> Optional["Selection"]:
        bb = mask.getbbox()
        if bb is None:
            return None
        return cls(bbox=bb, mask=mask)


@dataclass
class Project:
    name: str
    stack: LayerStack
    path: Optional[Path] = None
    dirty: bool = False
    history: History = field(default_factory=lambda: History(max_size=50))
    selection: Optional[Selection] = None

    def commit(self, label: str) -> None:
        self.history.commit(label, self.stack)

    @classmethod
    def blank(cls, width: int, height: int, name: str = "Untitled") -> "Project":
        stack = LayerStack(width, height)
        bg = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        stack.add_layer(Layer(name="Background", image=bg))
        stack.add_layer()
        stack.set_active(1)
        proj = cls(name=name, stack=stack)
        proj.history.commit("New project", stack)
        return proj

    @classmethod
    def from_image(cls, path: Path) -> "Project":
        img = Image.open(path).convert("RGBA")
        stack = LayerStack(img.width, img.height)
        stack.add_layer(Layer(name=path.stem, image=img))
        proj = cls(name=path.stem, path=path, stack=stack)
        proj.history.commit(f"Open {path.name}", stack)
        return proj

    def display_name(self) -> str:
        return f"{self.name}{'*' if self.dirty else ''}"
