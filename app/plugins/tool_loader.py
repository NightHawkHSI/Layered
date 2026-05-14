"""Tool discovery: scan Brushes/<Category>/<ToolFolder>/tool.json.

Layout:
    Brushes/
      <Category>/
        <ToolFolder>/
          tool.json    # required manifest
          tool.py      # optional: custom tool implementation

Manifest schema (all keys optional except `name`):

    {
        "name":        "Brush",       # display name (key in tools dict)
        "id":          "brush",       # stable internal ID; falls back to folder name
        "class":       "BrushTool",   # class name in app.tools (used when no tool.py)
        "category":    "Basic",       # override the parent folder name (optional)
        "icon":        "🖌",          # optional glyph shown on the tool button
        "permissions": ["clipboard"]  # capabilities the tool may use (see KNOWN_PERMISSIONS)
    }

When `tool.py` is present alongside `tool.json` the loader imports it
via importlib and expects a top-level ``TOOL_CLASS`` attribute.
Discovery is best-effort: a malformed entry is skipped, the rest still
load.

Permissions are stored as a frozenset on the instance via
``Tool._granted_permissions`` and queried with ``Tool.has_permission``.
The host enforces them at API boundaries (clipboard, network, fs);
plugins that bypass the boundary in raw PyQt are out of scope of the
sandbox — Python cannot truly sandbox in-process code.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Any, Tuple

from . import tools as tools_mod

_log = logging.getLogger("layered.plugin.tool")

# Capabilities a plugin may declare. The host enforces these at the
# corresponding API call sites (ctx hooks / clipboard / network / fs).
KNOWN_PERMISSIONS: frozenset[str] = frozenset({
    "clipboard",   # read/write system clipboard
    "web",         # outbound HTTP / URL fetch
    "filesystem",  # read/write outside project sandbox
    "subprocess",  # spawn external processes
})


def _slug(text: str) -> str:
    """Normalise text into a stable lowercase snake_case ID."""
    out = re.sub(r"[^0-9a-zA-Z]+", "_", text.strip()).strip("_").lower()
    return out or "tool"


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
            tool_py = tool_dir / "tool.py"
            meta: dict = {}
            if manifest.exists():
                try:
                    meta = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            elif not tool_py.exists():
                continue
            cls = _resolve_class(tool_dir, meta)
            if cls is None:
                continue
            display_name = meta.get("name") or getattr(cls, "name", None) or tool_dir.name
            try:
                try:
                    inst = cls()
                except TypeError:
                    inst = cls(ctx)
            except Exception:
                continue
            try:
                inst.ctx = ctx
            except Exception:
                pass
            # tool_id resolution order: manifest "id" > class attr > folder slug.
            # Stable ID lets host code look tools up without depending on the
            # display name or icon, which can change without breaking refs.
            tool_id = meta.get("id") or getattr(cls, "tool_id", "") or _slug(tool_dir.name)
            try:
                inst.tool_id = tool_id
            except Exception:
                pass
            effective_cat = meta.get("category") or cat
            try:
                inst.group = effective_cat
            except Exception:
                pass
            # Manifest icon overrides class attr; either is optional.
            icon = meta.get("icon")
            if icon:
                try:
                    inst.icon = icon
                except Exception:
                    pass
            # Permissions — validate against KNOWN_PERMISSIONS. Unknown
            # entries are dropped with a warning; the tool still loads
            # with whatever subset was recognised.
            raw_perms = meta.get("permissions") or []
            if not isinstance(raw_perms, (list, tuple)):
                _log.warning(
                    "%s: 'permissions' must be a list (got %s); ignoring",
                    tool_dir, type(raw_perms).__name__,
                )
                raw_perms = []
            granted: set[str] = set()
            for p in raw_perms:
                key = str(p).strip().lower()
                if key in KNOWN_PERMISSIONS:
                    granted.add(key)
                else:
                    _log.warning(
                        "%s: unknown permission %r (allowed: %s)",
                        tool_dir, p, sorted(KNOWN_PERMISSIONS),
                    )
            try:
                inst._granted_permissions = frozenset(granted)
            except Exception:
                pass
            tools_out[display_name] = inst
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
