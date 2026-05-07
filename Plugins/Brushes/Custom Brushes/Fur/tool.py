import importlib.util, math, sys, random
from pathlib import Path
from PIL import Image, ImageDraw
from app.layer import Layer
from app.tools import Tool

# ── load shared builtins ──────────────────────────────────────────────────────
_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_bt   = sys.modules[_K]
_walk = _bt._walk


class FurBrushTool(Tool):
    """Fur / Hair brush.

    Each stamp fires a fan of thin curling strands outward from the cursor.
    Strands taper from full width at the root down to a single pixel at the
    tip, and their opacity fades toward the end.  A sine-wave curl bends each
    strand sideways as it grows.

    Settings
    --------
    Strands   – how many hairs per stamp (1–60)
    Length    – strand length in px (4–200)
    Spread °  – angular fan width in degrees (1–360); 360 = full circle
    Curl      – lateral bend amplitude in px (0–40)
    Taper     – how quickly strands fade at the tip (0–100)
    """

    name = "Fur"
    icon = "🦔"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.strand_count = 20
        self.length       = 40
        self.spread_deg   = 30    # fan half-angle; full fan = spread_deg * 2
        self.curl         = 10
        self.taper        = 70    # 0 = no fade, 100 = fully transparent at tip

        self._stroke_angle: float = -math.pi / 2   # direction of travel
        self._last_pt: tuple[int, int] | None = None

    # ── settings bar ──────────────────────────────────────────────────────────
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
            ("strand_count", "Strands",  1,  60, 80),
            ("length",       "Length",   4, 200, 90),
            ("spread_deg",   "Spread °", 1, 360, 80),
            ("curl",         "Curl",     0,  40, 75),
            ("taper",        "Taper",    0, 100, 75),
        ]:
            row.addWidget(lbl(label))
            s = SliderField(lo, hi, getattr(self, attr), slider_width=w)
            s.valueChanged.connect(lambda v, a=attr: setattr(self, a, int(v)))
            row.addWidget(s)

        row.addStretch()
        return host

    # ── stroke lifecycle ──────────────────────────────────────────────────────
    def _spacing(self):
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing * 0.3)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stroke_angle = -math.pi / 2       # default: upward
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        if abs(dx) > 1 or abs(dy) > 1:
            # update stroke direction so strands flow with the brush movement
            self._stroke_angle = math.atan2(dy, dx)
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    # ── stamp ─────────────────────────────────────────────────────────────────
    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy  = layer.offset
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        W, H    = layer.image.width, layer.image.height

        length     = max(4, self.length)
        spread_rad = math.radians(max(1, self.spread_deg))
        half_spread = spread_rad / 2.0
        steps      = max(6, length)          # segments per strand
        step_len   = length / steps

        # bounding box for the scratch canvas
        pad  = length + 4
        bx0  = max(0, cx - ox - pad)
        by0  = max(0, cy - oy - pad)
        bx1  = min(W, cx - ox + pad)
        by1  = min(H, cy - oy + pad)
        bw   = bx1 - bx0
        bh   = by1 - by0
        if bw <= 0 or bh <= 0:
            return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        sd      = ImageDraw.Draw(scratch)

        # root in scratch coords
        rx = cx - ox - bx0
        ry = cy - oy - by0

        for _ in range(max(1, self.strand_count)):
            # random angle within the fan, centred on stroke direction
            angle = self._stroke_angle + random.uniform(-half_spread, half_spread)

            # random per-strand variation
            strand_len   = length * random.uniform(0.55, 1.0)
            s_steps      = max(4, int(steps * strand_len / length))
            s_step_len   = strand_len / s_steps
            curl_dir     = random.choice((-1, 1))
            curl_freq    = random.uniform(0.8, 1.4)   # sine frequency
            curl_phase   = random.uniform(0, math.pi)
            strand_alpha = int(alpha * random.uniform(0.6, 1.0))

            px, py = float(rx), float(ry)

            for step in range(s_steps):
                t = step / s_steps          # 0 → 1 along strand

                # perpendicular curl offset (sine wave bending)
                curl_offset = (
                    self.curl
                    * math.sin(curl_freq * math.pi * t + curl_phase)
                    * curl_dir
                )
                perp_angle = angle + math.pi / 2
                nx = px + math.cos(angle) * s_step_len + math.cos(perp_angle) * curl_offset * s_step_len / strand_len
                ny = py + math.sin(angle) * s_step_len + math.sin(perp_angle) * curl_offset * s_step_len / strand_len

                # taper: width shrinks from ~2 at root to 1 at tip
                seg_w = max(1, int(2 * (1.0 - t)))

                # opacity fade toward tip
                fade     = 1.0 - (self.taper / 100.0) * t
                seg_a    = int(strand_alpha * max(0.0, fade))
                if seg_a < 2:
                    px, py = nx, ny
                    continue

                sd.line(
                    [(round(px), round(py)), (round(nx), round(ny))],
                    fill=(r, g, b, seg_a),
                    width=seg_w,
                )
                px, py = nx, ny

        layer.image.alpha_composite(scratch, dest=(bx0, by0))


TOOL_CLASS = FurBrushTool