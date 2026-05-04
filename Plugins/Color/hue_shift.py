# hue_shift.py
import numpy as np
from PIL import Image
from app.plugin_api import Plugin, Setting

def _hue(img: Image.Image, *, shift: int = 90):
    img = img.convert("RGBA")
    arr = np.array(img)

    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]

    arr[:,:,0] = (r + shift) % 256
    arr[:,:,1] = (g + shift) % 256
    arr[:,:,2] = (b + shift) % 256

    return Image.fromarray(arr, "RGBA")

class HueShiftPlugin(Plugin):
    name = "Hue Shift"
    def register(self, ctx):
        ctx.register_filter(
            "Hue Shift",
            _hue,
            settings=[Setting("shift","int",90,"Shift",0,255,1)],
            category="Game Dev"
        )