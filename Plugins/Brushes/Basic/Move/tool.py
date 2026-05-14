"""Move tool.

Click-drag to move/resize the active selection or the whole layer.

Bbox + 8 handles render whenever a layer is active:
  * With a selection → bbox is the selection's bbox; resize scales the
    selected pixels + mask. Drag inside translates the floating pixels.
  * Without a selection → bbox is the layer's image bounds; resize
    rescales the entire layer.image (Pillow LANCZOS) and updates
    layer.offset. Drag inside translates layer.offset (non-destructive).

Shift constrains translate to one axis or scale to preserve aspect.
Esc cancels and restores the original state.
"""
import importlib.util as _iu, sys as _sys
from pathlib import Path as _P

# -------------------------------------------------------------------------
# Shared imports loader
# -------------------------------------------------------------------------

_SHARED_KEY = "_layered_brushes_shared"

if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)

_sh = _sys.modules[_SHARED_KEY]

_SelectionToolBase = _sh._SelectionToolBase
Image              = _sh.Image
ImageChops         = _sh.ImageChops
QWidget            = _sh.QWidget
QHBoxLayout        = _sh.QHBoxLayout
QLabel             = _sh.QLabel
QCheckBox          = _sh.QCheckBox
Qt                 = _sh.Qt
QColor             = _sh.QColor
QPen               = _sh.QPen


def _resampling():
    """Pillow resampling enum, compatible with both 9.x and 10.x."""
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


_LANCZOS = _resampling()


# -------------------------------------------------------------------------
# Move Tool
# -------------------------------------------------------------------------

