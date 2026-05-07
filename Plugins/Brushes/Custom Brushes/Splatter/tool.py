import importlib.util, math, sys, random
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


class SplatterBrushTool(Tool):
    """Ink Splatter brush.

    Each stamp drops a central ink blob surrounded by elongated tear-drop
    droplets that radiate outward — just like ink hitting paper at speed.
    Tiny satellite microdots scatter further out for extra realism.

    Settings
    --------
    Drops     – number of radiating droplets (1–40)
    Reach     – how far droplets fly (10–300 px)
    Elongation – how stretched the droplets are (1–12)
    Chaos     – randomness of drop angle & size (0–100)
    Micro     – number of tiny satellite dots (0–60)
    """

    name = "Splatter"
    icon = "💦"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.drops       = 12
        self.reach       = 60
        self.elongation  = 5
        self.chaos       = 60
        self.micro       = 20
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
            ("drops",      "Drops",  1,  40, 75),
            ("reach",      "Reach",  10, 300, 85),
            ("elongation", "Elong",  1,  12, 75),
            ("chaos",      "Chaos",  0, 100, 75),
            ("micro",      "Micro",  0,  60, 75),
        ]:
            row.addWidget(lbl(label))
            s = SliderField(lo, hi, getattr(self, attr), slider_width=w)
            s.valueChanged.connect(lambda v, a=attr: setattr(self, a, int(v)))
            row.addWidget(s)

        row.addStretch()
        return host

    def _spacing(self):
        return max(4.0, self.reach * 0.6)

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
        chaos_f = self.chaos / 100.0

        pad  = self.reach + self.elongation + 6
        lx   = cx - ox
        ly   = cy - oy
        bx0  = max(0, lx - pad);  bx1 = min(W, lx + pad)
        by0  = max(0, ly - pad);  by1 = min(H, ly + pad)
        bw   = bx1 - bx0;         bh  = by1 - by0
        if bw <= 0 or bh <= 0:
            return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        sd      = ImageDraw.Draw(scratch)
        rx, ry  = lx - bx0, ly - by0

        # central blob
        blob_r = max(2, self.ctx.brush_size // 3)
        sd.ellipse([rx - blob_r, ry - blob_r, rx + blob_r, ry + blob_r],
                   fill=(r, g, b, alpha))

        # radiating elongated droplets
        for i in range(self.drops):
            base_angle = (2 * math.pi * i / self.drops)
            angle = base_angle + random.uniform(-chaos_f, chaos_f) * math.pi
            dist  = self.reach * random.uniform(0.3 + (1 - chaos_f) * 0.4, 1.0)
            drop_a = int(alpha * random.uniform(0.5, 1.0))

            # droplet tip position
            tip_x = rx + dist * math.cos(angle)
            tip_y = ry + dist * math.sin(angle)

            # droplet body: elongated ellipse pointing from centre to tip
            elong = self.elongation * random.uniform(0.5, 1.5)
            short = max(1, int(blob_r * random.uniform(0.2, 0.6)))
            long_ = max(short + 1, int(short * elong))

            # build a tiny rotated ellipse
            cell_w = long_ * 2 + 4
            cell_h = short * 2 + 4
            cell   = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
            ImageDraw.Draw(cell).ellipse(
                [2, cell_h // 2 - short, cell_w - 2, cell_h // 2 + short],
                fill=(r, g, b, drop_a),
            )
            deg = math.degrees(angle)
            cell = cell.rotate(-deg, expand=True, resample=Image.BILINEAR)

            # place midpoint of droplet between centre and tip
            mid_x = int((rx + tip_x) / 2) - cell.width // 2
            mid_y = int((ry + tip_y) / 2) - cell.height // 2
            # clip to scratch bounds
            dx = max(0, mid_x);  dy = max(0, mid_y)
            cx2 = min(bw - dx, cell.width  - max(0, -mid_x))
            cy2 = min(bh - dy, cell.height - max(0, -mid_y))
            if cx2 > 0 and cy2 > 0:
                src_x = max(0, -mid_x);  src_y = max(0, -mid_y)
                crop  = cell.crop((src_x, src_y, src_x + cx2, src_y + cy2))
                scratch.alpha_composite(crop, dest=(dx, dy))

        # micro satellite dots
        for _ in range(self.micro):
            angle = random.uniform(0, 2 * math.pi)
            dist  = self.reach * random.uniform(0.6, 1.4)
            mx    = int(rx + dist * math.cos(angle))
            my    = int(ry + dist * math.sin(angle))
            mr    = random.randint(1, max(1, blob_r // 3))
            ma    = int(alpha * random.uniform(0.3, 0.9))
            sd.ellipse([mx - mr, my - mr, mx + mr, my + mr],
                       fill=(r, g, b, ma))

        layer.image.alpha_composite(scratch, dest=(bx0, by0))


TOOL_CLASS = SplatterBrushTool