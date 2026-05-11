"""Magic Wand selection tool.

Click a pixel — selects all matching pixels within tolerance. Supports
Shift (add to selection) / Alt (subtract). Click inside an existing
selection (no modifier) to drag-move the lifted pixels.

Modes:
    Contiguous : 4-connected flood fill from click point.
    Global     : selects every pixel in the layer matching the seed.
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

Tool                    = _sh.Tool
_SelectionToolBase      = _sh._SelectionToolBase
build_brush_settings_ui = _sh.build_brush_settings_ui
Image                   = _sh.Image
deque                   = _sh.deque
QWidget                 = _sh.QWidget
QHBoxLayout             = _sh.QHBoxLayout
QLabel                  = _sh.QLabel
QCheckBox               = _sh.QCheckBox
SliderField             = _sh.SliderField
np                      = _sh.np  # numpy is required for the wand


# -------------------------------------------------------------------------
# Magic Wand
# -------------------------------------------------------------------------

class MagicWandTool(_SelectionToolBase):
    name      = "Magic Wand"
    tool_id   = "magic_wand"
    icon      = "⁂"
    shortcut  = "W"
    group     = "Basic"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.tolerance  = 32     # 0-255 Manhattan-distance threshold
        self.contiguous = True
        self.sample_alpha = True  # also compare alpha channel

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self, parent, ctx):
        w = QWidget(parent)
        w.setFixedHeight(28)
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        row.addWidget(QLabel("Tolerance"))
        sf = SliderField(0, 255, int(self.tolerance))
        sf.setMinimumWidth(140)
        sf.valueChanged.connect(lambda v: setattr(self, "tolerance", int(v)))
        row.addWidget(sf, 1)

        cb_c = QCheckBox("Contiguous")
        cb_c.setChecked(self.contiguous)
        cb_c.toggled.connect(lambda v: setattr(self, "contiguous", bool(v)))
        row.addWidget(cb_c)

        cb_a = QCheckBox("Sample Alpha")
        cb_a.setChecked(self.sample_alpha)
        cb_a.toggled.connect(lambda v: setattr(self, "sample_alpha", bool(v)))
        row.addWidget(cb_a)

        row.addStretch(1)
        return w

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def press(self, layer, x, y):
        # Click inside the current selection (no modifier) starts a move.
        if self._begin_move_if_inside(layer, x, y):
            return

        img = layer.image
        if not (0 <= x < img.width and 0 <= y < img.height):
            return

        mask = self._generate_wand_mask(img, x, y)
        if mask is None:
            return

        # Place the layer-space mask onto a canvas-space mask the same size
        # as the active selection coordinate space (matches what
        # _combine_with_current expects).
        canvas_mask = self._layer_to_canvas_mask(layer, mask)
        combined = self._combine_with_current(canvas_mask, layer)
        self._commit_mask(combined)

    def move(self, layer, x, y):
        if self._move_mode:
            self._continue_move(x, y)

    def release(self, layer, x, y):
        if self._move_mode:
            self._end_move()

    def cancel(self):
        self.cancel_move()

    # ------------------------------------------------------------------
    # Wand mask
    # ------------------------------------------------------------------

    def _generate_wand_mask(self, pil_img, seed_x: int, seed_y: int):
        """Build a layer-sized 'L' mask of all matching pixels."""
        # Always sample RGBA — dropping alpha treats transparent pixels as
        # whatever stale RGB is sitting underneath, which is wrong.
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")

        arr = np.asarray(pil_img, dtype=np.int16)  # (h, w, 4)
        h, w = arr.shape[:2]

        if not (0 <= seed_x < w and 0 <= seed_y < h):
            return None

        seed = arr[seed_y, seed_x]
        if self.sample_alpha:
            diff = np.sum(np.abs(arr - seed), axis=2)
        else:
            diff = np.sum(np.abs(arr[..., :3] - seed[:3]), axis=2)
        match = diff <= self.tolerance

        if not self.contiguous:
            return Image.fromarray((match.astype(np.uint8)) * 255, mode="L")

        # 4-connected flood fill via numpy + deque BFS, restricted to the
        # global match set. Anti-aliased edges typically still pass the
        # threshold so the boundary stays clean.
        out     = np.zeros((h, w), dtype=np.uint8)
        visited = np.zeros((h, w), dtype=bool)
        queue   = deque()
        queue.append((seed_x, seed_y))
        visited[seed_y, seed_x] = True

        while queue:
            cx, cy = queue.popleft()
            out[cy, cx] = 255
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h \
                        and not visited[ny, nx] and match[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))

        return Image.fromarray(out, mode="L")

    def _layer_to_canvas_mask(self, layer, layer_mask):
        """Pad/translate a layer-space mask to canvas-space."""
        cw, ch = self._canvas_size(layer)
        if layer_mask.size == (cw, ch) and layer.offset == (0, 0):
            return layer_mask
        full = Image.new("L", (cw, ch), 0)
        full.paste(layer_mask, layer.offset)
        return full


# -------------------------------------------------------------------------
# Required export
# -------------------------------------------------------------------------

TOOL_CLASS = MagicWandTool
