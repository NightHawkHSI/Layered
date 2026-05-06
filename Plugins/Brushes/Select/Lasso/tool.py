"""Select / Lasso --- freehand polygon selection."""
from __future__ import annotations
from PIL import Image, ImageChops, ImageDraw
from app.tools import Tool


class LassoTool(Tool):
    name = "Lasso"
    commit_on = None

    def __init__(self):
        self._pts = []

    def _canvas_size(self, ctx):
        if ctx.get_canvas_size:
            try:
                return ctx.get_canvas_size()
            except Exception:
                pass
        layer = ctx.active_layer
        if layer is None:
            return (0, 0)
        ox, oy = layer.offset
        return layer.image.width + max(0, ox), layer.image.height + max(0, oy)

    def on_mouse_down(self, ctx, x, y):
        self._pts = [(x, y)]

    def on_mouse_drag(self, ctx, x, y):
        self._pts.append((x, y))

    def on_mouse_up(self, ctx, x, y):
        if len(self._pts) < 3:
            self._pts = []
            return
        self._pts.append(self._pts[0])  # close polygon
        cw, ch = self._canvas_size(ctx)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).polygon(self._pts, fill=255)
        self._pts = []
        if ctx.set_selection:
            from app.project import Selection
            ctx.set_selection(Selection.from_mask(mask))

    def build_ui(self, parent, ctx):
        return None


TOOL_CLASS = LassoTool
