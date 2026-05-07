import importlib.util, math, sys
from pathlib import Path
from PIL import Image, ImageDraw
from app.layer import Layer
from app.tools import Tool

_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_walk = sys.modules[_K]._walk


class WeaveBrushTool(Tool):
    """Weave / basket-weave brush.

    Stamps a tile of interlocking horizontal and vertical thread segments.
    Alternating rows/columns are offset by half a cell so every crossing
    looks like one thread passing over and one passing under, producing a
    woven-fabric appearance.

    Settings
    --------
    Cell     – size of one weave cell in px (4–40)
    Thread   – thickness of each thread (1–Cell/2)
    Angle °  – rotate the whole weave tile (0–180)
    Contrast – how dark the "under" threads appear (0–100)
    """

    name = "Weave"
    icon = "▦"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.cell_size  = 10
        self.thread_w   = 3
        self.angle_deg  = 0
        self.contrast   = 50
        self._last_pt: tuple[int, int] | None = None

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField

        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px;")
            return l

        for attr, label, lo, hi, w in [
            ("cell_size", "Cell",     4, 40, 75),
            ("thread_w",  "Thread",   1, 20, 75),
            ("angle_deg", "Angle °",  0, 180, 80),
            ("contrast",  "Contrast", 0, 100, 80),
        ]:
            row.addWidget(lbl(label))
            s = SliderField(lo, hi, getattr(self, attr), slider_width=w)
            s.valueChanged.connect(lambda v, a=attr: setattr(self, a, int(v)))
            row.addWidget(s)

        row.addStretch()
        return host

    def _spacing(self):
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing * 0.5)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy  = layer.offset
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        W, H    = layer.image.width, layer.image.height
        br      = max(2, self.ctx.brush_size // 2)
        cell    = max(4, self.cell_size)
        tw      = max(1, min(self.thread_w, cell // 2))

        # under-thread is the colour darkened by contrast %
        dark_f  = 1.0 - self.contrast / 100.0
        dr      = int(r * dark_f)
        dg      = int(g * dark_f)
        db      = int(b * dark_f)

        # build a square weave tile slightly bigger than the brush
        tile_sz = (br * 2 + cell * 2)
        # round up to nearest multiple of cell so pattern tiles cleanly
        tile_sz = ((tile_sz + cell - 1) // cell) * cell

        tile = Image.new("RGBA", (tile_sz, tile_sz), (0, 0, 0, 0))
        td   = ImageDraw.Draw(tile)

        cols = tile_sz // cell
        rows = tile_sz // cell

        # ── layer 1: horizontal threads (drawn first = "under" at even cols) ──
        for row_i in range(rows + 1):
            y0 = row_i * cell - tw // 2
            y1 = y0 + tw
            # draw full-width horizontal stripe
            td.rectangle([0, y0, tile_sz, y1], fill=(r, g, b, alpha))

        # ── layer 2: vertical threads (drawn on top, gaps reveal horizontal) ──
        for col_i in range(cols + 1):
            x0 = col_i * cell - tw // 2
            x1 = x0 + tw
            # draw full-height vertical stripe
            td.rectangle([x0, 0, x1, tile_sz], fill=(r, g, b, alpha))

        # ── layer 3: over/under illusion ──
        # At each intersection we paint a small square in either the
        # horizontal or vertical colour depending on the weave pattern.
        # Even (row+col): horizontal thread on top  → vertical is under → darken it
        # Odd  (row+col): vertical thread on top    → horizontal is under → darken it
        for row_i in range(rows + 1):
            for col_i in range(cols + 1):
                ix  = col_i * cell - tw // 2
                iy  = row_i * cell - tw // 2
                # which thread passes under at this crossing?
                if (row_i + col_i) % 2 == 0:
                    # horizontal under: paint a dark vertical patch here
                    td.rectangle([ix, iy, ix + tw, iy + tw],
                                 fill=(dr, dg, db, alpha))
                else:
                    # vertical under: paint a dark horizontal patch here
                    td.rectangle([ix, iy, ix + tw, iy + tw],
                                 fill=(dr, dg, db, alpha))

        # ── rotate the tile if requested ──────────────────────────────────────
        if self.angle_deg % 180 != 0:
            tile = tile.rotate(self.angle_deg, expand=False,
                               resample=Image.BILINEAR)

        # ── mask to brush circle ──────────────────────────────────────────────
        mask = Image.new("L", (tile_sz, tile_sz), 0)
        ImageDraw.Draw(mask).ellipse(
            [tile_sz // 2 - br, tile_sz // 2 - br,
             tile_sz // 2 + br, tile_sz // 2 + br],
            fill=255,
        )
        tile.putalpha(Image.fromarray(
            __import__("PIL.ImageChops", fromlist=["multiply"])
            .multiply(tile.getchannel("A"), mask)
        ))

        # ── composite onto layer ──────────────────────────────────────────────
        lx   = cx - ox - tile_sz // 2
        ly   = cy - oy - tile_sz // 2
        dx   = max(0, lx);  dy = max(0, ly)
        cr_x = max(0, -lx); cr_y = max(0, -ly)
        cr_w = min(tile_sz - cr_x, W - dx)
        cr_h = min(tile_sz - cr_y, H - dy)
        if cr_w <= 0 or cr_h <= 0:
            return
        crop = tile.crop((cr_x, cr_y, cr_x + cr_w, cr_y + cr_h))
        layer.image.alpha_composite(crop, dest=(dx, dy))


TOOL_CLASS = WeaveBrushTool