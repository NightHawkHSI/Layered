"""Bridge wrapper: load TransformTool from Plugins/_builtin_tools.py.

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

TOOL_CLASS = sys.modules[_KEY].TransformTool
