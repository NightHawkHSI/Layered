"""Lasso — freehand selection tool.

Draw any shape by holding and dragging. On release the enclosed area
is filled into the project selection mask.  Hardness controls edge
feathering (1.0 = hard pixel-perfect edge, lower = gaussian blur).
Add / Subtract / Clear work as expected.
"""

import importlib.util as _iu, sys as _sys
from pathlib import Path as _P

_SHARED_KEY = "_layered_brushes_shared"
if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod  = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)
_sh = _sys.modules[_SHARED_KEY]

_SelectionToolBase      = _sh._SelectionToolBase
build_brush_settings_ui = _sh.build_brush_settings_ui
Image                   = _sh.Image
ImageChops              = _sh.ImageChops

QWidget      = _sh.QWidget
QLabel       = _sh.QLabel
QHBoxLayout  = _sh.QHBoxLayout
QPushButton  = _sh.QPushButton
SliderField  = _sh.SliderField

try:
    from PyQt6.QtCore import Qt, QRect, QPoint
    from PyQt6.QtGui  import QPen, QColor, QImage, QPainterPath
    _FMT_RGBA = QImage.Format.Format_RGBA8888
    _NoBrush  = Qt.BrushStyle.NoBrush
    _DashLine = Qt.PenStyle.DashLine
except ImportError:
    from PyQt5.QtCore import Qt, QRect, QPoint
    from PyQt5.QtGui  import QPen, QColor, QImage, QPainterPath
    _FMT_RGBA = QImage.Format_RGBA8888
    _NoBrush  = Qt.NoBrush
    _DashLine = Qt.DashLine

try:
    from PIL import ImageDraw, ImageFilter
except ImportError:
    ImageDraw = ImageFilter = None


# ---------------------------------------------------------------------------
# PIL helpers
# ---------------------------------------------------------------------------

