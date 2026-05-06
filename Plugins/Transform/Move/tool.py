import importlib.util
import sys
from pathlib import Path

_KEY = "_layered_builtin_tools"
if _KEY not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_KEY, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_KEY] = _m
    _p.loader.exec_module(_m)


class MoveTool(sys.modules[_KEY].TransformTool):
    name = "Move"


TOOL_CLASS = MoveTool
