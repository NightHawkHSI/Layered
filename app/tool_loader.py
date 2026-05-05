"""Tool discovery: scan Brushes/<Category>/<ToolFolder>/tool.json.

Layout:
    Brushes/
      <Category>/
        <ToolFolder>/
          tool.json    # required manifest
          tool.py      # optional: custom tool implementation

Manifest schema (all keys optional except `name`):

    {
        "name":     "Brush",       # display name (key in tools dict)
        "class":    "BrushTool",      # class name in app.tools (used when no tool.py)
        "category": "Basic"           # override the parent folder name (optional)
    }

When `tool.py` is present alongside `tool.json` the loader imports it
via importlib and expects a top-level ``TOOL_CLASS`` attribute.
Discovery is best-effort: a malformed entry is skipped, the rest still
load.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Tuple

from . import tools as tools_mod


def load_tools(brushes_dir: Path, ctx) -> Tuple[dict[str, Any], dict[str, list[str]]]:
    """Return ``(tools_by_name, categories_map)``.

    * ``tools_by_name`` maps display name -> instantiated Tool.
    * ``categories_map`` maps category name -> ordered list of display names
      that live under that category folder.
    """
    tools_out: dict[str, Any] = {}
    cats_out: dict[str, list[str]] = {}
    if not brushes_dir.exists():
        return tools_out, cats_out

    for cat_dir in sorted(brushes_dir.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        for tool_dir in sorted(cat_dir.iterdir()):
            if not tool_dir.is_dir():
                continue
            manifest = tool_dir / "tool.json"
            if not manifest.exists():
                continue
            try:
                meta = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                continue
            display_name = meta.get("name")
            if not display_name:
                continue
            cls = _resolve_class(tool_dir, meta)
            if cls is None:
                continue
            try:
                tools_out[display_name] = cls(ctx)
            except Exception:
                continue
            effective_cat = meta.get("category") or cat
            cats_out.setdefault(effective_cat, []).append(display_name)
    return tools_out, cats_out


def _resolve_class(tool_dir: Path, meta: dict) -> Any:
    """Locate the Tool subclass for ``tool_dir``.

    Order: sibling `tool.py` (TOOL_CLASS attr), then `class` field of
    the manifest looked up in ``app.tools``. Returns ``None`` on failure.
    """
    tool_py = tool_dir / "tool.py"
    if tool_py.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                f"_layered_tool_{tool_dir.parent.name}_{tool_dir.name}", tool_py
            )
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                cls = getattr(mod, "TOOL_CLASS", None)
                if cls is not None:
                    return cls
        except Exception:
            pass
    cls_name = meta.get("class")
    if cls_name:
        return getattr(tools_mod, cls_name, None)
    return None
