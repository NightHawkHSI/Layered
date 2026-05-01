# Changelog

## 2026-05-01 (round 19)

### Fixed
- **Enter no longer drops the active selection.** With no text editor
  focused, pressing Return/Enter would activate whichever `QPushButton`
  Qt had marked autoDefault — typically the project tabs' "+ New" or
  the layer panel's "+ Add" — and the resulting project switch / layer
  insertion looked like a deselect. `MainWindow.keyPressEvent` now
  swallows stray Return / Enter at the window level. Text inputs
  (`QLineEdit`, `QSpinBox`, `QPlainTextEdit`, …) consume the key event
  before it bubbles up, so typing into a panel still works.

## 2026-05-01 (round 18)

### Fixed
- **Cross-project paste actually drops the pixels now.** Round 17's
  cross-project branch was guarded by `cb.ownsClipboard()`, which is
  unreliable on Windows — a modal dialog such as `NewCanvasDialog` can
  briefly flip clipboard ownership. When that happened, paste fell
  through to the legacy bottom branch which placed the layer at the
  *source* project's bbox coordinates (often outside the new tiny
  canvas), so the user saw an empty paste even though the new canvas
  was sized correctly. `_on_paste` is now restructured: it picks the
  source up front (prefers `_copy_buffer`, falls back to the external
  clipboard, and prefers the external one only when its dimensions
  differ from the buffer — i.e. another app overwrote the clipboard),
  then runs a single same-project / cross-project branch. No more
  fall-through to a stale code path.

## 2026-05-01 (round 17)

### Added
- **Cross-project paste.** Copying a selection in project A and pasting
  it in project B (or in a brand-new canvas created with `File → New`)
  now works. `_on_copy` tags `_copy_buffer` with the source `Project`
  reference, and `_on_paste` branches on it: same-project pastes still
  drop the pixels back at the original bbox position, while
  cross-project pastes go through `_ask_paste_mode` (the same
  Extend / Anchor / Crop dialog used for external clipboard images) so
  the pasted layer is sized sensibly against the destination canvas.
  Was previously broken because the paste used the source project's
  bbox coordinates verbatim, often dropping the layer outside the new
  canvas's bounds.

## 2026-05-01 (round 16)

### Fixed
- **New-canvas dims now match the size of an internal copy.** Round 15
  read only the system clipboard, which on Windows can pad / reformat
  images set via `QClipboard.setImage` and so didn't always reflect the
  exact bbox of an in-app `Ctrl+C`. `_on_new` now checks `_copy_buffer`
  first — the PIL image cached by `_on_copy` is the authoritative
  cropped selection — and only falls back to `_image_from_clipboard`
  when nothing was copied internally. The width / height spin boxes now
  reliably show the size of the copied selection.

## 2026-05-01 (round 15)

### Added
- **New canvas defaults to clipboard image size.** `MainWindow._on_new`
  inspects the clipboard via the existing `_image_from_clipboard`
  helper; if an image is present, the `NewCanvasDialog` is opened with
  its width / height pre-filled to the clipboard image's dimensions
  instead of the static 1024 × 768. Spin boxes still let the user
  override before accepting.

## 2026-05-01 (round 14)

### Changed
- **Selection drag now lifts the pixels, not just the marching ants.**
  Round 13 moved the selection mask but left the pixels behind, so
  Lasso / Marquee / Magic Wand selections only repositioned the outline.
  `_SelectionToolBase._begin_move_if_inside` now also:
  1. Translates the canvas-space selection mask into layer-image space
     via `paste(mask, (-ox, -oy))`.
  2. Splits the active layer's RGBA, multiplies the alpha with the
     layer-space mask to produce a *lifted* image (selected pixels
     only) and with the inverted mask to produce a *base* image (layer
     with the selection erased).
  3. Replaces `layer.image` with the base, so the original location
     becomes transparent immediately on press.
  `_continue_move` then re-pastes the lifted image onto the base at
  `(dx, dy)` each frame and shifts the mask by the same delta.
  `_end_move` calls `ctx.commit_action("Move selection")` so the lift +
  drop is one undoable action. Magic Wand was extended with `move` /
  `release` handlers so it benefits from the same drag-move (its
  click-to-select behaviour is unchanged when the press lands outside
  the current selection).

