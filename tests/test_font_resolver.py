"""Unit tests for cross-platform font resolution in app.tools."""
from __future__ import annotations

import pytest

from app.plugins import tools as tools_mod
from app.plugins.tools import resolve_font_path


@pytest.fixture
def fake_font_dir(tmp_path, monkeypatch):
    """Build a tmp dir with stub font files and rewire tools to scan only it."""
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "Arial.ttf").write_bytes(b"\x00")
    (fonts / "DejaVuSans.ttf").write_bytes(b"\x00")
    (fonts / "Helvetica-Bold.otf").write_bytes(b"\x00")

    # Reset the module-level cache so each test sees a fresh build.
    monkeypatch.setattr(tools_mod, "_FONT_PATH_CACHE", {})
    monkeypatch.setattr(tools_mod, "_FONT_CACHE_BUILT", False)
    monkeypatch.setattr(tools_mod, "_font_dirs", lambda: [str(fonts)])
    # Skip Windows registry scan in tests so we only see the tmp fonts.
    monkeypatch.setattr(tools_mod, "_index_windows_registry", lambda: None)
    return fonts


def test_resolves_exact_filename_stem(fake_font_dir):
    path = resolve_font_path("Arial")
    assert path is not None
    assert path.lower().endswith("arial.ttf")


def test_lookup_is_case_insensitive(fake_font_dir):
    assert resolve_font_path("arial") == resolve_font_path("ARIAL")


def test_returns_none_for_unknown_family(fake_font_dir):
    assert resolve_font_path("NotInstalledFont") is None


def test_returns_none_for_empty_family(fake_font_dir):
    assert resolve_font_path("") is None


def test_resolves_hyphenated_name_via_squashed_index(fake_font_dir):
    # Filename: Helvetica-Bold.otf — query as "HelveticaBold".
    path = resolve_font_path("HelveticaBold")
    assert path is not None
    assert "Helvetica-Bold.otf" in path


def test_strips_trailing_style_words(fake_font_dir):
    # "Arial Bold" -> falls back to "Arial" after style strip.
    path = resolve_font_path("Arial Bold")
    assert path is not None
    assert path.lower().endswith("arial.ttf")


def test_indexes_otf_extension(fake_font_dir):
    path = resolve_font_path("Helvetica-Bold")
    assert path is not None
    assert path.lower().endswith(".otf")


def test_back_compat_alias_resolve_windows_font(fake_font_dir):
    # The old Windows-only name still works for any plugin that imported it.
    assert tools_mod._resolve_windows_font("Arial") == resolve_font_path("Arial")


def test_back_compat_alias_build_windows_font_cache(fake_font_dir):
    # Existing callers may invoke the old build-cache name explicitly.
    tools_mod._FONT_CACHE_BUILT = False
    tools_mod._FONT_PATH_CACHE.clear()
    tools_mod._build_windows_font_cache()
    assert tools_mod._FONT_CACHE_BUILT is True
    assert tools_mod._FONT_PATH_CACHE  # populated


def test_skips_non_font_extensions(tmp_path, monkeypatch):
    fonts = tmp_path / "f"
    fonts.mkdir()
    (fonts / "Arial.txt").write_bytes(b"")  # not a font file
    (fonts / "Real.ttf").write_bytes(b"")

    monkeypatch.setattr(tools_mod, "_FONT_PATH_CACHE", {})
    monkeypatch.setattr(tools_mod, "_FONT_CACHE_BUILT", False)
    monkeypatch.setattr(tools_mod, "_font_dirs", lambda: [str(fonts)])
    monkeypatch.setattr(tools_mod, "_index_windows_registry", lambda: None)

    assert resolve_font_path("Arial") is None
    assert resolve_font_path("Real") is not None
