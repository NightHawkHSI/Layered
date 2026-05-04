# outer_glow.py
from PIL import Image, ImageFilter
import numpy as np
from app.plugin_api import Plugin, Setting

def _glow(img, *, radius=10, color=(255,255,0,255)):
    img = img.convert("RGBA")
    alpha = img.getchannel("A")

    glow = alpha.filter(ImageFilter.GaussianBlur(radius))
    arr = np.array(glow, dtype=float)

    r,g,b,a = color
    glow_img = Image.new("RGBA", img.size, (r,g,b,255))
    glow_img.putalpha(Image.fromarray(arr.astype("uint8")))

    out = glow_img.copy()
    out.paste(img,(0,0),img)
    return out

class GlowPlugin(Plugin):
    name = "Outer Glow"
    def register(self, ctx):
        ctx.register_filter(
            "Outer Glow",
            _glow,
            settings=[
                Setting("radius","int",10,"Radius",0,50,1),
                Setting("color","color",(255,255,0,255),"Color")
            ],
            category="Game Dev"
        )