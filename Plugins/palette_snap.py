"""palette_snap.py — Retro Palette Snap filter for Layered.

Quantizes the active layer to a famous game-console or retro-computer
colour palette.  Three dithering algorithms let you control the look from
crisp pixel-art snapping to organic film-grain patterns.

Palettes
────────
  Game Boy DMG     4 colours  (classic green phosphor LCD)
  Game Boy Pocket  4 colours  (gray LCD)
  PICO-8          16 colours  (the iconic fantasy-console palette)
  NES             52 colours  (Nintendo PPU palette — common subset)
  CGA             16 colours  (IBM PC CGA mode, all colours)
  Commodore 64    16 colours  (the C64's fixed hardware palette)
  ZX Spectrum     15 colours  (Sinclair 8-colour × normal/bright)

Dithering
─────────
  None              flat nearest-colour snap — cleanest pixel art
  Floyd-Steinberg   error-diffusion — smooth gradients, natural look
  Bayer 4×4         ordered / crosshatch — retro CRT feel

Settings
────────
  Palette       which palette to snap to
  Dither        dithering algorithm
  Bayer Spread  noise strength for Bayer mode (ignored otherwise)

Install
───────
  Drop into  Plugins/palette_snap.py  and restart Layered.
  Appears under  Filters → Palette Snap.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


# ── Palette definitions ───────────────────────────────────────────────────────

# Each palette is a list of (R, G, B) tuples.
# Colours are the canonical, hardware-accurate values for each system.

PALETTES: dict[str, list[tuple[int, int, int]]] = {

    "Game Boy DMG": [
        (15,  56,  15),
        (48,  98,  48),
        (139, 172,  15),
        (155, 188,  15),
    ],

    "Game Boy Pocket": [
        (0,   0,   0),
        (85,  85,  85),
        (170, 170, 170),
        (255, 255, 255),
    ],

    "PICO-8": [
        (0,   0,   0),    (29,  43,  83),   (126, 37,  83),   (0,   135, 81),
        (171, 82,  54),   (95,  87,  79),   (194, 195, 199),  (255, 241, 232),
        (255, 0,   77),   (255, 163, 0),    (255, 236, 39),   (0,   228, 54),
        (41,  173, 255),  (131, 118, 156),  (255, 119, 168),  (255, 204, 170),
    ],

    "NES": [
        # Nintendo PPU palette — 52 commonly referenced colours
        (124, 124, 124), (0,   0,   252), (0,   0,   188), (68,  40,  188),
        (148, 0,   132), (168, 0,   32),  (168, 16,  0),   (136, 20,  0),
        (80,  48,  0),   (0,   120, 0),   (0,   104, 0),   (0,   88,  0),
        (0,   64,  88),  (0,   0,   0),
        (188, 188, 188), (0,   120, 248), (0,   88,  248), (104, 68,  252),
        (216, 0,   204), (228, 0,   88),  (248, 56,  0),   (228, 92,  16),
        (172, 124, 0),   (0,   184, 0),   (0,   168, 0),   (0,   168, 68),
        (0,   136, 136),
        (248, 248, 248), (60,  188, 252), (104, 136, 252), (152, 120, 248),
        (248, 120, 248), (248, 88,  152), (248, 120, 88),  (252, 160, 68),
        (248, 184, 0),   (184, 248, 24),  (88,  216, 84),  (88,  248, 152),
        (0,   232, 216), (120, 120, 120),
        (252, 252, 252), (164, 228, 252), (184, 184, 248), (216, 184, 248),
        (248, 184, 248), (248, 164, 192), (240, 208, 176), (252, 224, 168),
        (248, 216, 120), (216, 248, 120), (184, 248, 184), (184, 248, 216),
    ],

    "CGA": [
        (0,   0,   0),   (0,   0,   170),  (0,   170, 0),   (0,   170, 170),
        (170, 0,   0),   (170, 0,   170),  (170, 85,  0),   (170, 170, 170),
        (85,  85,  85),  (85,  85,  255),  (85,  255, 85),  (85,  255, 255),
        (255, 85,  85),  (255, 85,  255),  (255, 255, 85),  (255, 255, 255),
    ],

    "Commodore 64": [
        (0,   0,   0),   (255, 255, 255),  (136, 0,   0),   (170, 255, 238),
        (204, 68,  204), (0,   204, 85),   (0,   0,   170), (238, 238, 119),
        (221, 136, 85),  (102, 68,  0),    (255, 119, 119), (51,  51,  51),
        (119, 119, 119), (170, 255, 102),  (0,   136, 255), (187, 187, 187),
    ],

    "ZX Spectrum": [
        # Normal colours
        (0,   0,   0),   (0,   0,   215),  (215, 0,   0),   (215, 0,   215),
        (0,   215, 0),   (0,   215, 215),  (215, 215, 0),   (215, 215, 215),
        # Bright colours (no bright-black — same as black)
        (0,   0,   255),  (255, 0,   0),   (255, 0,   255),
        (0,   255, 0),   (0,   255, 255),  (255, 255, 0),   (255, 255, 255),
    ],
}

PALETTE_NAMES = list(PALETTES.keys())


# ── Bayer 4×4 ordered dither matrix ──────────────────────────────────────────

_BAYER_4 = np.array([
    [ 0,  8,  2, 10],
    [12,  4, 14,  6],
    [ 3, 11,  1,  9],
    [15,  7, 13,  5],
], dtype=np.float32) / 16.0   # values in [0, 1)


# ── Palette image builder (required by PIL's quantize) ────────────────────────

def _make_palette_image(colours: list[tuple[int, int, int]]) -> Image.Image:
    """Build a mode-P image whose palette holds *colours* in slots 0…N-1."""
    flat: list[int] = []
    for c in colours:
        flat.extend(c)
    flat += [0] * (768 - len(flat))   # pad to 256 × 3
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


# ── Core filter function ──────────────────────────────────────────────────────

def apply(
    image: Image.Image,
    *,
    palette:      str = "PICO-8",
    dither:       str = "Floyd-Steinberg",
    bayer_spread: int = 28,
) -> Image.Image:
    """Snap *image* colours to *palette* using the chosen dither algorithm.

    Parameters
    ----------
    image         Input image (RGBA).  Alpha is preserved and not quantized.
    palette       Key into PALETTES dict.
    dither        "None" | "Floyd-Steinberg" | "Bayer 4×4"
    bayer_spread  Noise amplitude for Bayer mode (0 = no dither, 64 = heavy).
    """
    colours  = PALETTES.get(palette, PALETTES["PICO-8"])
    pal_img  = _make_palette_image(colours)

    # Preserve alpha separately — quantize works on RGB only
    alpha: Image.Image | None = None
    if image.mode == "RGBA":
        alpha = image.getchannel("A")

    rgb = image.convert("RGB")

    # ── Bayer pre-noise ──
    if dither == "Bayer 4×4":
        arr = np.array(rgb, dtype=np.float32)
        h, w = arr.shape[:2]
        # Tile the 4×4 matrix to cover the full canvas
        bayer = np.tile(_BAYER_4, (h // 4 + 1, w // 4 + 1))[:h, :w]
        # Centre noise around zero, scale by spread
        noise = (bayer - 0.5) * bayer_spread
        arr   = np.clip(arr + noise[:, :, np.newaxis], 0, 255).astype(np.uint8)
        rgb   = Image.fromarray(arr, "RGB")
        pil_dither = Image.Dither.NONE
    elif dither == "Floyd-Steinberg":
        pil_dither = Image.Dither.FLOYDSTEINBERG
    else:
        pil_dither = Image.Dither.NONE

    # PIL's quantize() with an explicit palette image is fast (C-level)
    quantized = rgb.quantize(palette=pal_img, dither=pil_dither).convert("RGBA")

    # Restore original alpha so transparent game-asset edges are kept intact
    if alpha is not None:
        r, g, b, _ = quantized.split()
        quantized = Image.merge("RGBA", (r, g, b, alpha))

    return quantized


# ── Plugin registration ───────────────────────────────────────────────────────

class PaletteSnapPlugin(Plugin):
    name    = "Palette Snap"
    version = "1.0.0"
    author  = ""

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Palette Snap",
            apply,
            settings=[
                Setting(
                    name    = "palette",
                    type    = "choice",
                    default = "PICO-8",
                    label   = "Palette",
                    choices = PALETTE_NAMES,
                ),
                Setting(
                    name    = "dither",
                    type    = "choice",
                    default = "Floyd-Steinberg",
                    label   = "Dithering",
                    choices = ["None", "Floyd-Steinberg", "Bayer 4×4"],
                ),
                Setting(
                    name    = "bayer_spread",
                    type    = "int",
                    default = 28,
                    label   = "Bayer Spread",
                    min     = 0,
                    max     = 64,
                    step    = 4,
                ),
            ],
        )
        ctx.logger.info(
            "Palette Snap registered — %d palettes available",
            len(PALETTES),
        )

    def shutdown(self) -> None:
        return None