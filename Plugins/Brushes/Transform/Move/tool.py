import importlib.util as _iu, sys as _sys
from pathlib import Path as _P

_TRANSFORM_KEY = "_layered_tool_transform_transform"
if _TRANSFORM_KEY not in _sys.modules:
    _t_src = _P(__file__).resolve().parents[2] / "Transform" / "Transform" / "tool.py"
    _t_spec = _iu.spec_from_file_location(_TRANSFORM_KEY, _t_src)
    _t_mod = _iu.module_from_spec(_t_spec)
    _sys.modules[_TRANSFORM_KEY] = _t_mod
    _t_spec.loader.exec_module(_t_mod)
_t = _sys.modules[_TRANSFORM_KEY]


class MoveTool(_t.TransformTool):
    name = "Move"
    tool_id = "move"
    role = "move"


TOOL_CLASS = MoveTool