class MoveTool(_SelectionToolBase):
    name      = "Move"
    tool_id   = "move"
    icon      = "✥"
    shortcut  = "V"
    role      = "move"
    group     = "Basic"
    commit_on = "release"

    HANDLE_SIZE = 10  # screen pixels

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.auto_select = False  # if True, click an opaque pixel to pick its layer (host hook)

        # Whole-layer translate state.
        self._layer_move_active = False
        self._layer_anchor: tuple[int, int] | None = None
        self._layer_origin: tuple[int, int] | None = None
        self._layer_ref = None

        # Transform (resize) state — used for both selection and whole-layer modes.
        self._tx_active = False
        self._tx_mode: str | None = None  # "selection" | "layer"
        self._tx_handle: str | None = None
        self._tx_bbox0: tuple[int, int, int, int] | None = None  # canvas-space (x0,y0,x1,y1) inclusive-exclusive
        self._tx_anchor: tuple[int, int] | None = None
        self._tx_layer = None
        # selection-mode buffers
        self._tx_orig_mask = None
        self._tx_orig_lifted = None
        self._tx_base = None
        # layer-mode buffers
        self._tx_orig_image = None        # PIL Image snapshot
        self._tx_orig_offset: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self, parent, ctx):
        w = QWidget(parent)
        w.setFixedHeight(28)
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        row.addWidget(QLabel("Move:"))

        cb = QCheckBox("Auto-select layer")
        cb.setChecked(self.auto_select)
        cb.toggled.connect(lambda v: setattr(self, "auto_select", bool(v)))
        cb.setToolTip("Pick the topmost opaque layer under the cursor before moving.")
        row.addWidget(cb)

        row.addStretch(1)
        return w

    # ------------------------------------------------------------------
    # Selection inspection
    # ------------------------------------------------------------------

    def _current_selection(self):
        getter = getattr(self.ctx, "get_selection", None)
        if not callable(getter):
            return None
        return getter()

    def _selection_bbox_canvas(self):
        """Return (x0, y0, x1, y1) of the active selection in canvas coords,
        or None if no selection. x1/y1 are exclusive (PIL convention)."""
        sel = self._current_selection()
        if sel is None:
            return None
        mask = getattr(sel, "mask", None)
        if mask is None:
            return None
        bb = mask.getbbox()
        return bb

    def _layer_bbox_canvas(self, layer):
        """Layer image bounds in canvas coords."""
        if layer is None or getattr(layer, "image", None) is None:
            return None
        ox, oy = layer.offset
        return (ox, oy, ox + layer.image.width, oy + layer.image.height)

    def _move_bbox(self, layer):
        """Active bbox + mode. Selection wins over layer bounds."""
        bb = self._selection_bbox_canvas()
        if bb is not None:
            return bb, "selection"
        bb = self._layer_bbox_canvas(layer)
        if bb is not None:
            return bb, "layer"
        return None, None

    def _handle_positions(self, bbox):
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        return {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                 "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }

    def _hit_handle(self, layer, x: float, y: float) -> str | None:
        bbox, _ = self._move_bbox(layer)
        if bbox is None:
            return None
        zoom = max(0.01, float(getattr(self.ctx, "canvas_zoom", 1.0)))
        r = (self.HANDLE_SIZE / zoom) * 0.75
        best, best_d = None, float("inf")
        for name, (hx, hy) in self._handle_positions(bbox).items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= r * r and d < best_d:
                best, best_d = name, d
        return best

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def press(self, layer, x, y):
        if self.auto_select:
            self._try_auto_select(x, y)
            layer = getattr(self.ctx, "active_layer", layer) or layer

        # 1) Handle hit → resize-transform mode (selection or whole layer).
        h = self._hit_handle(layer, x, y)
        if h is not None:
            self._begin_transform(layer, x, y, h)
            return

        # 2) Inside selection (no modifier) → drag-move floating pixels.
        if self._begin_move_if_inside(layer, x, y):
            return

        # 3) No selection / outside → translate the whole layer.
        self._layer_move_active = True
        self._layer_anchor      = (x, y)
        self._layer_origin      = tuple(layer.offset)
        self._layer_ref         = layer

    def move(self, layer, x, y):
        if self._tx_active:
            self._update_transform(x, y)
            return
        if self._move_mode:
            self._continue_move(x, y)
            return
        if self._layer_move_active and self._layer_ref is not None:
            ax, ay = self._layer_anchor
            ox, oy = self._layer_origin
            dx, dy = x - ax, y - ay
            if self.ctx.shift_held:
                if abs(dx) >= abs(dy):
                    dy = 0
                else:
                    dx = 0
            self._layer_ref.offset = (ox + dx, oy + dy)

    def release(self, layer, x, y):
        if self._tx_active:
            self._update_transform(x, y)
            self._commit_transform()
            return
        if self._move_mode:
            self._end_move()
            return
        if self._layer_move_active:
            moved = self._layer_ref is not None and \
                    tuple(self._layer_ref.offset) != self._layer_origin
            self._layer_move_active = False
            self._layer_anchor      = None
            self._layer_origin      = None
            self._layer_ref         = None
            if moved:
                ca = getattr(self.ctx, "commit_action", None)
                if callable(ca):
                    ca("Move Layer")

    def cancel(self):
        if self._tx_active:
            self._abort_transform()
            return
        if self._move_mode:
            self.cancel_move()
            return
        if self._layer_move_active and self._layer_ref is not None:
            self._layer_ref.offset = self._layer_origin
            self._layer_move_active = False
            self._layer_anchor      = None
            self._layer_origin      = None
            self._layer_ref         = None

    # ------------------------------------------------------------------
    # Transform — lift, resize, commit
    # ------------------------------------------------------------------

    def _begin_transform(self, layer, x: int, y: int, handle: str) -> None:
        bbox, mode = self._move_bbox(layer)
        if bbox is None or mode is None:
            return

        self._tx_active = True
        self._tx_mode   = mode
        self._tx_handle = handle
        self._tx_bbox0  = bbox
        self._tx_anchor = (x, y)
        self._tx_layer  = layer

        if mode == "selection":
            sel = self._current_selection()
            ox, oy = layer.offset
            layer_mask = Image.new("L", layer.image.size, 0)
            layer_mask.paste(sel.mask, (-ox, -oy))

            src = layer.image.convert("RGBA")
            r, g, b, a = src.split()
            lift_a = ImageChops.multiply(a, layer_mask)
            if lift_a.getextrema()[1] == 0:
                self._reset_transform()
                return
            base_a = ImageChops.multiply(a, ImageChops.invert(layer_mask))

            self._tx_orig_mask   = sel.mask.copy()
            self._tx_orig_lifted = Image.merge("RGBA", (r, g, b, lift_a))
            self._tx_base        = Image.merge("RGBA", (r, g, b, base_a))
            # Show the "hole" beneath the lifted pixels until the gesture ends.
            layer.image = self._tx_base.copy()
        else:
            # Whole-layer mode: snapshot image + offset for restore.
            self._tx_orig_image  = layer.image.copy()
            self._tx_orig_offset = tuple(layer.offset)

    def _update_transform(self, x: int, y: int) -> None:
        if not self._tx_active or self._tx_layer is None:
            return
        ax, ay = self._tx_anchor
        bx0, by0, bx1, by1 = self._tx_bbox0
        nbx0, nby0, nbx1, nby1 = bx0, by0, bx1, by1

        h = self._tx_handle
        dx, dy = x - ax, y - ay

        if "w" in h: nbx0 = bx0 + dx
        if "e" in h: nbx1 = bx1 + dx
        if "n" in h: nby0 = by0 + dy
        if "s" in h: nby1 = by1 + dy

        # Shift = preserve aspect ratio (anchor on opposite corner/edge).
        if self.ctx.shift_held:
            orig_w = max(1, bx1 - bx0)
            orig_h = max(1, by1 - by0)
            new_w  = abs(nbx1 - nbx0) or 1
            new_h  = abs(nby1 - nby0) or 1
            scale  = max(new_w / orig_w, new_h / orig_h)
            if "e" in h:
                nbx1 = nbx0 + orig_w * scale
            elif "w" in h:
                nbx0 = nbx1 - orig_w * scale
            if "s" in h:
                nby1 = nby0 + orig_h * scale
            elif "n" in h:
                nby0 = nby1 - orig_h * scale

        # Clamp to a sane minimum (no flip, no zero-size).
        if nbx1 - nbx0 < 1: nbx1 = nbx0 + 1
        if nby1 - nby0 < 1: nby1 = nby0 + 1

        new_w = int(round(nbx1 - nbx0))
        new_h = int(round(nby1 - nby0))
        if new_w < 1 or new_h < 1:
            return

        if self._tx_mode == "selection":
            self._update_selection_transform(nbx0, nby0, new_w, new_h)
        else:
            self._update_layer_transform(nbx0, nby0, new_w, new_h)

    def _update_selection_transform(self, nbx0, nby0, new_w, new_h):
        bx0i, by0i, bx1i, by1i = self._tx_bbox0
        sub_mask = self._tx_orig_mask.crop((bx0i, by0i, bx1i, by1i))
        ox, oy = self._tx_layer.offset
        sub_lifted = self._tx_orig_lifted.crop(
            (bx0i - ox, by0i - oy, bx1i - ox, by1i - oy)
        )

        new_mask   = sub_mask.resize((new_w, new_h), _LANCZOS)
        new_lifted = sub_lifted.resize((new_w, new_h), _LANCZOS)

        canvas = self._tx_base.copy()
        dest_x = int(round(nbx0)) - ox
        dest_y = int(round(nby0)) - oy
        canvas.alpha_composite(new_lifted, dest=(dest_x, dest_y))
        self._tx_layer.image = canvas

        cw, ch = self._canvas_size(self._tx_layer)
        full_mask = Image.new("L", (cw, ch), 0)
        full_mask.paste(new_mask, (int(round(nbx0)), int(round(nby0))))
        self._set_selection_mask(full_mask)

    def _update_layer_transform(self, nbx0, nby0, new_w, new_h):
        if self._tx_orig_image is None:
            return
        if (new_w, new_h) == self._tx_orig_image.size:
            self._tx_layer.image = self._tx_orig_image.copy()
        else:
            self._tx_layer.image = self._tx_orig_image.resize((new_w, new_h), _LANCZOS)
        self._tx_layer.offset = (int(round(nbx0)), int(round(nby0)))

    def _commit_transform(self) -> None:
        label = "Transform Selection" if self._tx_mode == "selection" else "Resize Layer"
        ca = getattr(self.ctx, "commit_action", None)
        if callable(ca):
            try:
                ca(label)
            except Exception:
                pass
        self._reset_transform()

    def _abort_transform(self) -> None:
        if self._tx_mode == "selection" and self._tx_layer is not None \
                and self._tx_base is not None and self._tx_orig_lifted is not None:
            restored = self._tx_base.copy()
            restored.alpha_composite(self._tx_orig_lifted)
            self._tx_layer.image = restored
            if self._tx_orig_mask is not None:
                self._set_selection_mask(self._tx_orig_mask)
        elif self._tx_mode == "layer" and self._tx_layer is not None \
                and self._tx_orig_image is not None:
            self._tx_layer.image = self._tx_orig_image
            if self._tx_orig_offset is not None:
                self._tx_layer.offset = self._tx_orig_offset
        self._reset_transform()

    def _reset_transform(self) -> None:
        self._tx_active      = False
        self._tx_mode        = None
        self._tx_handle      = None
        self._tx_bbox0       = None
        self._tx_anchor      = None
        self._tx_layer       = None
        self._tx_orig_mask   = None
        self._tx_orig_lifted = None
        self._tx_base        = None
        self._tx_orig_image  = None
        self._tx_orig_offset = None

    def _set_selection_mask(self, mask) -> None:
        from app.core.project import Selection
        bb = mask.getbbox()
        setter = getattr(self.ctx, "set_selection", None)
        if callable(setter):
            setter(Selection(bbox=bb, mask=mask) if bb else None)

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------

    def paint_overlay(self, painter, canvas) -> None:
        # Active bbox: prefer selection, fall back to current layer bounds.
        layer = None
        stack = getattr(canvas, "layer_stack", None)
        if stack is not None:
            layer = getattr(stack, "active", None)
        bbox, mode = self._move_bbox(layer)
        if bbox is None:
            return
        x0, y0, x1, y1 = bbox

        # Layer-mode uses a softer amber so it's visually distinct from the
        # cyan selection overlay.
        line_c    = QColor(0, 200, 255) if mode == "selection" else QColor(255, 170, 60)
        line_dash = QColor(0, 200, 255, 220) if mode == "selection" else QColor(255, 170, 60, 220)

        sx0, sy0 = canvas.canvas_to_screen(x0, y0)
        sx1, sy1 = canvas.canvas_to_screen(x1, y1)
        painter.setPen(QPen(line_dash, 1.5, Qt.PenStyle.DashLine))
        painter.drawRect(int(sx0), int(sy0), int(sx1 - sx0), int(sy1 - sy0))

        painter.setPen(QPen(line_c, 1.5))
        painter.setBrush(QColor(255, 255, 255))
        hs = self.HANDLE_SIZE
        for _, (hx, hy) in self._handle_positions(bbox).items():
            shx, shy = canvas.canvas_to_screen(hx, hy)
            painter.drawRect(int(shx - hs / 2), int(shy - hs / 2), hs, hs)

    # ------------------------------------------------------------------
    # Auto-select (best-effort; host may or may not provide the hook)
    # ------------------------------------------------------------------

    def _try_auto_select(self, x: int, y: int) -> None:
        hooks = getattr(self.ctx, "hooks", None)
        if isinstance(hooks, dict):
            hook = hooks.get("pick_layer_at")
            if callable(hook):
                try:
                    hook(x, y)
                except Exception:
                    pass


# -------------------------------------------------------------------------
# Required export
# -------------------------------------------------------------------------

TOOL_CLASS = MoveTool
