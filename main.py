"""Layered - Python image editor entry point."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _emergency_crash(exc_type, exc_value, exc_tb) -> Path:
    """Write a crash file even if app.logger could not import."""
    from datetime import datetime
    if getattr(sys, "frozen", False):
        err_dir = Path(sys.executable).resolve().parent / "logs" / "errors"
    else:
        err_dir = Path(__file__).resolve().parent / "logs" / "errors"
    err_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = err_dir / f"startup-crash-{ts}.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"Layered startup crash — {datetime.now().isoformat()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Platform: {sys.platform}\n")
        f.write("=" * 72 + "\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    return path


def main() -> int:
    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication

        from app.logger import get_logger, install_excepthook
        from app.main_window import ICON_PATH, ICON_PNG_PATH, MainWindow
        try:
            from app.splash import SplashScreen
        except Exception:
            SplashScreen = None  # type: ignore[assignment,misc]
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

    install_excepthook()
    log = get_logger("main")
    log.info("Layered starting up")

    app = QApplication(sys.argv)
    # Fusion gives consistent, crisp dock drop indicators across platforms
    # so dragging a panel shows VSCode-style snap zones reliably.
    app.setStyle("Fusion")
    app.setApplicationName("Layered")
    app.setOrganizationName("Layered")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    elif ICON_PNG_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PNG_PATH)))

    icon_png = ICON_PNG_PATH if ICON_PNG_PATH.exists() else None
    splash = SplashScreen(icon_png) if SplashScreen is not None else None
    if splash is not None:
        splash.show()
        splash.set_progress(3, "Initializing Qt runtime...")
        app.processEvents()
        splash.set_progress(8, "Preparing workspace...")

    try:
        window = MainWindow(splash=splash)
        if splash is not None:
            splash.set_progress(100, "Ready — welcome back")
            splash.finish(window)
        window.show()
    except Exception:
        if splash is not None:
            splash.hide()
        log.critical("Failed to construct main window:\n%s", traceback.format_exc())
        raise

    rc = app.exec()
    log.info("Layered exiting with code %s", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