## 2026-05-01 (round 13)

### Added
- **Drag a selection to reposition it.** `_SelectionToolBase` gained
  `_begin_move_if_inside` / `_continue_move` / `_end_move`. When the
  Marquee or Lasso tool is active and the user presses *inside* the
  current selection mask, the press starts a drag-move instead of a new
  selection — the original mask is shifted by the cursor delta on each
  move and re-committed (with a fresh bbox via `getbbox()`) so the
  marching ants follow the cursor. Releasing keeps the moved selection;
  pressing outside the mask still starts a new selection.

### Fixed
- **Lasso now selects the polygon interior, not just the line.**
  `LassoTool.release` explicitly closes the point list (appends the
  first point if the user did not return to it) and draws the polygon
  with both `fill=255` *and* `outline=255` so the resulting `L`-mode
  mask always covers the enclosed area plus its boundary. Paint tools
  clipped through `_apply_selection_to_stamp` consequently affect the
  whole interior.

## 2026-05-01 (round 12)

### Fixed
- **Quick-color swatches no longer overflow into adjacent docks.**
  `ColorPanel` now hosts its content in a `QScrollArea` (frameless,
  resize-aware), so when the dock is shorter than the natural content
  height the panel scrolls instead of letting the bottom row of quick
  colors paint past the panel boundary onto the dock below.

### Changed
- **VSCode-style dock drop indicators.** `QApplication.setStyle("Fusion")`
  in `main.py` ensures Qt's native dock drop zones (split top/bottom/
  left/right per dock + tabify center) render consistently across
  platforms and themes. Combined with the existing
  `AnimatedDocks | AllowNestedDocks | AllowTabbedDocks | GroupedDragging`
  options and `setDockNestingEnabled(True)`, dragging a panel now shows
  the same four-arrow-plus-center snap overlay as VSCode.

## 2026-05-01 (round 11)

### Added
- **Session restore.** Open projects persist across runs. New
  `app/session.py` writes each project to `session/proj_NNN/` on close
  (one PNG per layer plus `meta.json` with name/path/dimensions/active
  index/dirty flag and per-layer name, visible, opacity, blend_mode,
  offset, locked, group). On launch, `MainWindow` calls `load_session`
  before falling back to `Project.blank`. Explicit `Close Project` (and
  `Ctrl+W`) re-saves the session so closed projects do not reappear.
  History, selections, and clipboard remain ephemeral.
- **Tools dock.** New `tools_dock` layout in `ToolPanel` builds a
  2-column compact grid of tool buttons inside a left `QDockWidget`, so
  every brush/tool button is visible at once instead of clipping behind
  the toolbar overflow chevron. Settings strip stays on the top
  `Tool settings` toolbar. Tools dock is split above Colors on the left;
  Text dock tabified with Colors. Old `Tools` `QToolBar` removed and the
  `View → Panels → Tools bar` toggle replaced by the standard `Tools`
  dock toggle.

### Fixed
- **Panels can shrink, not just grow.** Hard minimum sizes that locked
  docks at large widths/heights were relaxed: `LayerPanel` list min
  height 220 → 60 (and `setMinimumSize(0, 0)` on the panel itself),
  `ColorWheel` min size 160×160 → 60×60, `ProjectTabs` select button min
  width 140 → 60, and `setMinimumSize(0, 0)` on `TextPanel`,
  `HistoryPanel`, `LogConsole`, and `ProjectTabs`. Docks now drag to
  small widths/heights without snapping back to a floor.

## 2026-05-01 (round 10)

