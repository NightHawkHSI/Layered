# Changelog

## 2026-05-02 (round 27)

### Changed
- **`build.bat` now reports live stage progress.** The previous
  script redirected the entire build into `build-error.log` and
  showed nothing on screen until everything finished, so a
  multi-minute PyInstaller freeze looked indistinguishable from a
  hang. Each stage now prints a `[NN%] description` line to the
  console (mirror source 5%, check Python 15%, upgrade pip 20%,
  install requirements 35%, install PyInstaller 50%, generate icon
  55%, freeze exe 60%, copy plugins 92%, copy assets 96%, done
  100%) while the verbose tool output (pip, robocopy, pyinstaller)
  still goes to the log. On failure, the script prints the
  failing stage and tails the last 40 lines of the log via
  `powershell Get-Content -Tail 40` so the actual error is visible
  without opening the file.

## 2026-05-02 (round 26)

### Added
- **Project save / load via `.layered` files.** New `app/project_io.py`
  bundles a `Project` into a single ZIP-deflated archive containing
  `manifest.json` (name, description, canvas size, active index,
  per-layer metadata: name / visibility / opacity / blend mode /
  offset / locked / group), one `layer_NNN.png` per layer, and an
  optional `selection.png` (canvas-sized L mask) so the active
  selection round-trips. File menu gained:
  - **Open Project…** — picks a `.layered` archive and adds it as a
    new tab.
  - **Save Project** (`Ctrl+S`) — writes back to the project's
    existing `.layered` path; falls through to *Save Project As* if
    none is set yet.
  - **Save Project As…** (`Ctrl+Shift+S`) — file dialog with the
    `.layered` filter, force-appends the extension if missing,
    updates `proj.path` / `proj.name` / window title, and pushes
    the path into Recent Files.
  Recent Files now route by extension: `.layered` paths reopen as
  projects, image extensions still go through the original image
  loader. `Ctrl+S` previously bound to *Quick Save Composite*; that
  action moved off the shortcut and stays available from the menu.
  *File → Open…* (image) renamed to *Open Image…* to disambiguate
  it from *Open Project…*. Verified a 2-layer project with custom
  opacity / blend mode / active-index / selection round-trips
  through save → load with all metadata intact in a 1 KB archive.

## 2026-05-02 (round 25)

### Fixed
- **Radial paste menu shadow artefact on the right and bottom edges.**
  Two converging causes on Windows. (1) `Qt.WindowType.Popup |
  FramelessWindowHint` still inherits the OS-level Windows 11 popup
  drop shadow; added `Qt.WindowType.NoDropShadowWindowHint`.
  (2) `WA_TranslucentBackground` allocates a translucent back buffer
  but does not auto-clear it between repaints, so the previous
  frame's antialiased ring leaked along the right/bottom strips.
  `paintEvent` now starts with a `CompositionMode_Source` +
  `fillRect(transparent)` clear before drawing the wedges.
- **Layer panel could not shrink below the natural button-row width.**
  The action buttons (`+ Add`, `Dup`, `Delete`, `Up`, `Down`,
  `Rename`) sized themselves to fit their text labels, which forced
  the panel's minimum width to roughly six full English labels —
  too wide for narrow side docks on smaller / scaled displays.
  Buttons now use single-glyph labels (`＋`, `⎘`, `✕`, `▲`, `▼`,
  `✎`) with the original text moved to tooltips, plus
  `setMinimumWidth(0)` and a `QSizePolicy.Ignored` horizontal
  policy that lets each button shrink past its sizeHint without
  clipping the dock. Same `Ignored` policy applied to the blend
  combo, opacity slider, and Export button so the entire panel
  collapses to roughly the layer-list thumbnail width.

## 2026-05-02 (round 24)

### Added
- **Radial paste menu at the cursor.** `Ctrl+V` now pops a frameless
  pie menu (`app/ui/radial_menu.py`) with the paste destinations as
  ring wedges instead of dropping pixels immediately. Default
  options: *New Layer*, *Current Layer*, *New Project*. When the
  clipboard image is bigger than the current canvas, the menu
  expands to five wedges — *New Layer (keep canvas)*, *Current Layer
  (keep canvas)*, *New Layer (extend canvas)*, *Current Layer
  (extend canvas)*, *New Project* — so canvas-resize decisions are
  inline with the paste choice rather than a separate modal. Hover
  highlights, click commits, click outside or Esc cancels. The
  underlying paste primitives (`_paste_new_layer`,
  `_paste_into_layer`, `_paste_new_project`) are shared with the
  `Ctrl+Shift+V` quick-paste-into-current shortcut and the legacy
  resolve-source flow. The legacy `_ask_paste_mode` modal is no
  longer reached on the standard `Ctrl+V` path.
