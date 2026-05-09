import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
from typing import Optional
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
ImageChops = _sh.ImageChops
ToolContext = _sh.ToolContext


class SelectionTransformTool(Tool):
    """Transform the active selection: drag handles to scale/move."""
    name = "Sel Transform"
    tool_id = "sel_transform"
    role = "sel_transform"
    commit_on = None
    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._lift_layer: Optional[Layer] = None
        self._base: Optional[Image.Image] = None
        self._floating: Optional[Image.Image] = None
        self._float_mask: Optional[Image.Image] = None
        self._bbox: Optional[tuple[int, int, int, int]] = None
        self._mode: Optional[str] = None
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._bbox_at_press: Optional[tuple[int, int, int, int]] = None

    def _ensure_lifted(self, layer: Layer) -> bool:
        if self._floating is not None and self._lift_layer is layer:
            return True
        if self.ctx.get_selection is None:
            return False
        sel = self.ctx.get_selection()
        if sel is None or getattr(sel, "mask", None) is None:
            return False
        bb = sel.mask.getbbox()
        if bb is None:
            return False

        canvas_w, canvas_h = self._canvas_size(layer)
        canvas_mask = sel.mask
        if canvas_mask.size != (canvas_w, canvas_h):
            full = Image.new("L", (canvas_w, canvas_h), 0)
            full.paste(canvas_mask, (0, 0))
            canvas_mask = full

        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(canvas_mask, (-ox, -oy))

        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        lr, lg, lb, la = src.split()

        floating_layer_alpha = ImageChops.multiply(la, layer_mask)
        floating_layer = Image.merge("RGBA", (lr, lg, lb, floating_layer_alpha))
        floating = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        floating.paste(floating_layer, (ox, oy))

        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base = Image.merge("RGBA", (lr, lg, lb, base_alpha))

        self._lift_layer = layer
        self._base = base
        self._floating = floating
        self._float_mask = canvas_mask
        self._bbox = bb
        layer.image = base.copy()
        self._render_preview(layer)
        return True

    def _canvas_size(self, layer: Layer) -> tuple[int, int]:
        getter = getattr(self.ctx, "get_canvas_size", None)
        if getter is not None:
            try:
                size = getter()
                if size is not None:
                    return int(size[0]), int(size[1])
            except Exception:
                pass
        ox, oy = layer.offset
        return layer.image.width + max(0, ox), layer.image.height + max(0, oy)

    def _hit_handle(self, x: int, y: int) -> Optional[str]:
        if self._bbox is None:
            return None
        x0, y0, x1, y1 = self._bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        hit_r = max(8, int(self.HANDLE_SIZE / zoom))
        best: Optional[tuple[str, int]] = None
        for name, (hx, hy) in handles.items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= hit_r * hit_r and (best is None or d < best[1]):
                best = (name, d)
        if best:
            return best[0]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if not self._ensure_lifted(layer):
            return
        hit = self._hit_handle(x, y)
        if hit is None:
            self._commit_floating(layer)
            return
        self._press_pt = (x, y)
        self._bbox_at_press = self._bbox
        if hit == "move":
            self._mode = "move"
        else:
            self._mode = "scale"
            self._anchor = hit

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._mode is None or self._bbox_at_press is None or self._press_pt is None:
            return
        x0, y0, x1, y1 = self._bbox_at_press
        px, py = self._press_pt
        dx, dy = x - px, y - py

        if self._mode == "move":
            self._bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        else:
            a = self._anchor or ""
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
            if "w" in a: nx0 += dx
            if "e" in a: nx1 += dx
            if "n" in a: ny0 += dy
            if "s" in a: ny1 += dy
            nx0, nx1 = sorted((nx0, nx1))
            ny0, ny1 = sorted((ny0, ny1))
            if self.ctx.shift_held:
                ow = max(1, x1 - x0); oh = max(1, y1 - y0)
                nw = max(1, nx1 - nx0); nh = max(1, ny1 - ny0)
                scale = max(nw / ow, nh / oh)
                tw = max(1, int(round(ow * scale)))
                th = max(1, int(round(oh * scale)))
                if "e" in a:
                    nx0, nx1 = x0, x0 + tw
                elif "w" in a:
                    nx0, nx1 = x1 - tw, x1
                else:
                    cx = (x0 + x1) // 2
                    nx0, nx1 = cx - tw // 2, cx - tw // 2 + tw
                if "s" in a:
                    ny0, ny1 = y0, y0 + th
                elif "n" in a:
                    ny0, ny1 = y1 - th, y1
                else:
                    cy = (y0 + y1) // 2
                    ny0, ny1 = cy - th // 2, cy - th // 2 + th
            self._bbox = (nx0, ny0, nx1, ny1)

        self._render_preview(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._mode = None
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None
        super().release(layer, x, y)

    def _render_preview(self, layer: Layer) -> None:
        if self._floating is None or self._base is None or self._bbox is None:
            return
        scaled, scaled_mask = self._scaled_floating()
        nx0, ny0, nx1, ny1 = self._bbox
        ox, oy = layer.offset
        canvas_layer = self._base.copy()
        dest = (nx0 - ox, ny0 - oy)
        if scaled.size[0] > 0 and scaled.size[1] > 0:
            tmp = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
            tmp.paste(scaled, dest, scaled_mask)
            canvas_layer.alpha_composite(tmp)
        layer.image = canvas_layer
        if self.ctx.set_selection is not None and scaled_mask is not None:
            from app.project import Selection
            cw, ch = self._canvas_size(layer)
            new_mask = Image.new("L", (cw, ch), 0)
            new_mask.paste(scaled_mask, (nx0, ny0))
            self.ctx.set_selection(Selection(bbox=(nx0, ny0, nx1, ny1), mask=new_mask))

    def _scaled_floating(self) -> tuple[Image.Image, Image.Image]:
        assert self._floating is not None and self._float_mask is not None and self._bbox is not None
        nx0, ny0, nx1, ny1 = self._bbox
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        orig_bb = self._float_mask.getbbox()
        if orig_bb is None:
            empty = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
            empty_mask = Image.new("L", (nw, nh), 0)
            return empty, empty_mask
        crop_rgba = self._floating.crop(orig_bb)
        crop_mask = self._float_mask.crop(orig_bb)
        scaled = crop_rgba.resize((nw, nh), Image.Resampling.LANCZOS)
        scaled_mask = crop_mask.resize((nw, nh), Image.Resampling.LANCZOS)
        return scaled, scaled_mask

    def _commit_floating(self, layer: Layer) -> None:
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None:
            try:
                ca("Transform Selection")
            except Exception:
                pass
        self._reset_state()

    def _reset_state(self) -> None:
        self._lift_layer = None
        self._base = None
        self._floating = None
        self._float_mask = None
        self._bbox = None
        self._mode = None
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None

    def commit(self) -> Optional[str]:
        had = self._floating is not None
        self._reset_state()
        return "Transform Selection" if had else None

    def paint_overlay(self, painter, canvas) -> None:
        bb = self._bbox
        if bb is None:
            sel = self.ctx.get_selection() if self.ctx.get_selection else None
            if sel is None or getattr(sel, "bbox", None) is None:
                return
            bb = sel.bbox
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        x0, y0, x1, y1 = bb
        sx0, sy0 = canvas.canvas_to_screen(x0, y0)
        sx1, sy1 = canvas.canvas_to_screen(x1, y1)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        pen = QPen(QColor(0, 200, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 200, 255, 30))
        painter.drawRect(rect)
        painter.setBrush(QColor(255, 255, 255, 255))
        cx = rect.center().x()
        cy = rect.center().y()
        hs = self.HANDLE_SIZE
        for hx, hy in (
            (rect.left(), rect.top()), (cx, rect.top()), (rect.right(), rect.top()),
            (rect.left(), cy),                            (rect.right(), cy),
            (rect.left(), rect.bottom()), (cx, rect.bottom()), (rect.right(), rect.bottom()),
        ):
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)


TOOL_CLASS = SelectionTransformTool