### Added
- **VSCode-style free-form dock layout that persists.** Enabled
  `setDockNestingEnabled(True)` plus
  `AnimatedDocks | AllowNestedDocks | AllowTabbedDocks | GroupedDragging`,
  and pinned the corners so the left/right side bars run full-height and
  the bottom panel spans full width. Any panel (Layers, History, Colors,
  Text, Console, Projects) can be dragged to any edge, split-nested,
  tabbed onto another panel (`TabPosition.North`), or floated as its
  own window — drag a tab group as one with grouped dragging. Drop
  indicators snap to the nearest valid spot edge-to-edge. Layout now
  saves on every dock move / float toggle / visibility change / window
  resize+move (debounced 400 ms via `QTimer`) instead of only on close,
  so a crash no longer loses the layout. Existing
  `restoreState`/`restoreGeometry` on start-up brings everything back
  exactly where you left it.
- **Persistent shape edit handles.** Rectangle and Ellipse drop their
  bbox + 8 corner/edge handles + center-move region after the initial
  drag. Drag a handle to resize, drag inside to move, hold Shift for
  aspect-locked scale or axis-locked move. Click outside the bbox to
  commit and start a new shape; switching tools also commits. New
  `_ShapeTool` base in `app/tools.py`; `ToolContext` gained
  `commit_action` so shape sessions can flush their own history
  snapshots, and `MainWindow._on_tool_selected` now calls
  `prev.commit()` for any tool that exposes one.
- **Five new asset-creation plugins.**
  - `Drop Shadow` — soft offset shadow with blur + opacity + color.
  - `Color Replace` — swap a target color (with tolerance) for another.
  - `Posterize` — quantize each channel to N levels for flat shading.
  - `Gradient Map` — remap luminance to a 2-color gradient.
  - `Pixel Art Resize` — nearest-neighbor up/down-scale that preserves
    crisp pixel edges.
- **Modifier-scroll canvas pan.** Plain wheel still zooms; **Shift+wheel**
  pans horizontally, **Ctrl+wheel** pans vertically. Step is derived
  from `angleDelta().y()` (40 px per notch).

### Fixed
- **Brush settings only show what the active tool uses, without
  reflowing the toolbar.** Picked Brush used to display
  Hardness/Opacity/Spacing/Fill-shape/Tolerance all at once even on
  tools where those did nothing. Built a per-tool `TOOL_SETTINGS` map;
  `ToolPanel.set_active_tool(name)` now greys out every setting the
  active tool doesn't read (kept visible so the toolbar width / widget
  positions never change between tools — disabled state signals "exists
  for other tools, inactive now"). Fill / Magic Wand finally get their
  `Tolerance` slider (was previously dialog-only).
- **Tool & Brush bar split into two rows.** The single tool toolbar
  packed buttons + every setting on one line and clipped via the chevron
  overflow. Now: row 1 is tool buttons (with `addToolBarBreak`); row 2
  is the per-tool settings strip. Each can be toggled separately under
  View → Panels.
- **Project tabs stacked vertically.** The bottom Projects dock used a
  horizontal row of tabs that scrolled off-screen as soon as you opened
  more than a few projects. Now stacked top-to-bottom with the `+ New`
  button at the top and a vertical scroll bar; each tab fills the dock
  width with a left-aligned label (`text-align: left; padding: 4px 8px`).
  Drop the dock on a side bar and it behaves like a VSCode explorer
  pane.

## 2026-04-30 (round 9)

### Fixed
- **Tool buttons sized to their labels.** Toolbar buttons used a Fixed
  size policy with no min width, which clipped longer names like
  "Magic Wand" / "Clone Stamp". They now size to the text width plus
  padding (and tighter spacing) so every label is fully readable.
- **Hidden panels reappear on toggle.** The View → Panels checkboxes
  used `dock.toggleViewAction()` directly, which sometimes left a
  re-shown dock at zero size (and stuck floating). Replaced with a
  custom toggle that re-attaches the dock to its initial area, calls
  `setFloating(False)`, raises it, and forces a sane size via
  `resizeDocks` if Qt restored it at 0×0.
