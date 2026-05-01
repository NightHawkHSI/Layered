"""Project document.

A `Project` is one open canvas: name, optional file path, layer stack, dirty
flag. The main window holds a list of projects and switches the canvas /
panels to the active project's stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image

from .history import History
from .layer import Layer, LayerStack


@dataclass
class Project:
    name: str
    stack: LayerStack
    path: Optional[Path] = None
    dirty: bool = False
    history: History = field(default_factory=lambda: History(max_size=50))

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
