"""Logging + crash reporting.

Two channels:
  * `layered.log` — rolling app log (user actions, system events, plugin activity).
  * `errors/<timestamp>.txt` — structured crash reports with stack traces.

`get_plugin_logger(name)` returns a sandboxed logger that prefixes records with
the plugin name so plugin activity is identifiable in logs and the in-app
console.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

if getattr(sys, "frozen", False):
    LOG_DIR = Path(sys.executable).resolve().parent / "logs"
else:
    LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
ERROR_DIR = LOG_DIR / "errors"
LOG_FILE = LOG_DIR / "layered.log"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False
_console_handlers: list[logging.Handler] = []


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)


def _configure() -> None:
    global _configured
    if _configured:
        return
    _ensure_dirs()

    root = logging.getLogger("layered")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(stream_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"layered.{name}")


def get_plugin_logger(plugin_name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"layered.plugin.{plugin_name}")


def attach_console_handler(callback: Callable[[str], None]) -> logging.Handler:
    """Attach a callback-driven handler so the in-app console can show logs."""
    _configure()

    class _CallbackHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                callback(self.format(record))
            except Exception:
                pass

    h = _CallbackHandler(level=logging.DEBUG)
    h.setFormatter(logging.Formatter(_FORMAT))
    logging.getLogger("layered").addHandler(h)
    _console_handlers.append(h)
    return h


def write_crash_report(exc_type, exc_value, exc_tb) -> Path:
    _ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = ERROR_DIR / f"crash-{ts}.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"Layered crash report — {datetime.now().isoformat()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Platform: {sys.platform}\n")
        f.write(f"Pid: {os.getpid()}\n")
        f.write("=" * 72 + "\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    return path


def install_excepthook() -> None:
    log = get_logger("excepthook")

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        report = write_crash_report(exc_type, exc_value, exc_tb)
        log.critical(
            "Unhandled exception: %s — report: %s",
            exc_value,
            report,
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = _hook
