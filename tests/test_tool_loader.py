"""Unit tests for app.tool_loader tool_id resolution."""
from __future__ import annotations

import pytest

from app.tool_loader import _slug, load_tools


# --- _slug ---

def test_slug_lowercases_and_snake_cases():
    assert _slug("Magic Wand") == "magic_wand"


def test_slug_collapses_non_alnum_runs():
    assert _slug("Sel--Transform!!") == "sel_transform"


def test_slug_strips_edges():
    assert _slug("  Brush  ") == "brush"


def test_slug_empty_falls_back_to_tool():
    assert _slug("") == "tool"
    assert _slug("---") == "tool"


def test_slug_preserves_digits():
    assert _slug("Brush 2") == "brush_2"


# --- load_tools id resolution ---

def _write_tool(tool_dir, *, body: str):
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(body, encoding="utf-8")


_TOOL_TEMPLATE = """
from app.tools import Tool

class _T(Tool):
    name = {name!r}
{extra}

TOOL_CLASS = _T
"""


def _make_tool(tool_dir, *, name: str, tool_id: str | None = None):
    extra_lines = []
    if tool_id is not None:
        extra_lines.append(f"    tool_id = {tool_id!r}")
    body = _TOOL_TEMPLATE.format(name=name, extra="\n".join(extra_lines))
    _write_tool(tool_dir, body=body)


def test_load_tools_uses_class_tool_id(tmp_path):
    brushes = tmp_path / "Brushes"
    _make_tool(brushes / "Paint" / "MyBrush", name="Brush", tool_id="brush")

    tools, _cats = load_tools(brushes, ctx=None)
    assert "Brush" in tools
    assert getattr(tools["Brush"], "tool_id", "") == "brush"


def test_load_tools_derives_tool_id_from_folder(tmp_path):
    brushes = tmp_path / "Brushes"
    _make_tool(brushes / "Select" / "Magic Wand", name="Magic Wand", tool_id=None)

    tools, _cats = load_tools(brushes, ctx=None)
    assert "Magic Wand" in tools
    assert getattr(tools["Magic Wand"], "tool_id", "") == "magic_wand"


def test_load_tools_manifest_id_overrides_class(tmp_path):
    import json

    brushes = tmp_path / "Brushes"
    tool_dir = brushes / "Paint" / "Brush"
    _make_tool(tool_dir, name="Brush", tool_id="ignored_class_id")
    (tool_dir / "tool.json").write_text(
        json.dumps({"name": "Brush", "id": "manifest_id"}),
        encoding="utf-8",
    )

    tools, _cats = load_tools(brushes, ctx=None)
    assert getattr(tools["Brush"], "tool_id", "") == "manifest_id"


def test_load_tools_empty_dir_returns_empty(tmp_path):
    tools, cats = load_tools(tmp_path / "missing", ctx=None)
    assert tools == {}
    assert cats == {}
