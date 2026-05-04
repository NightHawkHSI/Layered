# alpha_threshold.py
import numpy as np
from PIL import Image
from app.plugin_api import Plugin, Setting

def _alpha(img, *, threshold=128):
    img = img.convert("RGBA")
    arr = np.array(img)

    alpha = arr[:,:,3]
    alpha = (alpha > threshold) * 255

    arr[:,:,3] = alpha.astype("uint8")
    return Image.fromarray(arr, "RGBA")

class AlphaThresholdPlugin(Plugin):
    name = "Alpha Threshold"
    def register(self, ctx):
        ctx.register_filter(
            "Alpha Threshold",
            _alpha,
            settings=[Setting("threshold","int",128,"Threshold",0,255,1)],
            category="Game Dev"
        )