- **Selection modifier keys for Marquee / Lasso / Magic Wand.**
  `ToolContext` gained `ctrl_held`, populated each event by
  `Canvas._update_modifiers`. Behaviour:
  - **Shift** → add the new selection to the current one
    (`ImageChops.lighter`).
  - **Alt** → subtract the new selection from the current one
    (`current AND NOT new`, threshold-binarised).
  - **Ctrl** (Magic Wand only) → select-similar: skip the
    flood-fill contiguity pass and select every pixel in the layer
    matching the clicked color within `fill_tolerance` (Photoshop's
    "Select → Similar"). Combines with Shift/Alt the same way.
  When Shift or Alt is held, the existing drag-move-inside logic in
  `_SelectionToolBase._begin_move_if_inside` is suppressed so a
  click inside the current selection can refine it instead of
  accidentally lifting pixels.

## 2026-05-02 (round 23)

### Changed
- **Selection marching ants follow the actual mask shape.** The
  canvas used to paint a single dashed `QRect` over `sel.bbox`, so
  a Magic-Wand selection of a circle still showed a square outline,
  obscuring which pixels were actually selected. `Canvas.paintEvent`
  now traces the mask boundary into 1-pixel canvas-space edge
  segments via four vectorised numpy passes (top / bottom / left /
  right boundary detection: `arr[i, :] & ~arr[i-1, :]` etc., with
  boundary-row fall-throughs so masks that touch the canvas edge
  still close), converts each segment to screen coords, and emits
  them via a single `QPainter.drawLines(QLineF[])` call. Result:
  circle selections paint a dashed circle, lasso selections paint
  the polygon outline, brush-feathered alpha masks paint the alpha
  contour. Cached per `(id(mask), mask.size)` so a stationary
  selection costs zero recomputation across pan/zoom repaints.

### Added
- **Paste Into Current Layer** (`Ctrl+Shift+V`, Edit menu).
  Clipboard pixels alpha-composite into the active layer instead of
  creating a new layer. Same source resolution as `Ctrl+V` (prefers
  `_copy_buffer`, falls back to the system clipboard); same-project
  pastes land at the original bbox position so a copy → paste-into
  round-trip is positionally lossless, and cross-project pastes
  anchor at canvas (0, 0). Pixels are blitted into a layer-sized
  numpy buffer and merged with `Image.alpha_composite`, so blending
  is correct over partially-opaque destinations (no premultiply).
  Selection clears on paste, matching the new-layer paste flow.

## 2026-05-02 (round 22)

### Fixed
- **Copy/paste round-trip is now byte-exact for anti-aliased and
  semi-transparent pixels.** Round 21 switched the same-project paste
  to a no-mask `paste(img, dest)` to dodge the implicit alpha-mask
  premultiply on the *destination* side, but `_on_copy` was still
  using `canvas_layer.paste(src, (ox, oy))` on the *source* side.
  Pillow's behaviour for `paste` with an RGBA source and no explicit
  mask is version-dependent — some builds copy RGBA verbatim, others
  silently use the source alpha as a mask, which premultiplies RGB
  into a transparent destination and squares the alpha. Anti-aliased
  brush edges (any pixel with α < 255) lost colour and faded toward
  zero alpha across that step, so the user saw "didn't copy all the
  colors or pixels" even after the destination-side fix landed.
  Replaced both the source-blit (in `_on_copy`) and the four paste
  blits (same-project, extend, anchor, crop) with explicit NumPy
  slice assignment + a numpy `α × sel_mask // 255` for the selection
  multiply. No more PIL-version-dependent paste semantics anywhere
  in the copy/paste path; verified a 20×20 anti-aliased gradient
  round-trips with `np.array_equal == True` on every alpha value
  including the feathered edges.
- **Enter exits the post-paste Transform.** Round 21's
  `_confirm_selection` only flushed tools that exposed a `commit()`
  method, but `TransformTool` does not — it commits per-release
  through `commit_on = "release"` and instead just keeps drawing its
  bbox + 8 handles overlay until the user picks a different tool.
  Pasting auto-activates Transform, and pressing Enter would clear
  the (already-cleared) selection while leaving the handles on
  screen, looking like Enter was a no-op. Now `_confirm_selection`
  also switches the active tool back to `Brush` whenever the active
  tool is `Transform` / `Sel Transform` / `Move`, so Enter cleanly
  drops the transform overlay and the marching ants together. Tool
  switch goes through the existing `_on_tool_selected` path so
  `prev.commit()` still fires for tools that need it.

## 2026-05-02 (round 21)

### Fixed
- **Same-project paste finally drops the actual pixels.** Round 20
  fixed the *copy* side (no more PIL paste-with-mask premultiply on
  the way into `_copy_buffer`), but `_on_paste`'s same-project branch
  still called `canvas_layer.paste(img, (bb[0], bb[1]), img)` —
  passing `img` as the mask, which re-runs the same premultiply on
  the way back out: for any source pixel whose alpha is < 255, the
  RGBA blends into a transparent destination as
  `out_rgb = src_rgb × alpha/255`, `out_alpha = src_alpha²/255`. A
  brush stroke painted at <100% opacity (or any anti-aliased edge)
  paints with sub-255 alpha everywhere, so paste produced a layer
  whose pixels were so faint and so small-alpha that the user only
  saw the dashed selection rectangle drawn on top. Same fix in the
  three cross-project / external paste branches. Now using a
  no-mask `paste(img, dest)` which is a verbatim RGBA copy (the
  cropped buffer already carries `layer_alpha × sel_mask` as its own
  alpha, so a mask second-multiply was always wrong, not just
  redundant).
