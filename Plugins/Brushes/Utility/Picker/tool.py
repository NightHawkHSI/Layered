import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
_SHARED_KEY = "_layered_brushes_shared"
if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)
_sh = _sys.modules[_SHARED_KEY]

Tool = _sh.Tool
Layer = _sh.Layer
ToolContext = _sh.ToolContext


class PickerTool(Tool):
    name = "Picker"
    commit_on = None

    def __init__(self, ctx: ToolContext, on_pick=None):
        super().__init__(ctx)
        self.on_pick = on_pick

    def press(self, layer: Layer, x: int, y: int) -> None:
        if 0 <= x < layer.image.width and 0 <= y < layer.image.height:
            color = layer.image.getpixel((x, y))
            if self.on_pick:
                self.on_pick(color)


TOOL_CLASS = PickerTool
