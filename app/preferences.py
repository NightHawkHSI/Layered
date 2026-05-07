"""User preferences: persistent settings saved to prefs.json.

Stored next to the session/ folder so they survive app updates.
All keys have safe defaults so the file being absent is harmless.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULTS: dict = {
    "accent_color":     "#2196f3",   # Material Blue 500
    "restore_session":  True,        # reopen projects from last run
}


class Preferences:
    """Thin wrapper around a JSON prefs file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict = dict(_DEFAULTS)
        self.load()

    # ?? persistence ???????????????????????????????????????????????????????

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except Exception:
            pass

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2), encoding="utf-8"
        )

    # ?? accessors ?????????????????????????????????????????????????????????

    @property
    def accent_color(self) -> str:
        return str(self._data.get("accent_color", _DEFAULTS["accent_color"]))

    @accent_color.setter
    def accent_color(self, value: str) -> None:
        self._data["accent_color"] = str(value)

    @property
    def restore_session(self) -> bool:
        return bool(self._data.get("restore_session", _DEFAULTS["restore_session"]))

    @restore_session.setter
    def restore_session(self, value: bool) -> None:
        self._data["restore_session"] = bool(value)
