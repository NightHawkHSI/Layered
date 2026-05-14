"""Theme engine — dark / light palettes and base QSS.

`apply_theme(app, name)` installs a full QPalette plus a base stylesheet
for the named theme. The accent colour is layered on top separately by
``MainWindow._apply_accent``, which appends after a ``/* __accent */``
marker — so the base QSS produced here must never contain that marker.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette

# Each theme is a flat colour map sharing the same keys, so the palette
# and QSS builders below stay theme-agnostic.
_DARK: dict[str, str] = {
    "window":    "#1e1f22",
    "base":      "#18191c",
    "alt_base":  "#24262a",
    "surface":   "#2b2d31",
    "border":    "#3c3f44",
    "text":      "#dcddde",
    "text_dim":  "#969798",
    "highlight": "#4a90e2",
    "bright":    "#ff5050",
}

_LIGHT: dict[str, str] = {
    "window":    "#f3f3f4",
    "base":      "#ffffff",
    "alt_base":  "#e9eaec",
    "surface":   "#e4e5e8",
    "border":    "#c4c6ca",
    "text":      "#1e1f22",
    "text_dim":  "#7a7c80",
    "highlight": "#4a90e2",
    "bright":    "#c81e1e",
}

_THEMES: dict[str, dict[str, str]] = {"dark": _DARK, "light": _LIGHT}


def _palette(c: dict[str, str]) -> QPalette:
    window   = QColor(c["window"])
    base     = QColor(c["base"])
    alt_base = QColor(c["alt_base"])
    surface  = QColor(c["surface"])
    text     = QColor(c["text"])
    text_dim = QColor(c["text_dim"])
    accent   = QColor(c["highlight"])

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    p.setColor(QPalette.ColorRole.ToolTipBase, surface)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, text_dim)
    p.setColor(QPalette.ColorRole.Button, surface)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(c["bright"]))
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, accent)
    p.setColor(QPalette.ColorRole.LinkVisited, QColor("#b48cdc"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, text_dim)
    return p


def _qss(c: dict[str, str]) -> str:
    return f"""
        QToolTip {{
            color: {c['text']}; background-color: {c['surface']};
            border: 1px solid {c['border']}; padding: 3px 6px;
        }}
        QMenu {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
        }}
        QMenu::item:selected {{
            background-color: {c['highlight']};
            color: white;
        }}
        QMenuBar {{ background-color: {c['window']}; }}
        QMenuBar::item:selected {{ background-color: {c['surface']}; }}
        QStatusBar {{ background-color: {c['window']}; }}
        QToolBar {{
            background-color: {c['window']};
            border: none; spacing: 2px;
        }}
        QDockWidget::title {{
            background: {c['surface']};
            padding: 4px 8px;
            border-bottom: 1px solid {c['border']};
        }}
        QSplitter::handle {{ background: {c['border']}; }}
        QHeaderView::section {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            padding: 4px;
        }}
        QTabBar::tab {{
            background: {c['window']}; color: {c['text']};
            padding: 6px 12px;
            border: 1px solid {c['border']};
            border-bottom: none;
        }}
        QTabBar::tab:selected {{ background: {c['surface']}; }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {c['window']}; border: none;
        }}
        QScrollBar::handle {{
            background: {c['surface']}; border-radius: 4px;
        }}
        QScrollBar::handle:hover {{ background: {c['border']}; }}
    """


def theme_names() -> list[str]:
    """Return the available theme ids, in display order."""
    return ["dark", "light"]


def apply_theme(app, name: str) -> None:
    """Install the named theme ("dark" or "light") on `app`.

    Sets both the palette and a base stylesheet. Unknown names fall back
    to the dark theme.
    """
    c = _THEMES.get(name, _DARK)
    app.setPalette(_palette(c))
    app.setStyleSheet(_qss(c))
