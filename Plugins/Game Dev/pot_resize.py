# pot_resize.py
from PIL import Image
from app.plugins.plugin_api import Plugin, Setting

def _next_pot(x):
    p = 1
    while p < x:
        p *= 2
    return p

def _resize(img: Image.Image, *, upscale: bool = True) -> Image.Image:
    w, h = img.size
    nw, nh = _next_pot(w), _next_pot(h)

    if not upscale:
        nw = w if nw == w else nw // 2
        nh = h if nh == h else nh // 2

    return img.resize((nw, nh), Image.NEAREST)

class POTResizePlugin(Plugin):
    name = "Power of Two Resize"
    def register(self, ctx):
        ctx.register_filter(
            "Power of Two Resize",
            _resize,
            settings=[Setting("upscale","bool",True,"Upscale Instead of Downscale")],
            category="Game Dev"
        )