"""Per-project undo / redo history.

Each commit deep-copies the current `LayerStack` (layers + metadata + active
selection) and stores it under a human-readable label. Undo/redo move an
index pointer; "jump" lets the user click any past entry directly.

Memory: capped at `max_size` entries (default 50). Layer images are large,
so for very long sessions older entries are dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .layer import Layer, LayerStack


def clone_stack(stack: LayerStack) -> LayerStack:
    new = LayerStack(stack.width, stack.height)
    for layer in stack.layers:
        new.layers.append(Layer(
            name=layer.name,
            image=layer.image.copy(),
            visible=layer.visible,
            opacity=layer.opacity,
            blend_mode=layer.blend_mode,
            offset=layer.offset,
            locked=layer.locked,
            group=layer.group,
        ))
    new.active_index = stack.active_index
    return new


@dataclass
class Snapshot:
    label: str
    stack: LayerStack


class History:
    def __init__(self, max_size: int = 50):
        self.entries: list[Snapshot] = []
        self.index: int = -1
        self.max_size = max_size

    def commit(self, label: str, stack: LayerStack) -> None:
        del self.entries[self.index + 1:]
        self.entries.append(Snapshot(label=label, stack=clone_stack(stack)))
        if len(self.entries) > self.max_size:
            drop = len(self.entries) - self.max_size
            del self.entries[:drop]
        self.index = len(self.entries) - 1

    def can_undo(self) -> bool:
        return self.index > 0

    def can_redo(self) -> bool:
        return 0 <= self.index < len(self.entries) - 1

    def undo(self) -> Optional[Snapshot]:
        if not self.can_undo():
            return None
        self.index -= 1
        return self._restore_at(self.index)

    def redo(self) -> Optional[Snapshot]:
        if not self.can_redo():
            return None
        self.index += 1
        return self._restore_at(self.index)

    def jump(self, i: int) -> Optional[Snapshot]:
        if not (0 <= i < len(self.entries)):
            return None
        self.index = i
        return self._restore_at(i)

    def _restore_at(self, i: int) -> Snapshot:
        snap = self.entries[i]
        return Snapshot(label=snap.label, stack=clone_stack(snap.stack))

    def labels(self) -> list[str]:
        return [s.label for s in self.entries]
