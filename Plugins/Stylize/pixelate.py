# pixelate.py
from PIL import Image
from app.plugins.plugin_api import Plugin, Setting

def _pixel(img, *, size=8):
    w,h = img.size
    small = img.resize((w//size, h//size), Image.NEAREST)
    return small.resize((w,h), Image.NEAREST)

class PixelatePlugin(Plugin):
    name = "Pixelate"
    def register(self, ctx):
        ctx.register_filter(
            "Pixelate",
            _pixel,
            settings=[Setting("size","int",8,"Pixel Size",1,64,1)],
            category="Game Dev"
        )