# Changelog

## 2026-04-30 (round 4)

### Added
- **Import options dialog (button-style).** `DropActionDialog` rewritten:
  three large action buttons (Open as new project / Add as new layer /
  Replace current canvas) plus checkboxes for **Center on canvas** and
  **Scale to fit if larger than canvas**. Reused by both drag-and-drop and
  `File → Open as Layer`.
- **Centered import + scale-to-fit.** New `app/image_ops.py` (`fit_to_canvas`,
  `centered_offset`, `place_on_canvas`). When importing as a layer, images
  are scaled down to fit the canvas (preserving aspect) when larger and
  centered by default.
- **Plugin settings.** Plugin API extended:
  - New `Setting` dataclass (`type` ∈ `int`/`float`/`bool`/`choice`/`color`/
    `string`).
  - `register_filter(name, fn, settings=...)` and
    `register_action(name, fn, settings=...)`.
  - Plugin loader stores settings as `FilterEntry` / `ActionEntry`.
  - `app/ui/plugin_settings_dialog.py` builds a configuration dialog from
    the spec list and passes the result as kwargs to the plugin callback.
  - Filter / action menu items now show `…` when settings are present and
    pop the dialog before invoking.
- **Sample plugins updated** with settings to demo the new API:
  - Grayscale: `method` (Luminance/Average/Lightness) and `strength`.
  - Invert: `channels` (RGB/Red/Green/Blue/Alpha) and `preserve_alpha`.

## 2026-04-30 (round 3)

### Added
- **Undo / Redo** with `Ctrl+Z` and `Ctrl+Y` (also `Ctrl+Shift+Z`).
  Implemented in `app/history.py`: each project carries its own
  `History` ring of up to 50 deep-copied `LayerStack` snapshots.
- **History panel** (right dock). Lists every recorded action with the
  current entry highlighted; clicking any entry jumps the project state
  back to that snapshot. Includes Undo / Redo buttons.
- **Commit hooks** wired across the app:
  - Tools: `Tool.commit_on` ("press" for Fill, "release" for Brush /
    Eraser / Move / Line / Rect / Ellipse, `None` for Picker). Canvas
    emits `action_committed` so MainWindow can take a snapshot.
  - Layer panel: emits `committed(label)` for add/delete/up/down/rename
    /visibility/blend/opacity-release.
  - Filters, Clear Layer, Resize Canvas, Drop → Add Layer, Drop → Replace
    Canvas all commit.

## 2026-04-30 (round 2)

### Added
- **Move tool.** New tool that drags the active layer's `offset` so layers
  can be repositioned on the canvas (no longer locked at 0,0). Tools panel
  shows a "Move" button.
- **Brush settings group** with:
  - **Numeric size input** (`QSpinBox`, 1–1024) alongside the slider, kept
    in sync.
  - **Hardness slider** (0–100%) — controls how soft the circular stamp
    falls off at the edges. Stamps are cached per (size, hardness) pair.
  - **Opacity slider** (1–100%) — flow control independent of color alpha.
  - **Spacing slider** (1–100% of brush size) — distance between stamps
    along a stroke.
- **Soft circular brush + eraser.** Replaces the hard line+disk drawing.
  Brush composites tinted-mask stamps onto the active layer; eraser reduces
  alpha by the same mask.
- **Delete layer UX.** Layer panel button renamed `Delete`; pressing the
  `Delete` key while the layer list has focus deletes the active layer.
  Added `Edit → Delete Active Layer` (Ctrl+Delete).

## 2026-04-30

### Fixed
- **Lag while drawing.** `LayerStack` now caches a "below the active layer"
  composite as a Pillow image. Strokes only re-blend the active layer plus
  any layers above it. Normal blend mode uses Pillow's C-implemented
  `alpha_composite` (NumPy is now only the fallback for non-normal modes).
  Composite time on a 1024×768 / 5-layer stack: ~326 ms → ~17 ms.
- **Scale was off / canvas pushed off-screen.** Canvas now auto-fits the
  zoom on resize and on layer-stack swap. Added `View → Fit to Window`
  (Ctrl+0) and `View → Zoom 100%` (Ctrl+1). Zoom no longer clamps to a
  hard-coded screen size.
- **Right-click drew a dot.** `Canvas.mousePressEvent` now ignores any
  button that isn't `LeftButton` (middle still pans, right is reserved for
  future context menus).

### Added
- **Bottom-of-Layers "Export…" button** that opens a unified export dialog.
- **Multi-format export.** PNG, WEBP, TIFF, DDS, BMP, JPG. Per-layer or
  single composite. Per-layer export still writes a `manifest.json` with
  offsets, opacity, blend mode, and visibility for game-pipeline use.
- **Alpha policy.** Formats that support alpha (PNG, WEBP, TIFF, DDS) honor
  the "Preserve alpha channel" toggle. Formats that don't (JPG, BMP) — or
  any format with the toggle disabled — flatten over a user-pickable
  background color (default white).
- **Drag-and-drop images** onto the canvas. Prompts whether to open as a
  new project, add as a new layer, or replace the current canvas. Multi-file
  drops are supported (replace uses the first file).
- **Project tabs** at the bottom of the window. Each open project gets a
  selectable tab with its own Save (💾) and Close (✕) buttons. `+ New`
  creates a fresh project. `Ctrl+W` closes the current project; closing
  the last one auto-creates a blank canvas. The window title and tab
  labels show a dirty (`*`) marker until the project is saved/exported.

### Internal
- New `app/project.py` (Project document) and `app/ui/project_tabs.py`,
  `app/ui/export_dialog.py`, `app/ui/drop_dialog.py`.
- Layer panel now signals `export_requested` so the bottom button reuses
  the same export dialog as `File → Export…`.
- `LayerStack.invalidate_cache()` is called from layer panel mutations
  (visibility, blend mode, opacity, reorder, add/remove, resize) so the
  below-cache stays consistent.
