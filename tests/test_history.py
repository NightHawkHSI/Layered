"""Unit tests for app.history undo/redo."""
from __future__ import annotations

import pytest
from PIL import Image

from app.history import History, Snapshot, clone_stack
from app.layer import Layer, LayerStack


def _stack_with(n_layers: int = 1, width: int = 4, height: int = 4) -> LayerStack:
    s = LayerStack(width, height)
    for i in range(n_layers):
        s.add_layer(name=f"L{i}")
    return s


# --- clone_stack ---

def test_clone_stack_copies_layer_count_and_metadata():
    s = _stack_with(2)
    s.layers[0].opacity = 0.42
    s.layers[1].blend_mode = "Multiply"
    s.active_index = 1

    c = clone_stack(s)
    assert len(c.layers) == 2
    assert c.layers[0].opacity == 0.42
    assert c.layers[1].blend_mode == "Multiply"
    assert c.active_index == 1


def test_clone_stack_deep_copies_images():
    s = _stack_with(1)
    c = clone_stack(s)
    # Mutating clone's pixels must not affect original.
    c.layers[0].image.putpixel((0, 0), (255, 0, 0, 255))
    assert s.layers[0].image.getpixel((0, 0)) == (0, 0, 0, 0)


# --- empty / initial state ---

def test_empty_history_cannot_undo_or_redo():
    h = History()
    assert h.can_undo() is False
    assert h.can_redo() is False
    assert h.undo() is None
    assert h.redo() is None
    assert h.labels() == []


def test_single_commit_cannot_undo_or_redo():
    h = History()
    h.commit("first", _stack_with(1))
    assert h.can_undo() is False
    assert h.can_redo() is False


# --- basic undo/redo ---

def test_two_commits_then_undo_returns_first():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(2))

    snap = h.undo()
    assert snap is not None
    assert snap.label == "a"
    assert len(snap.stack.layers) == 1


def test_undo_then_redo_returns_second():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(2))

    h.undo()
    snap = h.redo()
    assert snap is not None
    assert snap.label == "b"
    assert len(snap.stack.layers) == 2


def test_can_undo_can_redo_flags_track_index():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(2))
    h.commit("c", _stack_with(3))

    assert h.can_undo() is True
    assert h.can_redo() is False
    h.undo()
    assert h.can_undo() is True
    assert h.can_redo() is True
    h.undo()
    assert h.can_undo() is False
    assert h.can_redo() is True


# --- jump ---

def test_jump_to_valid_index():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(2))
    h.commit("c", _stack_with(3))

    snap = h.jump(0)
    assert snap is not None
    assert snap.label == "a"
    assert h.index == 0


def test_jump_out_of_range_returns_none():
    h = History()
    h.commit("a", _stack_with(1))
    assert h.jump(-1) is None
    assert h.jump(99) is None


# --- branching: commit after undo discards future ---

def test_commit_after_undo_truncates_redo_stack():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(2))
    h.commit("c", _stack_with(3))

    h.undo()  # at "b"
    h.commit("d", _stack_with(4))

    assert h.labels() == ["a", "b", "d"]
    assert h.can_redo() is False


# --- max_size cap ---

def test_max_size_drops_oldest_entries():
    h = History(max_size=3)
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(1))
    h.commit("c", _stack_with(1))
    h.commit("d", _stack_with(1))
    h.commit("e", _stack_with(1))

    assert len(h.entries) == 3
    assert h.labels() == ["c", "d", "e"]
    assert h.index == 2


# --- _restore_at returns isolated copy ---

def test_restore_returns_independent_clone():
    h = History()
    h.commit("a", _stack_with(1))
    h.commit("b", _stack_with(1))

    snap = h.undo()
    assert snap is not None
    # mutating returned snapshot must not corrupt stored entry
    snap.stack.layers[0].image.putpixel((0, 0), (255, 0, 0, 255))

    snap2 = h.undo() if h.can_undo() else h.jump(0)
    if snap2 is None:
        snap2 = h.jump(0)
    assert snap2 is not None
    assert snap2.stack.layers[0].image.getpixel((0, 0)) == (0, 0, 0, 0)


# --- labels ---

def test_labels_preserves_order():
    h = History()
    for name in ("a", "b", "c"):
        h.commit(name, _stack_with(1))
    assert h.labels() == ["a", "b", "c"]
