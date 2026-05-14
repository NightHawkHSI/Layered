import numpy as np
import time
from PIL import Image
from app.plugins.plugin_api import Plugin, PluginContext, Setting

class LivePixelSorter(Plugin):
    name = "Live Pixel Sorter"
    version = "1.5.0"

    def register(self, ctx: PluginContext) -> None:
        # Crucial: Save the context so the action can talk to the canvas
        self.ctx = ctx
        
        ctx.register_action(
            "Play Live Pixel Sort",
            self.run_sort_animation,
            settings=[
                Setting("speed", "float", 0.5, "Sort Speed (Delay)", 0.0, 1.0, 0.05),
                Setting("granularity", "int", 5, "Smoothness (Lines per Frame)", 1, 50),
                Setting("direction", "choice", "Vertical", "Direction", choices=["Vertical", "Horizontal"]),
                Setting("mode", "choice", "Transparency", "Sort By", choices=["Transparency", "Brightness"]),
                Setting("threshold", "int", 30, "Sensitivity", 0, 255),
            ],
            category="Glitch"
        )

    def run_sort_animation(self, speed=0.5, granularity=5, direction="Vertical", mode="Transparency", threshold=30):
        # 1. Get the current image
        idx = self.ctx.active_index()
        img = self.ctx.get_layer_image(idx)
        if not img:
            self.ctx.status("Select a layer first!")
            return

        # Convert to numpy for the 'math'
        arr = np.array(img.convert("RGBA"))
        out_arr = arr.copy()
        
        # Decide what we are measuring
        if mode == "Brightness":
            measure = (0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2])
        else:
            measure = arr[:,:,3] # Alpha channel

        # Rotate data if vertical
        is_vertical = (direction == "Vertical")
        if is_vertical:
            measure = measure.T
            arr = arr.swapaxes(0, 1)
            out_arr = out_arr.swapaxes(0, 1)

        rows, cols = measure.shape
        
        # Calculate delay (Speed 1.0 = 0 delay, Speed 0.0 = 0.1s delay)
        sleep_time = (1.0 - speed) * 0.05

        # 2. Start the Live Loop
        self.ctx.status("▶️ Sorting Live...")
        
        try:
            for i in range(rows):
                line_measure = measure[i]
                mask = line_measure >= threshold
                
                # Find segments to sort
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

                # --- THE LIVE PREVIEW PART ---
                # Only update the screen every 'granularity' lines to keep it smooth
                if i % granularity == 0 or i == rows - 1:
                    # Prepare current state for display
                    display_arr = out_arr
                    if is_vertical:
                        display_arr = out_arr.swapaxes(0, 1)
                    
                    # Push image to the active layer
                    frame = Image.fromarray(display_arr)
                    self.ctx.replace_active_layer_image(frame)
                    
                    # Force the app to repaint the canvas
                    self.ctx.refresh()
                    
                    # Progress bar update
                    self.ctx.progress(i / rows, f"Sorting line {i}...")
                    
                    # Pause so the user can actually see the movement
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            # 3. Finalize
            self.ctx.commit("Live Pixel Sort") # Save to undo history
            self.ctx.status("✅ Done!")
            
        except Exception as e:
            self.ctx.logger.error(f"Live Sort Crashed: {e}")
        finally:
            self.ctx.progress(None)