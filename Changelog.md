# Changelog

## 2026-04-30 (round 7)

### Added
- **Persistent dock layout.** `MainWindow` now saves geometry +
  `saveState()` to `QSettings("Layered", "Layered")` on close and
  restores both on launch — every dock's size, area, floating state,
  and the toolbar position survive across sessions. A snapshot of the
  default layout is taken at construction so it can be restored later.
- **View → Panels submenu.** One toggle action per dock (Layers,
  History, Colors, Console, Projects) plus the Tools & Brush
  toolbar, generated from `dock.toggleViewAction()` so the checkmark
  state stays in sync when docks are closed via their `×` button.
- **View → Reset Layout.** Restores the default geometry / dock
  arrangement and re-shows any closed panel.

### Changed
- **Layers dock is roomier.** Layer list `setMinimumHeight(220)` and
  History dock is split below Layers via `splitDockWidget(...,
  Qt.Vertical)` so several layers are visible without resizing.
- **All docks fully drag-snappable.** `_add_dock` now sets
  `AllDockWidgetAreas` plus `Movable | Floatable | Closable`, so any
  panel — including Projects — can be dragged into any edge area and
  snaps in, or torn off as a floating window.
- Each dock and the toolbar now have `objectName`s so `saveState()` /
  `restoreState()` can match them on the next launch.

## 2026-04-30 (round 6)

### Added
- **Layer thumbnails.** `LayerPanel` shows a 40px preview of each
  layer's image as the list item's icon, so layers are recognisable at
  a glance without renaming.
- **Project tab thumbnails.** Each project tab now carries a 28px
  composited preview of its canvas next to the project name, built from
  `LayerStack.composite()` at every `_refresh_tabs()`.
- **Color wheel + quick palette in the Colors panel.** New
  `ColorWheel` widget (HSV: hue around the ring, saturation along the
  radius, brightness via a slider). Below it, a 16-swatch quick
  palette. **Left-click** on the wheel or any swatch sets the
  **primary** color; **right-click** sets the **secondary** color.
  Both work during drag for fine tuning.

### Changed
- **Per-layer export filenames match layer names.** `export_layers`
  now writes each file as `<layer-name>.<ext>` (sanitized — non
  alphanumeric / `-_ ` characters become `_`). Duplicate names are
  disambiguated with ` (2)`, ` (3)`, …. The previous `NN_` index
  prefix is gone. Manifest still records the index.

## 2026-04-30 (round 5)

### Added
- **New canvas dialog.** Single `NewCanvasDialog` with width + height spin
  boxes replaces the back-to-back `QInputDialog` prompts.
- **Top hot bar for tools + brush settings.** `ToolPanel` gained a
  `layout="toolbar"` mode (compact horizontal). Mounted as a top
  `QToolBar` so the tool buttons and brush size / hardness / opacity /
  spacing controls stop monopolising side-dock space.
- **Session-remembered export folder.** `MainWindow` tracks
  `_last_export_dir` / `_last_open_dir`; the export, save, and open
  dialogs default to the previously used directory.
- **File → Open Recent.** Submenu lists the last 10 opened images and
  re-opens with one click. Updated automatically by `Open…` and
  `Open as Layer…`.
- **Application icon.** `Icon.png` converted to a multi-resolution
  `Icon.ico` (16/24/32/48/64/128/256). Window + app icon set on startup.
  `build.bat` now passes `--icon` to PyInstaller and bundles both
  `Icon.ico` and `Icon.png` so the icon is present at runtime in the
  one-file build.
- **Transform tool.** New tool with 8 anchor handles plus a center-move
  region drawn around the active layer's opaque bounding box. Drag a
  handle to scale; hold Shift for uniform scaling (preserves aspect
  ratio). Implemented via PIL crop → `Image.resize(LANCZOS)` → paste
  back into the canvas-sized layer. `Canvas` now tracks the Shift
  modifier through `ToolContext.shift_held`, exposes
  `canvas_to_screen`, and calls `tool.paint_overlay(painter, canvas)`
  during repaint so tools can draw screen-space overlays.

### Fixed
- **Outline plugin did nothing + no settings panel.** `outline_filter`
  now registers a `Setting[]` spec (color / thickness / opacity /
  softness / placement) so the generic plugin settings dialog actually
  opens. `apply()` accepts those kwargs, draws either behind or in
  front of the source, and respects opacity. Verified: produces a
  visible outline ring on transparent layers (156 outline pixels around
  a 10×10 test square).

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
