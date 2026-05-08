import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
from typing import Callable, Optional
from PIL import ImageFont
from app.tools import _resolve_windows_font

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
Image = _sh.Image
ImageDraw = _sh.ImageDraw
ToolContext = _sh.ToolContext


class TextTool(Tool):
    """Click to drop a re-editable text layer."""
    name = "Text"
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._target_stack = None
        self._target_layer: Optional[Layer] = None
        self._position: tuple[int, int] = (0, 0)
        self.on_layer_committed: Optional[Callable[[str], None]] = None
        self.on_layer_created: Optional[Callable[[], None]] = None

    def attach_stack(self, stack) -> None:
        self._target_stack = stack

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._target_stack is None:
            return
        if self._target_layer is not None and self._target_layer in self._target_stack.layers:
            label = self._commit_active()
            if label and self.on_layer_committed is not None:
                try:
                    self.on_layer_committed(label)
                except Exception:
                    pass
        new_layer = Layer(
            name="Text",
            image=Image.new("RGBA", (self._target_stack.width, self._target_stack.height), (0, 0, 0, 0)),
        )
        self._target_stack.add_layer(new_layer)
        self._target_layer = new_layer
        self._position = (x, y)
        self.rerender()
        if self.on_layer_created is not None:
            try:
                self.on_layer_created()
            except Exception:
                pass

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._target_layer is None:
            return
        self._position = (x, y)
        self.rerender()

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    def rerender(self) -> None:
        if self._target_layer is None or self._target_stack is None:
            return
        text = self.ctx.text or ""
        size = max(4, int(self.ctx.text_size))
        font = self._load_font(getattr(self.ctx, "text_font", "") or "", size)
        canvas = Image.new(
            "RGBA",
            (self._target_stack.width, self._target_stack.height),
            (0, 0, 0, 0),
        )
        if text:
            d = ImageDraw.Draw(canvas)
            try:
                d.multiline_text(self._position, text, fill=self.ctx.primary_color, font=font)
            except Exception:
                d.text(self._position, text, fill=self.ctx.primary_color, font=font)
        self._target_layer.image = canvas
        self._target_stack.invalidate_cache()

    def _commit_active(self) -> Optional[str]:
        if self._target_layer is None:
            return None
        label = f"Text: {self.ctx.text or ''}"[:40]
        self._target_layer = None
        return label

    def commit(self) -> Optional[str]:
        return self._commit_active()

    def _load_font(self, family: str, size: int):
        if family:
            path = _resolve_windows_font(family)
            if path:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        candidates = []
        if family:
            candidates.append(family)
            candidates.append(f"{family}.ttf")
            candidates.append(f"{family.lower()}.ttf")
        candidates.extend(["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
        for c in candidates:
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
        return ImageFont.load_default()


TOOL_CLASS = TextTool
