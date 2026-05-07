"""Bridge wrapper: load EllipseTool from Plugins/_builtin_tools.py.

Each Plugins/Brushes/<Group>/<Tool>/tool.py file is a thin wrapper that
exposes TOOL_CLASS so app.tool_loader can register the tool. The actual
implementation still lives in the legacy _builtin_tools.py module; once
every tool has been ported into its own folder this wrapper can be
replaced with a direct class definition.
"""
import importlib.util
import sys
from pathlib import Path

_KEY = "_layered_builtin_tools"
if _KEY not in sys.modules:
    src = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    spec = importlib.util.spec_from_file_location(_KEY, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_KEY] = mod
    spec.loader.exec_module(mod)


_Base = sys.modules[_KEY].EllipseTool


class EllipseTool(  # type: ignore[misc]
    _Base,
):
    name = 'Ellipse'

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField
        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)
        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px;")
            return l
        row.addWidget(lbl('Size'))
        s = SliderField(1, 200, max(1, int(ctx.brush_size)), slider_width=120)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = EllipseTool