- **Recent files persist across sessions.** `MainWindow._recent_files`
  is now loaded from `QSettings("Layered","Layered")/files/recent` at
  start-up, saved on every add, and pruned to existing paths only.
  Added a `Clear Recent` entry. Menu labels now show
  `<filename> — <parent>` rather than the full path.

### Added
- **Live text editing.** New `TextPanel` dock (left area) bound to
  `TextTool`. Click the canvas with the Text tool to drop a dedicated
  *Text* layer; everything below is rendered live as you type:
  - Text string (`QLineEdit`).
  - Font size (`QSpinBox`).
  - Font family (`QComboBox` populated from `QFontDatabase`).
  - Color (the existing primary-color swatch is the text color, so
    color-wheel / palette picks update the text in real time).
  Drag-clicking on the canvas relocates the in-progress text. Switching
  to another tool (or the panel's *Commit* button) finalises the text
  layer and snapshots a history entry. `ToolContext` gained
  `text_font`.

## 2026-04-30 (round 8)

### Added
- **Selection model.** New `Selection` (bbox + L-mask) on `Project`.
  All paint tools (brush, eraser, gradient, blur/sharpen/smudge,
  clone-stamp) clip stamps through the selection mask via
  `_apply_selection_to_stamp`, so edits stay inside the marching-ants
  region.
- **Marquee, Lasso, Magic Wand selection tools** that all commit a
  canvas-sized mask through `ToolContext.set_selection` and draw their
  in-progress rubber-band/polyline as a tool overlay.
- **Edit menu: Cut / Copy / Paste / Select All / Deselect** with
  shortcuts `Ctrl+X / Ctrl+C / Ctrl+V / Ctrl+A / Ctrl+D`. Copy stores a
  PIL image of the active layer's pixels masked by the current
  selection (or the whole canvas if none), Paste creates a new layer
  positioned at the original bbox.
- **Gradient tool.** Drag to draw a linear gradient from primary →
  secondary color. Honors active selection.
- **Text tool.** Click to drop text. On tool selection a small dialog
  prompts for string + size; rendered through PIL `ImageDraw.text`
  using Arial when available, default font otherwise.
- **Blur / Sharpen / Smudge brushes.** Soft circular brush stamps that
  apply `ImageFilter.GaussianBlur` / `SHARPEN` / pixel-pull within the
  brush mask, throttled by the existing brush size / hardness /
  spacing / opacity settings, and selection-aware.
- **Clone Stamp tool.** Alt-click to set a source point; subsequent
  drags stamp the offset region from the source. Honors brush settings
  + selection.
- **Filled shapes.** New "Fill shape" toggle in the top toolbar
  applies to Rectangle / Ellipse — fills with primary color instead of
  outlining. Holding Shift constrains them to a perfect square /
  circle.
- **Selection bbox overlay.** `Canvas` paints a dashed rectangle for
  any active selection (set via `selection_provider`).

### Changed
- **Painting lag fixed.** During a stroke, `Canvas.layer_changed`
  no longer triggers a full `LayerPanel.refresh()` (which rebuilt list
  rows + thumbnails per move) or a `_refresh_tabs()` (which composited
  per-project previews). Both run only on `action_committed`. Drawing
  is dramatically faster.
- **Plugin polish.**
  - `Glow Filter`: gained `radius` / `intensity` / `mode`
    (screen/add/lighten) settings; alpha preserved.
  - `Normal Map`: settings for `strength`, `invert_x`, `invert_y`, and
    height `source` (luminance vs alpha).
  - `Make Tileable`: rewritten as a filter (was an action), with a
    new `blend_seams` mode that hides cross-tile seams via a
    Gaussian-blurred composite of a 3×3 self-tiled super-image plus the
    original `offset` mode.
- `ToolContext` gained `alt_held`, `fill_shape`, `text`, `text_size`,
  and `get_selection` / `set_selection` callbacks.

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
