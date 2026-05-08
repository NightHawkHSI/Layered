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
ToolContext = _sh.ToolContext


class TransformTool(Tool):
    """Scale the active layer by dragging anchor handles on its bbox."""
    name = "Transform"
    commit_on = "release"

    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._mode: Optional[str] = None
        self._anchor: Optional[str] = None
        self._bbox0: Optional[tuple[int, int, int, int]] = None
        self._cropped: Optional[Image.Image] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._cur_bbox: Optional[tuple[int, int, int, int]] = None
        self._rotation_angle: float = 0.0
        self._rotation_angle_at_press: float = 0.0
        self._layer_at_press: Optional[Image.Image] = None
        self._offset_at_press: Optional[tuple[int, int]] = None
        self._layer_ref: Optional[Layer] = None

    def _layer_bbox(self, layer: Layer) -> Optional[tuple[int, int, int, int]]:
        ox, oy = layer.offset
        lw, lh = layer.image.size
        if lw <= 0 or lh <= 0:
            return None
        return (ox, oy, ox + lw, oy + lh)

    def _hit_handle(self, layer: Layer, x: int, y: int, hit_radius: int) -> Optional[str]:
        bb = self._cur_bbox or self._layer_bbox(layer)
        if bb is None:
            return None
        x0, y0, x1, y1 = bb
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        rot_canvas_offset = max(20, int(30 / zoom))
        rot_hx, rot_hy = cx, y0 - rot_canvas_offset
        if (x - rot_hx) ** 2 + (y - rot_hy) ** 2 <= hit_radius * hit_radius:
            return "rotate"
        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        best: Optional[tuple[str, int]] = None
        for name, (hx, hy) in handles.items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= hit_radius * hit_radius and (best is None or d < best[1]):
                best = (name, d)
        if best:
            return best[0]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        bb = self._cur_bbox or self._layer_bbox(layer)
        if bb is None:
            return
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        hit_radius = max(8, int(self.HANDLE_SIZE / zoom))
        h = self._hit_handle(layer, x, y, hit_radius)
        if h is None:
            return
        self._layer_at_press = layer.image.copy()
        self._offset_at_press = layer.offset
        self._layer_ref = layer
        self._anchor = h
        if h == "move":
            self._mode = "move"
        elif h == "rotate":
            self._mode = "rotate"
            self._rotation_angle_at_press = self._rotation_angle
        else:
            self._mode = f"scale-{h}"
        self._bbox0 = bb
        self._cur_bbox = bb
        self._press_pt = (x, y)
        ox, oy = layer.offset
        local = (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
        self._cropped = layer.image.crop(local).convert("RGBA")

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._mode is None or self._bbox0 is None or self._press_pt is None:
            return
        x0, y0, x1, y1 = self._bbox0
        px, py = self._press_pt
        dx, dy = x - px, y - py

        if self._mode == "rotate":
            import math
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            initial_angle = math.atan2(py - cy, px - cx)
            current_angle = math.atan2(y - cy, x - cx)
            delta = math.degrees(current_angle - initial_angle)
            angle = self._rotation_angle_at_press + delta
            if self.ctx.ctrl_held:
                angle = round(angle / 45.0) * 45.0
            self._rotation_angle = angle
            self._apply(layer, self._bbox0)
            return

        if self._mode == "move":
            new_bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
            self._apply(layer, new_bbox)
            return

        a = self._anchor or ""
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        if "w" in a: nx0 = x0 + dx
        if "e" in a: nx1 = x1 + dx
        if "n" in a: ny0 = y0 + dy
        if "s" in a: ny1 = y1 + dy
        nx0, nx1 = sorted((nx0, nx1))
        ny0, ny1 = sorted((ny0, ny1))

        if self.ctx.shift_held:
            ow = max(1, x1 - x0)
            oh = max(1, y1 - y0)
            nw = max(1, nx1 - nx0)
            nh = max(1, ny1 - ny0)
            scale = max(nw / ow, nh / oh)
            tw = max(1, int(round(ow * scale)))
            th = max(1, int(round(oh * scale)))
            if "e" in a or a == "n" or a == "s" or a == "move":
                ax = x0
            elif "w" in a:
                ax = x1
            else:
                ax = (x0 + x1) // 2
            if "s" in a or a == "w" or a == "e":
                ay = y0
            elif "n" in a:
                ay = y1
            else:
                ay = (y0 + y1) // 2
            if "e" in a:
                nx0, nx1 = ax, ax + tw
            elif "w" in a:
                nx0, nx1 = ax - tw, ax
            else:
                cx = (x0 + x1) // 2
                nx0, nx1 = cx - tw // 2, cx - tw // 2 + tw
            if "s" in a:
                ny0, ny1 = ay, ay + th
            elif "n" in a:
                ny0, ny1 = ay - th, ay
            else:
                cy = (y0 + y1) // 2
                ny0, ny1 = cy - th // 2, cy - th // 2 + th

        new_bbox = (nx0, ny0, nx1, ny1)
        self._apply(layer, new_bbox)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._mode is not None and self._cur_bbox is not None and self._cropped is not None:
            self._apply(layer, self._cur_bbox, final=True)
        self._mode = None
        self._anchor = None
        self._bbox0 = None
        self._cropped = None
        self._press_pt = None
        self._rotation_angle = 0.0
        self._rotation_angle_at_press = 0.0
        self._layer_at_press = None
        self._offset_at_press = None
        self._layer_ref = None
        super().release(layer, x, y)

    def commit(self) -> Optional[str]:
        self._mode = None
        self._anchor = None
        self._bbox0 = None
        self._cropped = None
        self._press_pt = None
        self._cur_bbox = None
        self._rotation_angle = 0.0
        self._rotation_angle_at_press = 0.0
        self._layer_at_press = None
        self._offset_at_press = None
        self._layer_ref = None
        return None

    def cancel(self) -> None:
        if (self._mode is not None
                and self._layer_at_press is not None
                and self._layer_ref is not None):
            self._layer_ref.image = self._layer_at_press
            self._layer_ref.offset = self._offset_at_press or (0, 0)
            self._cur_bbox = self._layer_bbox(self._layer_ref)
        self._mode = None
        self._anchor = None
        self._bbox0 = None
        self._cropped = None
        self._press_pt = None
        self._rotation_angle = 0.0
        self._rotation_angle_at_press = 0.0
        self._layer_at_press = None
        self._offset_at_press = None
        self._layer_ref = None

    def _apply(self, layer: Layer, new_bbox: tuple[int, int, int, int],
               *, final: bool = False) -> None:
        if self._cropped is None:
            return
        img: Image.Image = self._cropped
        nx0, ny0, nx1, ny1 = new_bbox
        rot_resample = Image.Resampling.BICUBIC if final else Image.Resampling.BILINEAR
        scale_resample = Image.Resampling.LANCZOS if final else Image.Resampling.BILINEAR
        if self._rotation_angle != 0.0:
            img = img.rotate(-self._rotation_angle, expand=True,
                             resample=rot_resample)
            if self._mode == "rotate":
                rw, rh = img.size
                cx = (nx0 + nx1) / 2.0
                cy = (ny0 + ny1) / 2.0
                nx0 = int(round(cx - rw / 2))
                ny0 = int(round(cy - rh / 2))
                nx1 = nx0 + rw
                ny1 = ny0 + rh
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        if (nw, nh) != img.size:
            img = img.resize((nw, nh), scale_resample)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        layer.image = img
        layer.offset = (nx0, ny0)
        self._cur_bbox = (nx0, ny0, nx1, ny1)

    def paint_overlay(self, painter, canvas) -> None:
        import math
        from PyQt6.QtCore import QLineF, QPointF
        from PyQt6.QtGui import QColor, QPen, QPolygonF
        layer = canvas.layer_stack.active
        if layer is None:
            return

        rotating = self._mode == "rotate" and self._bbox0 is not None
        if rotating:
            x0, y0, x1, y1 = self._bbox0
            angle = self._rotation_angle
        else:
            bb = self._cur_bbox or self._layer_bbox(layer)
            if bb is None:
                return
            x0, y0, x1, y1 = bb
            angle = 0.0

        cx_c = (x0 + x1) / 2.0
        cy_c = (y0 + y1) / 2.0
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        def rot(px: float, py: float) -> tuple[float, float]:
            dx, dy = px - cx_c, py - cy_c
            return cx_c + cos_a * dx - sin_a * dy, cy_c + sin_a * dx + cos_a * dy

        def to_screen(px: float, py: float) -> QPointF:
            sx, sy = canvas.canvas_to_screen(px, py)
            return QPointF(sx, sy)

        corners = [rot(*p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        poly = QPolygonF([to_screen(px, py) for px, py in corners])

        pen = QPen(QColor(0, 200, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 200, 255, 40))
        painter.drawPolygon(poly)

        painter.setBrush(QColor(255, 255, 255, 255))
        hs = self.HANDLE_SIZE
        handles_local = (
            (x0, y0), (cx_c, y0), (x1, y0),
            (x0, cy_c),            (x1, cy_c),
            (x0, y1), (cx_c, y1), (x1, y1),
        )
        for px, py in handles_local:
            rx, ry = rot(px, py)
            sx, sy = canvas.canvas_to_screen(rx, ry)
            painter.drawRect(int(sx - hs / 2), int(sy - hs / 2), hs, hs)

        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        rot_canvas_offset = max(20, int(30 / zoom))
        rot_local = (cx_c, y0 - rot_canvas_offset)
        rot_pt = rot(*rot_local)
        top_mid = rot(cx_c, y0)
        rot_sp = to_screen(*rot_pt)
        top_sp = to_screen(*top_mid)
        rot_pen = QPen(QColor(255, 220, 0, 220), 1)
        rot_pen.setCosmetic(True)
        painter.setPen(rot_pen)
        painter.setBrush(QColor(255, 220, 0, 200))
        rot_r = hs
        painter.drawEllipse(int(rot_sp.x() - rot_r), int(rot_sp.y() - rot_r),
                            rot_r * 2, rot_r * 2)
        painter.drawLine(QLineF(top_sp, rot_sp))


TOOL_CLASS = TransformTool
