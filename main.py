"""Layered - Python image editor entry point."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _emergency_crash(exc_type, exc_value, exc_tb) -> Path:
    """Write a crash file even if app.app_ui.logger could not import."""
    from datetime import datetime
    if getattr(sys, "frozen", False):
        err_dir = Path(sys.executable).resolve().parent / "logs" / "errors"
    else:
        err_dir = Path(__file__).resolve().parent / "logs" / "errors"
    err_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = err_dir / f"startup-crash-{ts}.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"Layered startup crash - {datetime.now().isoformat()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Platform: {sys.platform}\n")
        f.write("=" * 72 + "\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    return path


def _apply_dark_palette(app) -> None:
    """Install a modern dark Fusion palette + base QSS."""
    from PyQt6.QtGui import QColor, QPalette

    bg        = QColor(30, 31, 34)
    base      = QColor(24, 25, 28)
    alt_base  = QColor(36, 38, 42)
    surface   = QColor(43, 45, 49)
    border    = QColor(60, 63, 68)
    text      = QColor(220, 221, 222)
    text_dim  = QColor(150, 151, 152)
    highlight = QColor(74, 144, 226)

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    p.setColor(QPalette.ColorRole.ToolTipBase, surface)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, text_dim)
    p.setColor(QPalette.ColorRole.Button, surface)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link, highlight)
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(180, 140, 220))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_dim)
    app.setPalette(p)

    app.setStyleSheet(
        f"""
        QToolTip {{
            color: {text.name()}; background-color: {surface.name()};
            border: 1px solid {border.name()}; padding: 3px 6px;
        }}
        QMenu {{
            background-color: {surface.name()};
            border: 1px solid {border.name()};
        }}
        QMenu::item:selected {{
            background-color: {highlight.name()};
            color: white;
        }}
        QMenuBar {{ background-color: {bg.name()}; }}
        QMenuBar::item:selected {{ background-color: {surface.name()}; }}
        QStatusBar {{ background-color: {bg.name()}; }}
        QToolBar {{
            background-color: {bg.name()};
            border: none; spacing: 2px;
        }}
        QDockWidget::title {{
            background: {surface.name()};
            padding: 4px 8px;
            border-bottom: 1px solid {border.name()};
        }}
        QSplitter::handle {{ background: {border.name()}; }}
        QHeaderView::section {{
            background: {surface.name()};
            color: {text.name()};
            border: 1px solid {border.name()};
            padding: 4px;
        }}
        QTabBar::tab {{
            background: {bg.name()}; color: {text.name()};
            padding: 6px 12px;
            border: 1px solid {border.name()};
            border-bottom: none;
        }}
        QTabBar::tab:selected {{ background: {surface.name()}; }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {bg.name()}; border: none;
        }}
        QScrollBar::handle {{
            background: {surface.name()}; border-radius: 4px;
        }}
        QScrollBar::handle:hover {{ background: {border.name()}; }}
        """
    )


def _resolve_icon_paths() -> tuple[Path, Path]:
    """Locate icon files without importing app.main_window (heavy)."""
    if getattr(sys, "frozen", False):
        project_dir = Path(sys.executable).resolve().parent
        resource_dir = Path(getattr(sys, "_MEIPASS", project_dir))
    else:
        project_dir = Path(__file__).resolve().parent
        resource_dir = project_dir
    ico = resource_dir / "Icon.ico"
    if not ico.exists():
        ico = project_dir / "Icon.ico"
    png = resource_dir / "Icon.png"
    if not png.exists():
        png = project_dir / "Icon.png"
    return ico, png


def main() -> int:
    # Light imports only. Heavy stuff (app.main_window which pulls PIL,
    # numpy, plugin_loader, UI panels) is deferred until the shell window
    # is on screen.
    try:
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QColor, QIcon, QPixmap
        from PyQt6.QtWidgets import QApplication, QSplashScreen
    except Exception:
        report = _emergency_crash(*sys.exc_info())
        msg = (
            f"Layered failed to start. Crash report: {report}\n"
            f"Likely cause: missing dependency. Run:\n"
            f"  py -3 -m pip install -r requirements.txt\n"
        )
        if sys.stderr is not None:
            sys.stderr.write(msg)
            traceback.print_exc()
        return 2

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Layered")
    app.setOrganizationName("Layered")
    _apply_dark_palette(app)

    ICON_PATH, ICON_PNG_PATH = _resolve_icon_paths()
    app_icon = None
    if ICON_PATH.exists():
        app_icon = QIcon(str(ICON_PATH))
    elif ICON_PNG_PATH.exists():
        app_icon = QIcon(str(ICON_PNG_PATH))
    if app_icon is not None:
        app.setWindowIcon(app_icon)

    # Show a splash immediately so the user gets instant feedback while the
    # heavy imports and full window construction run. Without it the process
    # appears to hang, then a half-built shell window flashes on screen.
    splash = None
    if ICON_PNG_PATH.exists():
        pix = QPixmap(str(ICON_PNG_PATH))
        if not pix.isNull():
            pix = pix.scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            splash = QSplashScreen(pix)
            splash.showMessage(
                "Loading Layered…",
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                QColor(220, 221, 222),
            )
            splash.show()
            app.processEvents()

    holder: dict = {"window": None}

    def _bring_up_main() -> None:
        try:
            from app.app_ui.logger import get_logger, install_excepthook
            install_excepthook()
            log = get_logger("main")
            log.info("Layered starting up")
            from app.main_window import MainWindow
            win = MainWindow()
            win.show()
            if splash is not None:
                splash.finish(win)
            holder["window"] = win
        except Exception:
            if splash is not None:
                splash.close()
            try:
                report = _emergency_crash(*sys.exc_info())
                msg = f"Layered failed to start. Crash report: {report}\n"
                if sys.stderr is not None:
                    sys.stderr.write(msg)
            except Exception:
                traceback.print_exc()
            app.quit()

    QTimer.singleShot(0, _bring_up_main)

    rc = app.exec()
    return rc


if __name__ == "__main__":
    sys.exit(main())
