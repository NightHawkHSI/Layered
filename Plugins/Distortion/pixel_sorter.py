import numpy as np
import time
from PIL import Image
from app.plugin_api import Plugin, PluginContext, Setting

class AnimatedSorterPlugin(Plugin):
    name = "Animated Pixel Sorter"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        # We register as an ACTION so we can control the animation loop
        ctx.register_action(
            "Animate Pixel Sort",
            self.start_animation,
            settings=[
                Setting("speed", "float", 0.5, "Animation Speed", 0.0, 1.0, 0.05),
                Setting("chunk_size", "int", 10, "Lines per Frame", 1, 100),
                Setting("direction", "choice", "Vertical", "Direction", choices=["Vertical", "Horizontal"]),
                Setting("threshold", "int", 50, "Transparency Threshold", 0, 255),
            ],
            category="Glitch"
        )

    def start_animation(self, speed=0.5, chunk_size=10, direction="Vertical", threshold=50):
        # 1. Get the current image from the active layer
        img = self.ctx.get_layer_image(self.ctx.active_index())
        if not img:
            self.ctx.status("No active layer found!")
            return

        arr = np.array(img.convert("RGBA"))
        out_arr = arr.copy()
        
        # Prepare the measurement map (using Alpha/Transparency)
        measuring_map = arr[:,:,3]

        is_vertical = (direction == "Vertical")
        if is_vertical:
            measuring_map = measuring_map.T
            arr = arr.swapaxes(0, 1)
            out_arr = out_arr.swapaxes(0, 1)

        rows, cols = measuring_map.shape

        # 2. Setup the "Speed" (Delay)
        # Higher speed setting = lower sleep time
        delay = (1.0 - speed) * 0.1 

        self.ctx.status("Sorting started... Watch the canvas!")

        # 3. The Animation Loop
        for i in range(rows):
            line_measure = measuring_map[i]
            mask = line_measure >= threshold
            
            # Find sorting segments
            padded = np.concatenate(([False], mask, [False]))
            diff = np.diff(padded.astype(int))
            starts = np.where(diff == 1)[0]
            ends = np.where(diff == -1)[0]
            
            for s, e in zip(starts, ends):
                if e - s < 2: continue
                segment = arr[i, s:e]
                seg_vals = line_measure[s:e]
                indices = np.argsort(seg_vals)
                out_arr[i, s:e] = segment[indices]

            # 4. UPDATE THE UI
            # Every 'chunk_size' lines, push the new image to the screen
            if i % chunk_size == 0 or i == rows - 1:
                # Convert back to PIL
                temp_arr = out_arr
                if is_vertical:
                    temp_arr = out_arr.swapaxes(0, 1)
                
                frame_img = Image.fromarray(temp_arr)
                
                # Replace the image on the active layer directly
                self.ctx.replace_active_layer_image(frame_img)
                
                # Force the app to redraw
                self.ctx.refresh()
                
                # Update progress bar
                self.ctx.progress(i / rows, f"Sorting line {i}...")
                
                # Pause so the user can see it
                if delay > 0:
                    time.sleep(delay)

        # 5. Finalize
        self.ctx.commit("Animated Pixel Sort") # Add to Undo history
        self.ctx.progress(None)
        self.ctx.status("Sorting complete!")