- **Paste clears the source selection.** The dashed marching-ants
  rectangle from the original copy used to keep drawing on top of
  the pasted layer, which read as "the selection moved but the
  pixels didn't" even when the pixels were correct. `_on_paste` now
  sets `proj.selection = None` before refresh in both same-project
  and cross-project branches.

### Added
- **Layer panel: Duplicate button.** New `Dup` button between
  `+ Add` and `Delete` (tooltip notes the existing `Ctrl+J`
  shortcut). Routes through `LayerPanel.duplicate_requested` →
  `MainWindow._on_duplicate_layer` so the click and the menu/
  shortcut go through the exact same code path (history snapshot
  included).
- **Enter confirms the active selection.** `MainWindow.keyPressEvent`
  used to swallow Return/Enter outright (round 19). Now it routes
  through a new `_confirm_selection`: any tool that exposes a
  `commit()` (Sel Transform, Text, shape edit sessions) gets called
  first so an in-progress floating buffer or shape lands as a
  history entry, then `proj.selection` is cleared and the canvas is
  refreshed. Photoshop-style Enter-to-confirm. Text inputs still
  consume the key before it bubbles up, so typing a layer name or
  spinbox value still works.

## 2026-05-02 (round 20)

### Fixed
- **Magic Wand copy/paste/move actually moves pixels, not just the
  marching ants.** Three converging bugs:
  1. `MagicWandTool.press` sampled `arr[y, x]` with canvas coords on a
     layer-local NumPy buffer, so any layer with a non-zero offset
     either flood-filled from the wrong target or threw an index error,
     producing a mask that didn't enclose the clicked pixels.
  2. The wand also produced a layer-sized mask `(w + ox, h + oy)`
     while marquee/lasso committed canvas-sized masks via
     `Selection.rect`. Downstream code (`_on_copy`, `_on_cut`,
     `_apply_selection_to_stamp`) silently used whichever size the
     active selection happened to be, so cropping a marquee then a
     wand produced different alpha alignment.
  3. `_on_copy` used `tmp.paste(layer.image, offset, layer.image)` —
     PIL's paste-with-mask premultiplies source RGB into a transparent
     destination, so any pixel under alpha < 255 came out darkened
     before the alpha was rewritten with `sel_mask × layer_alpha`.
  Fix: wand now converts to layer-local coords (`x - ox, y - oy`) for
  sampling and indexing; a new `ToolContext.get_canvas_size` callback
  lets every selection tool build canvas-sized masks via a shared
  `_canvas_size` helper; `_on_copy` does a straight `paste` (no mask)
  onto a canvas-sized RGBA buffer and multiplies the pixel alpha by
  the canvas-aligned selection mask afterwards. `_on_cut` got the
  same defensive size handling. Marquee and Lasso bbox math was
  cleaned up to drop the double-offset that had been canceling out
  only when `layer.offset == (0, 0)`.

### Added
- **Selection transform with anchor handles.** New
  `SelectionTransformTool` (`Ctrl+T`, "Sel Transform" in the tools
  dock). On first interaction it lifts the pixels under the active
  selection mask off the layer (`layer.image = base; floating =
  layer × mask`), then renders 8 corner/edge handles plus a
  center-move region around the bbox. Drag a handle to scale the
  lifted pixels with `LANCZOS` resampling (Shift = aspect-lock); drag
  inside to translate; click outside to commit. The selection mask
  follows the bbox live so the marching ants always wrap the floating
  pixels. Switching tools commits via the existing `prev.commit()`
  hook.
- **Image menu.** Crop to Selection, Resize Image (LANCZOS resample
  with proportional layer-offset rescaling), Flip Horizontal/Vertical,
  Rotate 90 CW / 90 CCW / 180 (canvas dims swap on the 90s), Flatten
  Image, plus the existing Resize Canvas. All operations rebuild
  per-layer offsets so layers with non-zero offsets stay anchored
  correctly through the transform.
- **Layer menu.** New Layer (`Ctrl+Shift+N`), Duplicate Layer
  (`Ctrl+J`, copies image + visibility/opacity/blend/offset/lock/
  group), Merge Down (`Ctrl+Shift+E`, composites the active layer
  into the one below using the existing blend pipeline; respects
  blend mode, opacity, and visibility).
- **Edit menu QoL.** Invert Selection (`Ctrl+Shift+I`, computes
  `255 - mask` and rebuilds the bbox), Transform Selection (`Ctrl+T`,
  switches to Sel Transform), Fill with Primary (`Alt+Backspace`),
  Fill with Secondary (`Ctrl+Backspace`). Fill respects the active
  selection and the active layer's offset; with no selection, fills
  the whole layer.
- **View menu.** Zoom In (`Ctrl+=` and `Ctrl++` for both layouts),
  Zoom Out (`Ctrl+-`).

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
