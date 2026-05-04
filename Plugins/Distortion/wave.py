# wave.py
import math
import numpy as np
from PIL import Image
from app.plugin_api import Plugin, Setting

def _wave(img, *, amplitude=5, frequency=20):
    img = img.convert("RGBA")
    arr = np.array(img)
    h,w,_ = arr.shape

    out = np.zeros_like(arr)

    for y in range(h):
        shift = int(math.sin(y/frequency)*amplitude)
        out[y] = np.roll(arr[y], shift, axis=0)

    return Image.fromarray(out, "RGBA")

class WavePlugin(Plugin):
    name = "Wave Distortion"
    def register(self, ctx):
        ctx.register_filter(
            "Wave",
            _wave,
            settings=[
                Setting("amplitude","int",5,"Amplitude",0,50,1),
                Setting("frequency","int",20,"Frequency",1,100,1)
            ],
            category="Game Dev"
        )