def _fill_lasso(working, pts, hardness, erase):
    """Fill/erase the polygon *pts* (canvas-space) in *working* (L image).

    hardness 1.0 → sharp edge.
    hardness < 1 → gaussian feather scaled to bounding-box size.
    """
    if len(pts) < 3 or ImageDraw is None:
        return

    flat = [c for pt in pts for c in pt]

    # Build a temporary mask of just this polygon
    tmp = Image.new("L", working.size, 0)
    ImageDraw.Draw(tmp).polygon(flat, fill=255)

    # Feather if needed
    if hardness < 0.999:
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        span   = max(1, max(max(xs)-min(xs), max(ys)-min(ys)))
        radius = max(1, int((1.0 - hardness) * span * 0.05))
        tmp = tmp.filter(ImageFilter.GaussianBlur(radius))

    if erase:
        # Subtract: multiply working by the inverse of the polygon mask
        inv    = tmp.point(lambda v: 255 - v)
        result = ImageChops.multiply(working, inv)
        working.paste(result)
    else:
        # Add: union — take the lighter (max) of existing and new
        result = ImageChops.lighter(working, tmp)
        working.paste(result)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class LassoTool(_SelectionToolBase):
    name      = "Lasso"
    tool_id   = "lasso"
    icon      = "🪢"
    shortcut  = "L"
    group     = "Basic"
    commit_on = "release"

    # Defaults — written by the hardness slider
    brush_hardness = 1.0

    # Selection mode constants
    _MODE_NEW      = "new"
    _MODE_ADD      = "add"
    _MODE_SUBTRACT = "subtract"

    # Anchor hit-radius in screen pixels (scaled by zoom for canvas-space test)
    _ANCHOR_HIT_PX = 8

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self._sel_mode   = self._MODE_NEW   # default: each stroke replaces
        self._erase_mode = False            # derived from _sel_mode for _fill_lasso
        self._drawing    = False
        self._working    = None
        self._dirty      = False

        # Path recorded during a stroke
        self._cpts = []   # canvas-space  [(cx, cy), ...]

        # Anchor editing — committed polygon kept around so the user can
        # tweak vertices or drag the whole selection after release.
        self._anchors        = []      # canvas-space vertices of last stroke
        self._anchors_base   = None    # mask snapshot taken just before _fill_lasso
        self._anchors_erase  = False   # erase flag used when last stroke filled
        self._anchor_drag    = None    # index of vertex currently being dragged
        self._move_start     = None    # press point when selection-move started

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_ui(self, parent, ctx):
        root   = QWidget(parent)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._new_btn   = QPushButton("⬜ New")
        self._add_btn   = QPushButton("➕ Add")
        self._sub_btn   = QPushButton("➖ Subtract")
        self._clear_btn = QPushButton("✖ Clear")
        for b in (self._new_btn, self._add_btn, self._sub_btn, self._clear_btn):
            b.setFixedHeight(24)
            layout.addWidget(b)

        self._new_btn.clicked.connect(lambda: self._set_mode(self._MODE_NEW))
        self._add_btn.clicked.connect(lambda: self._set_mode(self._MODE_ADD))
        self._sub_btn.clicked.connect(lambda: self._set_mode(self._MODE_SUBTRACT))
        self._clear_btn.clicked.connect(self._clear_now)

        layout.addWidget(QLabel("Feather"))
        sf = SliderField(0, 100, int(self.brush_hardness * 100), suffix="%")
        sf.setMinimumWidth(120)
        sf.valueChanged.connect(
            lambda v: setattr(self, "brush_hardness", v / 100.0)
        )
        layout.addWidget(sf, 1)
        layout.addStretch(0)

        self._refresh_buttons()
        return root

    def _set_mode(self, mode):
        self._sel_mode   = mode
        self._erase_mode = (mode == self._MODE_SUBTRACT)
        self._refresh_buttons()

    def _refresh_buttons(self):
        if not hasattr(self, "_new_btn"):
            return
        styles = {
            self._MODE_NEW:      ("background:#557; color:#fff; font-weight:bold;", "", ""),
            self._MODE_ADD:      ("", "background:#4a9; color:#fff; font-weight:bold;", ""),
            self._MODE_SUBTRACT: ("", "", "background:#c55; color:#fff; font-weight:bold;"),
        }
        ns, as_, ss = styles.get(self._sel_mode, ("", "", ""))
        self._new_btn.setStyleSheet(ns)
        self._add_btn.setStyleSheet(as_)
        self._sub_btn.setStyleSheet(ss)

    def _clear_now(self):
        self._clear_selection()
        self._anchors      = []
        self._anchors_base = None
        ca = getattr(self.ctx, "commit_action", None)
        if callable(ca):
            ca("Clear Selection")

    # ------------------------------------------------------------------
    # Anchor helpers
    # ------------------------------------------------------------------
    _ANCHOR_MAX_VIS = 24   # cap visible/draggable anchor dots

    def _anchor_indices(self):
        n = len(self._anchors)
        if n == 0:
            return []
        if n <= self._ANCHOR_MAX_VIS:
            return list(range(n))
        step = n / self._ANCHOR_MAX_VIS
        return [min(n - 1, int(i * step)) for i in range(self._ANCHOR_MAX_VIS)]

    def _hit_anchor(self, cx, cy):
        if not self._anchors:
            return None
        zoom = getattr(self.ctx, "_canvas_zoom", 1.0) or 1.0
        r = max(self._ANCHOR_HIT_PX / zoom, 3.0)
        r2 = r * r
        best_i = None
        best_d = r2
        for i in self._anchor_indices():
            ax, ay = self._anchors[i]
            dx = ax - cx; dy = ay - cy
            d  = dx * dx + dy * dy
            if d <= best_d:
                best_d = d
                best_i = i
        return best_i

    def _rebuild_from_anchors(self):
        if len(self._anchors) < 3 or self._anchors_base is None:
            return
        self._working = self._anchors_base.copy()
        _fill_lasso(self._working, self._anchors,
                    self.brush_hardness, self._anchors_erase)
        self._push_live()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _to_canvas(self, layer, x, y):
        ox, oy = layer.offset
        return x + ox, y + oy

    def _ensure_working(self, layer):
        if self._working is not None:
            return
        if self._sel_mode == self._MODE_NEW:
            # Replace mode: always start from a blank slate so the new
            # stroke replaces whatever was selected before.
            self._working = Image.new("L", self._canvas_size(layer), 0)
        else:
            # Add / Subtract: build on top of the existing selection.
            existing = self._current_mask_canvas(layer)
            self._working = (existing.copy() if existing is not None
                             else Image.new("L", self._canvas_size(layer), 0))

    def _push_live(self):
        if self._working is not None:
            self._commit_mask(self._working)

    def _append_canvas(self, cx, cy):
        """Append a canvas point, skipping sub-2px moves to save memory."""
        if self._cpts:
            lx, ly = self._cpts[-1]
            if abs(cx - lx) < 2 and abs(cy - ly) < 2:
                return
        self._cpts.append((cx, cy))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def press(self, layer, x, y):
        # Drop stale anchors if the selection was cleared externally.
        if (callable(getattr(self.ctx, "get_selection", None))
                and self.ctx.get_selection() is None):
            self._anchors      = []
            self._anchors_base = None

        cx, cy = self._to_canvas(layer, x, y)

        # 1) Vertex hit-test — drag an existing anchor (overrides mode).
        idx = self._hit_anchor(cx, cy)
        if idx is not None and not (self.ctx.shift_held or self.ctx.alt_held):
            self._anchor_drag = idx
            self._drawing     = False
            self._working     = None
            self._dirty       = False
            self._cpts        = []
            return

        # 2) Click inside the current selection — move it.
        if self._begin_move_if_inside(layer, x, y):
            self._move_start = (x, y)
            self._drawing    = False
            return

        # 3) New freehand stroke.
        self._working = None
        self._dirty   = False
        self._drawing = True
        self._cpts    = []
        self._ensure_working(layer)
        self._append_canvas(cx, cy)

    def move(self, layer, x, y):
        if self._anchor_drag is not None:
            cx, cy = self._to_canvas(layer, x, y)
            self._anchors[self._anchor_drag] = (cx, cy)
            self._rebuild_from_anchors()
            return
        if self._move_mode:
            self._continue_move(x, y)
            return
        if self._drawing:
            cx, cy = self._to_canvas(layer, x, y)
            self._append_canvas(cx, cy)

    def release(self, layer, x, y):
        # --- anchor edit commit ------------------------------------------
        if self._anchor_drag is not None:
            cx, cy = self._to_canvas(layer, x, y)
            self._anchors[self._anchor_drag] = (cx, cy)
            self._rebuild_from_anchors()
            if self._working is not None:
                self._commit_mask(self._working)
                ca = getattr(self.ctx, "commit_action", None)
                if callable(ca):
                    ca(f"{self.name}: edit anchor")
            self._anchor_drag = None
            self._working     = None
            return

        # --- selection-move commit ---------------------------------------
        if self._move_mode:
            sx, sy = self._move_start or (x, y)
            dx, dy = x - sx, y - sy
            self._end_move()              # base class commits if dirty
            if (dx or dy) and self._anchors:
                self._anchors = [(ax + dx, ay + dy) for ax, ay in self._anchors]
                if self._anchors_base is not None:
                    shifted = Image.new("L", self._anchors_base.size, 0)
                    shifted.paste(self._anchors_base, (dx, dy))
                    self._anchors_base = shifted
            self._move_start = None
            return

        # --- normal freehand stroke --------------------------------------
        if not self._drawing:
            return
        self.move(layer, x, y)   # capture final point
        self._drawing = False

        if len(self._cpts) >= 3 and self._working is not None:
            base_before = self._working.copy()
            _fill_lasso(self._working, self._cpts,
                        self.brush_hardness, self._erase_mode)
            self._dirty = True
            self._push_live()

            self._anchors       = list(self._cpts)
            self._anchors_base  = base_before
            self._anchors_erase = self._erase_mode

        if self._dirty and self._working is not None:
            self._commit_mask(self._working)
            ca = getattr(self.ctx, "commit_action", None)
            if callable(ca):
                ca(self.name)

        self._working = None
        self._dirty   = False
        self._cpts    = []

    def cancel(self):
        self._drawing     = False
        self._working     = None
        self._dirty       = False
        self._cpts        = []
        self._anchor_drag = None
        self._move_start  = None
        self.cancel_move()

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------
    def paint_overlay(self, painter, canvas):
        self._draw_tint(painter, canvas)
        if self._drawing and len(self._cpts) >= 2:
            spts = [canvas.canvas_to_screen(cx, cy) for cx, cy in self._cpts]
            self._draw_live_fill(painter, spts)
            self._draw_lasso_path(painter, spts)
        elif self._anchors and not self._move_mode:
            sel_ok = (
                not callable(getattr(self.ctx, "get_selection", None))
                or self.ctx.get_selection() is not None
            )
            if sel_ok:
                idxs = self._anchor_indices()
                spts = [canvas.canvas_to_screen(*self._anchors[i]) for i in idxs]
                if self._anchor_drag is not None:
                    full = [canvas.canvas_to_screen(cx, cy) for cx, cy in self._anchors]
                    self._draw_lasso_path(painter, full)
                hi = idxs.index(self._anchor_drag) if self._anchor_drag in idxs else None
                self._draw_anchors(painter, spts, highlight=hi)
        self._draw_cursor(painter)

    # ---- anchor dots ---------------------------------------------------
    def _draw_anchors(self, painter, pts, highlight=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        for i, (x, y) in enumerate(pts):
            if i == highlight:
                painter.setPen(QPen(QColor(0, 0, 0, 220), 1))
                painter.setBrush(QColor(255, 200, 0, 240))
                r = 5
            else:
                painter.setPen(QPen(QColor(0, 0, 0, 220), 1))
                painter.setBrush(QColor(255, 255, 255, 230))
                r = 3
            painter.drawEllipse(int(x) - r, int(y) - r, r * 2, r * 2)

    # ---- committed selection tint (blue wash over the saved mask) ------
    def _draw_tint(self, painter, canvas):
        ctx = self.ctx
        if ctx is None:
            return
        sel = getattr(ctx, "selection_mask", None)
        if sel is None:
            return
        np    = _sh.np
        alpha = np.array(sel, dtype=np.uint8)
        if alpha.max() == 0:
            return
        H, W  = alpha.shape
        rgba  = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[..., 0] = 30
        rgba[..., 1] = 144
        rgba[..., 2] = 255
        rgba[..., 3] = (alpha.astype(np.uint16) * 115 // 255).astype(np.uint8)
        qimg  = QImage(rgba.tobytes(), W, H, W * 4, _FMT_RGBA)
        painter.setOpacity(1.0)
        painter.drawImage(QRect(0, 0, canvas.width(), canvas.height()), qimg)

    # ---- live fill — translucent polygon rendered in screen-space ------
    def _draw_live_fill(self, painter, pts):
        if len(pts) < 3:
            return

        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        path.closeSubpath()

        painter.save()
        # Erase mode → red tint; add mode → blue tint
        if self._erase_mode:
            fill = QColor(220, 60,  60,  70)
            edge = QColor(220, 60,  60, 140)
        else:
            fill = QColor(30,  144, 255, 70)
            edge = QColor(30,  144, 255, 140)

        painter.setPen(QPen(edge, 1))
        painter.setBrush(fill)
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.drawPath(path)
        painter.restore()

    # ---- lasso outline + decorations -----------------------------------
    def _draw_lasso_path(self, painter, pts):
        qpts = [QPoint(int(x), int(y)) for x, y in pts]

        painter.setBrush(_NoBrush)
        painter.setRenderHint(painter.RenderHint.Antialiasing, False)

        # Drawn path — double-pen for contrast on any background
        for pen in (
            QPen(QColor(0,   0,   0,   160), 3, _DashLine),
            QPen(QColor(255, 255, 255, 230), 1, _DashLine),
        ):
            painter.setPen(pen)
            for i in range(len(qpts) - 1):
                painter.drawLine(qpts[i], qpts[i + 1])

        # Closing segment — lighter, signals "not drawn yet"
        for pen in (
            QPen(QColor(0,   0,   0,   70),  2, _DashLine),
            QPen(QColor(120, 200, 255, 160), 1, _DashLine),
        ):
            painter.setPen(pen)
            painter.drawLine(qpts[-1], qpts[0])

        # Origin dot — aim here to close the shape
        r = 6
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.setBrush(QColor(30, 144, 255, 220))
        painter.drawEllipse(qpts[0].x() - r, qpts[0].y() - r, r * 2, r * 2)

        # Cursor dot — current pen tip
        cx, cy = pts[-1]
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        painter.setBrush(QColor(255, 255, 255, 180))
        painter.drawEllipse(int(cx) - 3, int(cy) - 3, 6, 6)

    # ---- simple crosshair cursor when idle ----------------------------
    def _draw_cursor(self, painter):
        pos = getattr(self, "_cursor_pos", None)
        if pos is None or self._drawing:
            return
        x, y = pos
        arm  = 8
        gap  = 3

        painter.setBrush(_NoBrush)
        for pen in (
            QPen(QColor(0,   0,   0,   160), 3),
            QPen(QColor(255, 255, 255, 230), 1),
        ):
            painter.setPen(pen)
            # horizontal arms
            painter.drawLine(x - arm, y, x - gap, y)
            painter.drawLine(x + gap, y, x + arm, y)
            # vertical arms
            painter.drawLine(x, y - arm, x, y - gap)
            painter.drawLine(x, y + gap, x, y + arm)

TOOL_CLASS = LassoTool