# Changelog

## 2026-05-14 — App Package Reorg, New Blend Modes, Theme Engine, Custom Shortcuts, Mirror View

### Added
1. **`app/core/blending.py` — Soft Light, Color, and Saturation blend
   modes.** Soft Light is the W3C separable dodge/burn formula and runs on
   both the numpy and numba JIT paths (new `_MODE_SOFT_LIGHT = 9` kernel
   branch). Color and Saturation are the W3C non-separable HSL modes
   (`_set_luma` / `_set_sat` / `_clip_color` helpers); they are numpy-only,
   so `composite()` now routes any mode not in `_MODE_IDS` past the kernel
   instead of silently falling back to Normal. `BLEND_MODES` now has 12
   entries and the layer-panel dropdown picks them up automatically.

2. **`app/render/canvas.py` — non-destructive Mirror View.** New
   `_mirror_x` flag with `set_mirror_x()` / `mirror_x()`; `_to_canvas_coords`
   and `canvas_to_screen` are mirror-aware so tools, selection ants, and
   overlays stay correct, and a shared `_draw_canvas_pixmap` helper flips
   the composite + selection-highlight blits. Exposed in **View → Mirror
   View Horizontally** (`Ctrl+Shift+M`). Pixels are never touched — an
   artist trick for spotting composition errors.

3. **Custom keyboard shortcuts.** `app/app_ui/preferences.py` gained a
   `shortcuts` override map; `MainWindow._act()` reads it (built-in default
   otherwise) and registers every menu action in `self._actions`. New
   `app/ui/shortcuts_dialog.py` lists all rebindable actions with
   `QKeySequenceEdit` fields — only overrides differing from the default
   are persisted. Reachable via **Edit → Keyboard Shortcuts…**.

4. **`app/app_ui/theme.py` — dark / light theme engine.** Builds a full
   `QPalette` + base QSS for either theme; `MainWindow._apply_theme()`
   installs it and re-layers the accent colour on top. New `theme` pref,
   selectable in the Preferences dialog with live preview.

### Changed
5. **`app/` reorganised into subpackages.** Flat module layout replaced
   with `core/` (layer, project, history, blending, image_ops,
   adjustments), `render/` (canvas, gpu_renderer, tile_renderer), `io/`
   (export, project_io, session, brush_loader), `plugins/` (plugin_api,
   plugin_loader, tool_loader, tools), and `app_ui/` (theme, preferences,
   logger); `main_window.py` stays at the package root, `ui/` and
   `controllers/` are unchanged. All intra-`app` imports, the ~40 bundled
   plugins, the tests, and `main.py` were updated. **Plugin authors:**
   `from app.plugin_api import …` is now `from app.plugins.plugin_api
   import …`; `app.tools` → `app.plugins.tools`. The PyInstaller build
   needs no change — `--collect-submodules app` is recursive.

6. **`app/plugins/plugin_loader.py` — fuller type hints.** `load_plugins`
   now annotates `layer_stack` / `canvas`, `_load_module` returns
   `ModuleType`, `LoadedPlugin.plugin` is `Optional[Plugin]`, and the inner
   `_register_*` closures declare `-> None`.

## 2026-05-13 — Tool Panel Flow Layout & Shrink-to-Fit

### Changed
1. **`app/ui/tool_panel.py` — buttons auto-arrange + shrink so the dock
   works at any width and position.** Replaced fixed 3-column
   `QGridLayout` with a new in-file `_FlowLayout(QLayout)` that wraps
   children left-to-right when width runs out (`hasHeightForWidth=True`,
   `heightForWidth` reports stacked height for the given viewport). Used
   in both `set_tool_groups()` and `_reflow_grid()`; the `_COLUMNS`
   constant is kept only for backwards compatibility.

2. **`_ToolBtn` — shrinkable size policy.** Min `(44, 44)`, max
   `(96, 96)`; `sizeHint`/`minimumSizeHint` return those bounds so flow
   wrap math is stable. Was previously locked at 84×84.

3. **`ToolPanel._build_ui()` — narrow-dock friendly chrome.** Active
   label gets `setWordWrap(True)` + `QSizePolicy.Ignored` horizontal so
   long tool names don't push the panel wide. Search field placeholder
   shortened to "Search..." and given `Ignored` horizontal policy.
   `QScrollArea.horizontalScrollBarPolicy = ScrollBarAlwaysOff` forces
   wrap rather than horizontal pan. Content margins `8 → 0`, spacing
   `14 → 10`.

4. **`ToolPanel.__init__` — `setMinimumWidth(_BTN_MAX + 16)` (112 px).**
   Guarantees at least one full-size button column plus scrollbar room
   regardless of where the dock is placed.

5. **`grid_host` widgets — `heightForWidth` size policy.** Both grouped
   and ungrouped paths set `QSizePolicy.setHeightForWidth(True)` on the
   host so the outer `QVBoxLayout` propagates the flow layout's
   width-dependent height up through the scroll area.

## 2026-05-13 — New Brush Categories, Tablet Pressure, Sandbox Permissions, Layer Masks, Adjustment Layers, Smart Objects, Tile + GPU Render

### Added
1. **`Plugins/Brushes/Pixel Art Kit/` — new brush category for pixel art.**
   Three tools: **Pixel Pencil** (`N`) — hardness 1.0, integer coords, 1-px
   spacing; **Pixel Eraser** (`Shift+E`) — hard aliased erase via
   `_stamp_erase`; **Pixel Line** (`Shift+L`) — Bresenham line with snapshot
   + redraw on `move`, Shift snaps to 45° octants. All three share a
   single-size cached `_brush_mask(size, 1.0)` and short-circuit on
   integer coordinates so output is always grid-aligned (no anti-aliased
   half-pixel bleed).

2. **`Plugins/Brushes/Basic/Fill/` — flood fill (paint bucket) tool (`F`).**
   `commit_on = "press"`; reads pixel under cursor, returns early if
   target color already equals primary, snapshots the layer, calls
   `ImageDraw.floodfill(thresh=tolerance)` and then
   `_clip_layer_to_selection(layer, ctx, before)` so the fill is bounded
   by the active selection (everything outside the marquee is restored
   from the snapshot). Tolerance slider 0–255.

3. **`Plugins/Brushes/Basic/` — four new round/flat brushes.**
   **Hard Round** (`Shift+H`) — hardness 1.0, fixed size, opacity +
   spacing sliders; for blocking-in and UI outlines. **Soft Round**
   (`Shift+S`) — hardness 0.0, pressure-opacity dynamic; reads
   `ctx.pressure` first, falls back to stroke-velocity mapping
   (`50 px/s → 1.0`, `1500 px/s → 0.15`). **Variable Inker** (`Shift+I`)
   — hardness 1.0, pressure-size dynamic with `SIZE_MIN_FRAC = 0.15`,
   per-stamp mask cache keyed by integer size. **Chisel Flat**
   (`Shift+C`) — rotated rectangular mask built by `_flat_mask(w, h,
   angle)` via `ImageDraw.polygon` over rotated corners; W / H / Angle
   / Opacity sliders, cache invalidated on any setting change.

4. **`app/canvas.py` + `app/tools.py` — Tablet/Stylus pressure pipeline.**
   New `Canvas.tabletEvent(e)` routes `QEvent.Type.TabletPress` /
   `TabletMove` / `TabletRelease` through the active tool, calling
   `self._set_pressure(e.pressure())` before each press/move/release.
   `_tablet_stroke_active` guard discards stray `TabletMove`s arriving
   without a preceding press, accepts events to suppress Qt's synthetic
   mouse twin, and resets the pressure to `None` on release.
   `mousePressEvent` clears stale tablet pressure when no tablet stroke
   is active so a mouse user never inherits the last stylus value.
   `ToolContext.pressure: Optional[float] = None` plumbs the value to
   brushes; Soft Round and Variable Inker consume it directly, mouse
   strokes fall back to velocity mapping.

5. **`app/tool_loader.py` + `app/tools.py` — plugin permission sandbox.**
   `KNOWN_PERMISSIONS = {"clipboard", "web", "filesystem", "subprocess"}`
   defines the four capabilities a plugin can declare via a
   `"permissions": [...]` array in `tool.json`. `load_tools` validates
   each entry (`logging.warning` on unknown / wrong-type), stores the
   accepted subset as `inst._granted_permissions: frozenset`, and the
   `Tool.has_permission(name)` method lets host code at clipboard /
   network / fs / subprocess call sites gate access. Empty default — a
   tool that omits `permissions` gets nothing.

6. **`app/layer.py` — non-destructive layer masks.**
   `Layer.mask: Optional[Image.Image]` (mode `"L"`) and
   `Layer.mask_enabled: bool = True`. `LayerStack._positioned` multiplies
   `image.alpha` by `mask` (resized if size differs) before pasting at
   `layer.offset` — the existing fast path that returned the bare image
   now defers to the mask branch when one is present. Helpers on Layer:
   `add_mask(reveal_all=True/False)`, `remove_mask()`, `apply_mask()`
   (bakes the mask into the alpha channel and clears the attribute).
   `resize_canvas` pads the mask with black (hidden) outside the
   original area; `merge_down` / `merge_up` clear the destination layer's
   mask after merge so the baked composite isn't double-masked.

7. **`app/adjustments.py` + `app/layer.py` — non-destructive adjustment
   layers.** Six built-in filters in the `ADJUSTMENTS` registry:
   *Brightness, Contrast, Invert, Grayscale, Levels* (black / white /
   gamma) and *Hue/Saturation* (hue shift / saturation scale / lightness
   add). Each is `(callable, default_params_dict)`. `Layer.adjustment:
   Optional[str]` + `Layer.adjustment_params: dict` mark a layer as an
   adjustment; in `_blend_onto`, adjustment layers skip the pixel-stamp
   path entirely and call `apply_adjustment(base, name, params)` on the
   running composite, then `_blend_adjustment_result` composites the
   filtered image back through the layer's mask × opacity. New helper
   `LayerStack.add_adjustment(name, params, label)` constructs the
   layer with default params merged.

8. **`app/layer.py` — Smart Objects.**
   `Layer.source_path: Optional[str]` + `Layer.source_mtime:
   Optional[float]` mark a layer as a smart object. `_rasterize_source`
   opens the source — image files via `Image.open(...).convert("RGBA")`,
   nested `.layered` projects via `project_io.load_project` plus
   `stack.composite()` (centred into the host canvas if dimensions
   differ). `LayerStack.add_smart_object(path, name)` rasterizes
   immediately and records the source mtime;
   `LayerStack.refresh_smart_objects()` walks all layers, compares
   `Path(src).stat().st_mtime` to the recorded value, re-rasterizes when
   newer, returns the number updated, and invalidates the below cache.

9. **`app/tile_renderer.py` — 256×256 tile compositor with dirty
   tracking.** `TileRenderer(stack, tile_size=256)` owns a `_full_canvas`
   PIL image and a `_tiles: dict[(tx, ty), _TileCache]` keyed by tile
   coords. `mark_dirty(rect)` translates a canvas-space rect into the
   set of overlapping tile coords via bit-pattern division;
   `mark_all_dirty()` re-queues every tile (size-aware via `cols` /
   `rows`); `invalidate()` drops everything. A per-tile
   `layer_signature` tuple records `(id, image-id, visible, opacity,
   blend_mode, offset, mask-id, mask_enabled, adjustment,
   adjustment_params)` so any structural change forces a full rebuild.
   `render()` re-blends only dirty tiles via `_render_tile(tx, ty)`,
   which iterates layers and calls `_blend_layer_onto_tile`: positioned
   image is cropped to the tile rect, `Image.alpha_composite` runs in
   Normal mode, the numpy blend kernel runs for non-Normal modes, and
   adjustment layers read base / mask / opacity through the tile-sized
   region. Output round-trips equal to `stack.composite()` (verified
   in-process).

10. **`app/gpu_renderer.py` — moderngl GPU compositor (opt-in).**
    `gpu_available()` gates on a soft `import moderngl`. `GpuRenderer`
    builds a standalone GL context, a fullscreen-quad VAO, two
    ping-pong RGBA8 framebuffers, and a single fragment program that
    branches on `u_mode` to cover all nine blend modes plus Porter-Duff
    "over" alpha math. Per-layer texture cache is keyed by
    `id(layer.image)`; mask layers upload a canvas-sized "L" texture
    and the shader multiplies `top.a` by `mask.r` when `u_use_mask =
    1`. Adjustment layers fall back to a CPU pass that reads the source
    FBO, runs `apply_adjustment`, and writes the result back into the
    destination texture with `texture.write` (cheap enough since
    adjustments are rare). `release()` drops every texture, FBO, VAO,
    program and the context itself. Verified against the CPU compositor
    — Multiply blend matches within `±1/255` quantization.

### Changed
- **`requirements.txt`** — added `moderngl>=5.10` (GPU compositor) and
  `numba>=0.59` (JIT blend kernel, was already a soft import) so the
  build venv installs both by default.
- **`build.bat`** — PyInstaller call now includes `--collect-all
  moderngl` and `--collect-all numba` so their runtime hooks and
  bundled DLLs ship in `_internal/`.

### Notes
- Pressure pipeline reads `ctx.pressure` first; brushes that ignore
  pressure (Hard Round, Pixel Pencil, etc.) are unaffected. Mouse-only
  strokes fall back to a velocity → pressure mapping inside each
  pressure-aware brush — no host plumbing required.
- Tile renderer and GPU renderer are independent of the legacy
  `LayerStack.composite()` path. They share the same blend math, masks,
  and adjustments, but the canvas hot path still calls `composite()`
  until a host wiring change opts in. Both engines are usable from
  scripts today.

## 2026-05-10 — Plugin Hot-Reload, Dark Palette, Numba Composite & Brush HUD

### Added
1. **`app/main_window.py` + `app/plugin_loader.py` — plugin hot-reload watcher.**
   `snapshot_plugin_files(plugins_dir)` walks `Plugins/**.py` recursively and
   returns `{path: (mtime, size)}` so package internals (helpers next to
   `tool.py`) also trigger reloads. `MainWindow` builds the baseline snapshot
   right after the deferred plugin init, then a 1 s `QTimer`
   (`_plugin_watch_timer` → `_poll_plugin_changes`) compares snapshots each
   tick; a two-tick debounce (`_plugin_pending_snapshot`) waits for the
   editor to finish a burst-save before firing `reload_plugins()`. The
   reload path drops the active tool if it came from a plugin, tears down
   plugin tools, brush tools (`_brush_tool_names`), and plugin docks
   (`_plugin_dock_titles`), calls `shutdown_plugins` + `purge_plugin_modules`
   to clear `sys.modules`, re-runs `load_plugins` + `load_brush_tools`, and
   reports `Reloaded: N plugin(s), M brush tool(s)` on the status bar.
   `_plugin_reload_in_progress` re-entrancy guard stops a tick mid-reload
   from kicking off another. The timer is stopped on `closeEvent`.

2. **`main.py` — modern dark Fusion palette + base QSS.**
   New `_apply_dark_palette(app)` installs a full dark `QPalette` (window
   `#1e1f22`, base `#18191c`, surface `#2b2d31`, border `#3c3f44`, text
   `#dcdddd`, dim text `#969798`, default highlight `#4a90e2`) plus
   disabled-state colors, then layers a stylesheet that themes `QToolTip`,
   `QMenu` / `QMenuBar`, `QStatusBar`, `QToolBar`, `QDockWidget::title`,
   `QSplitter::handle`, `QHeaderView::section`, `QTabBar::tab`, and
   `QScrollBar` (vertical + horizontal). Called right after the
   `QApplication` is built so child widgets inherit dark colors before any
   window paints. `_apply_accent` in `main_window` reads `app.palette()`
   and only overrides `Highlight`, so user-chosen accent colors layer on
   top of the dark base instead of replacing it.

3. **`app/blending.py` — fused numba JIT composite kernel.**
   `_composite_kernel(base, top, mode_id, opacity)` is a
   `@njit(cache=True, parallel=True, fastmath=True)` parallel kernel
   (`prange` over rows) that does blend + Porter-Duff "over" alpha
   compositing in one per-pixel pass, no intermediate HxWx4 allocations.
   `mode_id` (int) covers all nine modes — `0 Normal, 1 Multiply,
   2 Screen, 3 Overlay, 4 Darken, 5 Lighten, 6 Add, 7 Subtract,
   8 Difference` — with inline branch ladders, channel clamp to `[0, 1]`,
   and `out_a = src_a + ba * (1 - src_a)` Porter-Duff alpha. `composite()`
   prefers the kernel when `_HAS_NUMBA` is set and shapes match
   (`ascontiguousarray` float32 HxWx4), else falls through to the
   numpy path (`_composite_numpy`). Numba is a soft-import: install with
   `pip install numba` for 10x-50x speedup on big canvases, otherwise
   the numpy fallback runs untouched and `njit` / `prange` are stubbed
   so the kernel definition still parses.

4. **`app/ui/hud_picker.py` — floating on-canvas brush HUD.**
   `HudPicker(QFrame)` is a frameless `Qt.WindowType.Tool` panel with
   semi-opaque background (`rgba(36,38,42,235)`) that hosts three
   `SliderField` rows — Size (1–1024 px), Opacity (1–100 %), Hardness
   (0–100 %) — and primary / secondary color swatches that open
   `QColorDialog` with alpha. `_read` / `_write` thread values through
   the active `Tool` instance (`brush_size`, `brush_opacity`,
   `brush_hardness`) and fall back to `ToolContext` for legacy tools
   that still keep settings on the shared context. Color picks update
   the swatch QSS and call `color_panel.refresh()` so the sidebar stays
   in sync. `MainWindow._install_hud_picker` registers a `Shift+S`
   `QShortcut` with `ApplicationShortcut` context that calls
   `toggle_at_cursor`: anchors the HUD 16 px below/right of the cursor
   so it doesn't sit directly under the pointer, refreshes from current
   tool state on each open, hides on re-press.


## 2026-05-09 — MainWindow Controllers, Cross-Platform Fonts & Test Suite

### Added
1. **`app/controllers/` package — three controllers carved out of `MainWindow`.**
   `HistoryController` owns undo / redo / jump, `apply_snapshot`, history-panel
   sync, and the `commit(label)` entry point used by every edit path
   (`app/controllers/history_controller.py`). `SelectionController` owns
   `select_all`, `deselect`, `invert`, `transform`, `fill_with` /
   `fill_primary` / `fill_secondary`, `erase`, `crop_to_selection`, plus the
   `selection_or_full()` helper that lets copy/paste treat *no selection* as
   the whole canvas (`app/controllers/selection_controller.py`).
   `PasteController` owns `copy` / `cut` / `paste` / `paste_into_current`
   plus the three paste-exec variants (`paste_new_layer`,
   `paste_into_layer`, `paste_new_project`), the cursor-anchored radial
   menu, the internal copy buffer with source-project tag, and clipboard
   round-tripping (`app/controllers/paste_controller.py`).
   `MainWindow` instantiates `self.history_ctrl`, `self.selection_ctrl`,
   `self.paste_ctrl` and forwards Qt actions/signals through them; the
   public `commit_history` / `undo` / `redo` shims on the window stay so
   plugins keep working.

2. **`app/tools.py` — cross-platform font resolution.**
   New `resolve_font_path(family)` walks platform-standard font directories
   (`%WINDIR%\Fonts` + `%LOCALAPPDATA%\Microsoft\Windows\Fonts` on Windows,
   `/System/Library/Fonts` + `/Library/Fonts` + `~/Library/Fonts` on macOS,
   `/usr/share/fonts` + `/usr/local/share/fonts` + `~/.fonts` +
   `~/.local/share/fonts` on Linux), with `winreg` font-registration
   scanning kept on Windows for speed and renamed-file coverage. Indexes
   `.ttf` / `.otf` / `.ttc` / `.otc` by filename stem and a hyphen/space-
   stripped variant ("Helvetica-Bold" → also "helveticabold"), then falls
   back to stripping trailing style words ("Arial Bold" → "Arial"). Cache
   is built once on first call. Old Windows-only names
   `_build_windows_font_cache` and `_resolve_windows_font` remain as
   aliases so existing plugin imports keep resolving.

3. **`tests/` — pytest suite with 87 tests.**
   `test_blending.py` (20), `test_history.py` (13), `test_layer.py` (23),
   `test_image_ops.py` (12), `test_tool_loader.py` (9), and
   `test_font_resolver.py` (10) cover the pure-function blend math,
   history snapshot stack, layer/stack ops, place-on-canvas math,
   `_slug` + `tool_id` resolution (class attr / folder-derived /
   manifest override), and font lookup including hyphen-squashing,
   trailing-style stripping, OTF indexing, back-compat aliases, and
   non-font extension rejection. `tests/conftest.py` provides shared
   `solid_rgba` and `solid_arr` factories. `pytest.ini` pins
   `testpaths = tests` and `pythonpath = .`. `requirements-dev.txt`
   layers `pytest>=7.4` on top of the runtime requirements.

### Changed
4. **`Plugins/Brushes/Text/Text/tool.py` — import portable font lookup.**
   Now imports `resolve_font_path` from `app.tools` instead of the
   Windows-only `_resolve_windows_font` shim, so the Text tool resolves
   font families on macOS and Linux installs without falling back to
   Pillow's own search.

5. **`Plugins/Brushes/_shared.py` — re-exports `Tool` and `ToolContext`.**
   The shared bootstrap module now pulls `Tool`, `ToolContext`, and the
   stamp / brush-mask / walk helpers from `app.tools` and lists them in
   `__all__` so plugin `tool.py` files can `from _shared import Tool,
   ToolContext` instead of reaching into `app.tools` directly.

6. **`docs/PLUGIN_API.md` — refreshed plugin-author reference.**
   Updated table of contents, registration table for tools / filters /
   actions, and the minimal `GrayscalePlugin` example to match the
   current `PluginContext` surface and the per-tool-folder
   `Plugins/Brushes/<Group>/<ToolName>/tool.py` layout.

7. **`build.bat` — tighter source mirror + richer release payload.**
   The `Git Main` mirror now also excludes `session`, `.pytest_cache`,
   The `Release` copy now also ships `Create_tool_or_Brush.py` (the
   plugin-authoring cheat sheet) and the entire `docs/` folder
   (`PLUGIN_API.md`, etc.) alongside `Layered.exe`, `Plugins/`,
   `Icon.ico` / `Icon.png`, `README.md`, and `Changelog.md`.


## 2026-05-08 — Plugin Authoring Template, Tool Reorder & Preferences Dialog

### Added
1. **`Create_tool_or_Brush.py` — standalone tool/brush authoring reference.**
   New top-level cheat-sheet (700 lines) that documents every hook, helper,
   and convention available when writing a `Plugins/Brushes/<Group>/<Tool>/
   tool.py`. Covers the `Tool` base class (`name`, `group`, `role`, `icon`,
   `is_default`, `commit_on`, lifecycle hooks, pointer-event APIs,
   `build_ui`, `paint_overlay`, `commit`), the `ToolContext` surface
   (colours, modifier keys, `active_layer`, selection hooks, history hooks,
   hook registry, legacy compat shims), the `Plugins/Brushes/_shared.py`
   helpers (`_brush_mask`, `_stamp_color`, `_stamp_erase`, `_walk`,
   `_local_filter_stamp`, `_selection_at_layer`,
   `_clip_layer_to_selection`, `_ShapeTool`, `_SelectionToolBase`,
   `_shape_geom`, lazy Qt enum getters), the `tool.json` manifest, and the
   keyboard-shortcut registry. Includes ten runnable example classes —
   round soft brush, eraser, flood fill, filter brush, shape (`_ShapeTool`),
   marquee (`_SelectionToolBase`), popup-settings tool, multi-press sticker
   with hand-rolled `commit()`, picker with `on_pick` callback, and a
   stateful tool using `on_select`/`on_deselect`. The file lives at the
   project root (outside `Plugins/`) so the loader ignores it.

2. **Drag-drop tool reorder in the Tools dock.**
   `app/ui/tool_panel.py` adds a `tool_order_changed = pyqtSignal(list)`
   signal, a `set_tool_order(order)` method that reflows the grid (names
   not in `order` keep relative position and are appended), and an
   `open_reorder_dialog()` that pops a `QListWidget` in
   `InternalMove` drag-drop mode pre-filled with the current tool labels.
   A right-click `contextMenuEvent` on the panel exposes the dialog via a
   "Customize tool order..." action. The companion `remove_tool_button(name)`
   helper detaches a button from the `QButtonGroup`, drops its shortcut, and
   `deleteLater()`s both — used by hot-reload paths.

3. **Shape and line tool icons registered in `TOOL_ICONS`.**
   Triangle △, Star ★, Pentagon ⬠, Hexagon ⬡, Diamond ◇, Arrow ➤,
   Curve ∿, Dashed ┈ now have built-in glyphs in
   `app/ui/tool_panel.py:TOOL_ICONS`, matching the shape / line tools added
   on 2026-05-06 so they no longer rely on per-tool `tool.json` icon
   overrides.

4. **Category-menu actions show their keyboard shortcut.**
   `set_tool_categories` now calls `action.setShortcut(QKeySequence(sc))`
   on each dropdown entry whose tool is in `TOOL_SHORTCUTS`, so the popup
   menu of every split-button shows the Photoshop-style shortcut next to
   the tool name (`app/ui/tool_panel.py`).

### Changed
5. **`app/ui/prefs_dialog.py` — Preferences dialog with live accent
   preview and session restore.**
   Adds a `_ColorSwatch` `QPushButton` that opens `QColorDialog`, plus a
   live preview `QLabel` that re-tints itself and chooses white/black text
   per the `0.299 R + 0.587 G + 0.114 B` luminance threshold. A "Reset"
   button restores the default `#2196f3`. A "Restore open projects on
   startup" checkbox binds to `Preferences.restore_session`. The dialog
   uses a `QDialogButtonBox` with Ok / Cancel / Apply: Apply writes through
   and `prefs.save()`s, Ok applies + accepts, Cancel calls `_apply_fn` with
   the `_original_accent` captured at open so any live-preview tinting is
   reverted.

6. **`prefs.json` default schema.** Now stores `accent_color` (`"#2196f3"`)
   and `restore_session` (`false`) — the two fields the new dialog edits.


### Added
1. **Tool buttons now show an icon glyph + tooltip + keyboard shortcut.**
   `app/ui/tool_panel.py` gained a `TOOL_ICONS` map and a Photoshop-ish
   `TOOL_SHORTCUTS` map (B Brush, E Eraser, G Fill, V Move, M Marquee,
   L Lasso, W Magic Wand, T Text, I Picker, U Line, Shift+U Rectangle,
   Alt+U Ellipse, R Blur, Shift+R Sharpen, Alt+R Smudge, S Clone Stamp,
   Ctrl+T Transform, Ctrl+Shift+T Sel Transform). Each button is bigger
   (min height 30px), left-aligned, gets a hover hint, and the active
   tool is now highlighted via stylesheet (`#2a6ad6` background, bold
   white text, blue border) so the eye can pick it out at a glance.
   Shortcuts use `ApplicationShortcut` scope but skip activation while
   a `QLineEdit`, `QTextEdit`, `QPlainTextEdit`, `QAbstractSpinBox`, or
   editable `QComboBox` is focused so typing in the Text dock / spin
   boxes is not hijacked.

2. **`Tool.icon` class attribute + `tool.json` `"icon"` field.**
   `app/tools.py` adds `icon: str = ""` on the `Tool` base class.
   `app/tool_loader.py` reads `meta.get("icon")` from each `tool.json`
   and writes it onto the instantiated tool (manifest icon overrides
   class attr). `ToolPanel.set_tool_icon(name, icon)` is called from
   `main_window._deferred_plugin_init` and the hot-reload path before
   `add_tool_button` / `set_tool_categories`, so custom brushes can
   ship their own glyph instead of inheriting `TOOL_ICONS`. Both the
   primary split-button label and the dropdown menu actions render
   with the icon prefix; `_on_category_pick` keeps the label and
   tooltip in sync when the user picks a sub-tool.

3. **All built-in custom brushes declare an `icon`.**
   Spray 💨, Square Brush ▣, Scatter ✣, Fur 🦔, Splatter 💦, Weave ▦,
   Lightning ⚡, Kaleidoscope ❋, Constellation ✦.

### Changed
4. **`HOW_TO_ADD_TOOLS.md`** — documents the new `icon` attribute and
   `tool.json` `"icon"` manifest field, plus the keyboard-shortcut /
   tooltip behaviour for built-in tools.

## 2026-05-06 — Custom Tool Categories, Selection Undo & Rotation Fix

### Added
1. **`Plugins/Brushes/Shapes/` — five new shape tools.**
   Triangle, Star, Pentagon, Diamond, Hexagon — each drag-to-draw with
   resize/move handles inherited from `_ShapeTool`. Shift-drag locks
   proportions; Fill Shape toggle switches between filled and outline
   rendering. Tools are fully auto-discovered and appear under a
   **Shapes** split-button in the Tools dock.

2. **`Plugins/Brushes/Lines/` — three new line tools.**
   - **Arrow** — straight line with a proportionally scaled filled
     arrowhead at the release point.
   - **Curve** — quadratic Bezier: press sets the anchor, drag pulls the
     control point with a live preview, release commits the end point.
   - **Dashed Line** — dash and gap lengths scale with `brush_size`.

3. **`Plugins/Brushes/Custom Brushes/` — three new brush tools.**
   - **Spray** — airbrush effect; pixel density scales with opacity,
     radius scales with brush size, positions sampled via `_walk`.
   - **Square Brush** — hard square stamp along the stroke path using
     `alpha_composite`; spacing driven by `brush_spacing`.
   - **Scatter** — random-size dot splatter for grungy / textured strokes.

4. **`Plugins/Brushes/Custom Brushes/HOW_TO_ADD_TOOLS.md`** — drop-in
   authoring guide with a minimal `Tool` template and a full `_ShapeTool`
   subclass example. Anyone can copy a folder in and have a working tool
   on next launch — no registration code needed.

### Fixed
5. **Magic Wand undo / redo did not work.**
   `History.commit()` only snapshotted the layer stack; `proj.selection`
   was stored separately and never captured. `Snapshot` now carries an
   optional `selection` field. `History.commit()` accepts and deep-copies
   it; `_restore_at()` returns a cloned copy. `Project.commit()` passes
   `self.selection`. `_apply_snapshot_stack()` in `main_window.py` now
   receives the full `Snapshot` (not just `.stack`) and writes
   `snap.selection` back to `proj.selection`. `_on_undo`, `_on_redo`,
   and `_on_history_jump` updated accordingly
   (`app/history.py`, `app/project.py`, `app/main_window.py`).

6. **Transform rotation squashed the image into the original bbox.**
   During a rotate drag, `_apply()` was called with `self._cur_bbox`
   (which accumulated updates), causing each frame to re-rotate an
   already-rotated size. Fixed: rotation mode now always calls
   `_apply(layer, self._bbox0)` so every frame starts from the pristine
   pre-drag crop. Inside `_apply()`, when `_mode == "rotate"` the bbox
   is re-centered on the original bbox center and expanded to the AABB
   of the rotated image (`rw, rh = img.size` after `rotate(expand=True)`)
   so no content is clipped during the live preview. Pressing Enter
   applies the existing `_crop_layer_to_canvas()` clip, cutting anything
   that extends past the canvas edge (`Plugins/_builtin_tools.py`).

---

## 2026-05-05 — Plugin-Driven Tools & Settings UI

### Added
1. **Folder-based tool plugins under `Plugins/Brushes/<Group>/<Tool>/`.**
   Each `tool.py` exposes `TOOL_CLASS` and is auto-discovered by
   `app.tool_loader.load_tools` — no `Plugin` subclass, no
   `register_tool` call. Group folders become split-buttons in the Tools
   dock; sub-tools populate the dropdown
   (`app/tool_loader.py`, `app/main_window.py:_deferred_plugin_init`).

2. **`Tool.build_ui(parent, ctx)` mounts per-tool settings into the
   tool-settings toolbar.** A persistent host widget keeps the toolbar a
   fixed 40 px tall, so switching tools never reflows the main UI. The
   previous tool's widget is destroyed before the new one is built
   (`app/main_window.py:_mount_tool_settings`,
   `app/tools.py:Tool.build_ui`).

3. **Lifecycle hooks on the `Tool` base class.** New methods
   `on_select(ctx)`, `on_deselect(ctx)`, `on_mouse_down/drag/up(ctx,
   x, y)` make tools fully self-contained. Default `press`/`move`/
   `release` shims forward to the new hooks via `ctx.active_layer`,
   keeping existing tools working unchanged (`app/tools.py:Tool`).

4. **Magic Wand has its own popout settings UI.** A 110 px-wide
   "Tolerance" `QToolButton` opens a dropdown carrying the SliderField
   so the toolbar shape is constant. Slider drags update
   `ctx.fill_tolerance` immediately; `MagicWandTool.reapply()` is
   debounced by a 120 ms `QTimer` to stop the flood-fill scan from
   running on every pixel of slider travel
   (`Plugins/Brushes/Select/MagicWand/tool.py`).

### Changed
5. **`Plugins/builtin_tools.py` → `Plugins/_builtin_tools.py`.** The
   underscore prefix tells `app.plugin_loader` to skip the file, so it
   no longer double-registers the same tool classes that
   `Plugins/Brushes/<Group>/<Tool>/tool.py` wrappers expose. The 19
   bundled tools are still defined in `_builtin_tools.py` and pulled in
   by importlib from each wrapper.

6. **Default-tool selection now uses `Tool.is_default`, not emoji
   strings.** `_post_plugin_tools_loaded` walks `self.tools.values()`
   and activates the first tool with `is_default=True` (falling back to
   `BrushTool`, then any tool). Picker / Text wiring uses class-name
   checks (`type(tool).__name__ == "PickerTool"`) instead of looking up
   `"🎯 Picker"` / `"📝 Text"` by literal display name
   (`app/main_window.py`).

### Fixed
7. **`AttributeError: 'ToolContext' object has no attribute
   'brush_size'` on startup.** The legacy tool-state fields
   (`brush_size`, `brush_hardness`, `brush_opacity`, `brush_spacing`,
   `fill_tolerance`, `fill_shape`, `text`, `text_size`, `text_font`,
   `on_tolerance_changed`) were re-added to `ToolContext` as a
   compatibility shim while the legacy tools in `_builtin_tools.py`
   still read from shared context. Marked `DEPRECATED`; removable once
   every tool owns its own state through `build_ui()`
   (`app/tools.py:ToolContext`).

8. **`Plugins/Brushes/Select/Lasso/tool.py` failed to import.** The
   docstring contained a 0x97 byte (cp1252 em-dash) that broke UTF-8
   decoding. Re-encoded as UTF-8.

9. **`Tool` base class missing `__init__` broke `super().__init__(ctx)`
   calls in legacy tools.** Added
   `__init__(self, ctx: Optional[ToolContext] = None)` so both old-style
   `super().__init__(ctx)` and new-style `super().__init__()` work
   (`app/tools.py:Tool.__init__`).

10. **Tool-group split-button only had a dropdown when the group held
    more than one tool.** `set_tool_categories` now always attaches the
    dropdown menu, so single-tool groups still expose the popup affordance
    (`app/ui/tool_panel.py:set_tool_categories`).

---

## 2026-05-04 (round 37) — Tool Panel Overhaul & Cleanup

### Added
1. **One split-button per Brushes folder in the tools dock.** The tools
   panel now creates exactly one `QToolButton` per category folder inside
   `Brushes/` (e.g. Basic, Drawing, Selection, Transform, Effects,
   Picker). The button shows the currently active tool; clicking the
   arrow opens a dropdown to switch to any other tool in that folder.
   "Basic" is always pinned to the top of the list
   (`app/ui/tool_panel.py:set_tool_categories`).

2. **`ToolPanel.set_tool_categories` implemented.** The method was
   referenced in `main_window.py` but never existed, causing an
   `AttributeError` crash on every startup. It is now fully implemented,
   replacing all individual per-tool buttons with per-category
   split-buttons and wiring their dropdown items to `tool_selected`
   (`app/ui/tool_panel.py`).

### Changed
3. **All tools now appear in the panel — no more hidden preset-only
   tools.** The `_preset_only_tools` filter that was hiding Eraser,
   Blur, Sharpen, Smudge, and Clone Stamp from the tools dock has been
   removed. All tools are passed to the panel and exposed via their
   category's split-button dropdown (`app/main_window.py`).

4. **Emojis added to Marquee and Rectangle tools.** `▭ Marquee` is now
   `⬜ Marquee` and `▯ Rectangle` is now `🟦 Rectangle` across
   `build_default_tools`, `TOOL_SETTINGS`, and the corresponding
   `Brushes/` manifest files. Also fixed a stale `🌫️ Blur` key in
   `TOOL_SETTINGS` to match the actual tool name `😶‍🌫️ Blur`
   (`app/tools.py`, `app/ui/tool_panel.py`,
   `Brushes/Drawing/Rectangle/tool.json`,
   `Brushes/Selection/Marquee/tool.json`).

### Removed
5. **Glitch Brush, Symmetry Brush, and Light Brush removed from the
   tool panel.** The `register_tool` calls for these three plugin-added
   tools have been removed from their respective plugin files
   (`Plugins/Distortion/glitch_sorter.py`,
   `Plugins/Game Dev/infinite_pattern_lab.py`,
   `Plugins/Lighting/smart_lighting.py`). Their filters and actions are
   unaffected.

---

## 2026-05-04 (round 36) — Performance & Tool-Name Fixes

### Fixed
1. **Startup and shutdown are now near-instant.** Plugin loading
   (`load_plugins` / `importlib` module imports) is deferred to the
   first idle event-loop tick via `QTimer.singleShot(0, ...)` so the
   window paints before any plugin files are imported. On close, the
   window hides immediately and `save_session` + `shutdown_plugins`
   run in a background thread (joined with a 2 s timeout), eliminating
   the visible freeze while layer PNGs are written to disk
   (`app/main_window.py:__init__`, `_deferred_plugin_init`,
   `closeEvent`).

2. **Tool name `KeyError` crash on startup fixed.** All tool-name
   string literals in `main_window.py` (`"Brush"`, `"Text"`,
   `"Picker"`, `"Transform"`, `"Sel Transform"`, `"Magic Wand"`,
   `"Move"`) were updated to match the emoji-prefixed keys that
   `build_default_tools` actually registers (e.g. `"🖌️ Brush"`,
   `"📝 Text"`, `"🎯 Picker"`). The app previously crashed immediately
   with `KeyError: 'Brush'` (`app/main_window.py`).

## 2026-05-03 (round 35) — Bug Fixes

### Fixed
1. **Paste-to-new-layer now properly activates the new layer.** After 
   pasting (Ctrl+V → New Layer), the newly created layer is explicitly
   set as active via `proj.stack.set_active()` and the layer panel 
   refreshes before tool activation, ensuring the UI correctly shows 
   the new layer as active. Users can immediately draw or edit on the
   pasted layer (`app/main_window.py:_paste_new_layer`).

2. **Pasted content now maintains an active selection (Paint.NET-style 
   workflow).** Instead of clearing the selection after paste, a 
   selection is automatically created around the pasted content based 
   on its alpha channel. This matches Paint.NET's behavior and enables 
   the select→copy→paste→fill workflow. The selection allows users to 
   immediately fill, move, or modify the pasted area without the image 
   disappearing when using selection tools 
   (`app/main_window.py:_paste_new_layer`).

3. **Fill and move operations now work correctly on pasted layers.** By
   maintaining an active selection around pasted content (fix #2), fill
   (Alt+Backspace) and move operations work as expected. The selection
   defines the area to fill or move, matching the expected Paint.NET
   workflow (`app/main_window.py:_paste_new_layer`).

4. **Transform tool now properly cleans up state when switching tools.**
   Added `commit()` method to `TransformTool` that clears internal state
   (`_mode`, `_anchor`, `_bbox0`, `_cropped`, `_press_pt`, `_cur_bbox`)
   when the user switches to a different tool. This prevents stale 
   references and ensures smooth tool transitions (`app/tools.py`).

## 2026-05-03 (round 34) — 3 updates

### Added
1. **Plugin folder subfolder support.** `Plugins/` may now contain
   category folders (e.g. `Game Dev`, `Color`, `Lighting`, `Stylize`,
   `Distortion`, `Utility`, `ETC`). `.py` files inside such a folder
   register with that folder name as their default menu category, so
   filters/actions group under a submenu without each plugin having to
   declare `category=`. Nested folders join with " / ". Folders that
   contain `__init__.py` are still treated as plugin packages, not
   category buckets (`app/plugin_loader.py`).

### Fixed
2. **Ctrl+Z no longer recenters the canvas view.** `Canvas.set_layer_stack`
   now takes `reset_view: bool = True`; the undo/redo/history-jump path
   (`_apply_snapshot_stack`) passes `reset_view=False` so pan/zoom stay
   put across snapshot swaps. Project-tab switches keep the previous
   reset behavior (`app/canvas.py`, `app/main_window.py`).
3. **Text tool font selection actually applies the chosen family.**
   `TextTool._load_font` now resolves the Qt family name to the real
   `.ttf`/`.otf` via the Windows font registry
   (`HKLM`/`HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts`)
   instead of guessing `<family>.ttf`. Cached on first lookup; falls
   back to the previous filename guesses and PIL's default
   (`app/tools.py`).

## 2026-05-03 (round 33) — 4 updates

### Added
1. **Layer panel drag-and-drop reorder.** Dragging a row in the layer list
   reorders the stack live (UI rows are top-first, so the move is
   inverted into stack indices before applying via `LayerStack.move`).
   Internal-only drag/drop with single-selection guards keep the existing
   ▲/▼ buttons and click-to-activate behavior intact
   (`app/ui/layer_panel.py`).
2. **Move tool drags selected pixels when a selection is active.** Press
   inside (or anywhere on canvas while a selection is set) lifts the
   masked pixels off the active layer into a floating buffer; drag
   translates both the lifted pixels and the selection mask; release
   commits the new position via a "Move selection" history snapshot.
   With no selection, dragging still pans `layer.offset` as before.
   Removed the old `Move → Sel Transform` redirect since `MoveTool`
   handles selection lifting internally now (`app/tools.py`,
   `app/main_window.py`).
3. **Text tool: multi-line + per-click new layer + Tab-to-edit.**
   - Each canvas click commits the previous text layer and starts a new
     one at the click point (no more reusing the same layer across
     clicks).
   - `TextTool.rerender` uses `ImageDraw.multiline_text` so embedded
     newlines render as separate lines.
   - Text panel switched from `QLineEdit` to `QPlainTextEdit` with
     `setTabChangesFocus(True)` so Enter inserts a newline and Tab
     jumps focus instead of inserting whitespace.
   - Pressing Tab while the Text tool is active focuses the Text panel
     editor automatically; new layers also reset the editor and steal
     focus via `TextPanel.reset_for_new_layer()`. New `on_layer_created`
     and `on_layer_committed` hooks let the host wire panel sync and
     history labels (`app/tools.py`, `app/ui/text_panel.py`,
     `app/main_window.py`).

### Fixed
4. **Lag on Fill / Select-All.** Added `Selection.is_full` and a
   fast-path in `_selection_at_layer` / `_clip_layer_to_selection`:
   when the active selection covers the whole canvas and the layer
   exactly fills it, paint and clip ops skip the per-stamp /
   per-op selection composite entirely. `Selection.rect` and
   `Selection.from_mask` set the flag automatically when bounds match
   (`app/project.py`, `app/tools.py`).

## 2026-05-03 (round 32) — 1 update

### Fixed
1. **Fill / Line / Rectangle / Ellipse now clip to active selection.**
   Brought direct-draw tools in line with Brush, Eraser, Gradient, Blur,
   Sharpen, Smudge, and Clone Stamp — paint outside the selection mask
   is reverted from a pre-op snapshot. New `_clip_layer_to_selection`
   helper composites `layer.image` against the snapshot through the
   selection mask. Applied in `FillTool.press`, `LineTool.move`, and
   `_ShapeTool._render` (`app/tools.py`).

## 2026-05-03 (round 31) — 3 updates

### Added
1. **Magic Wand "select open area".** Clicking a fully transparent pixel
   now flood-fills the connected empty region instead of clearing the
   selection. `MagicWandTool.press` no longer early-returns on alpha=0;
   the existing transparent-target branch in `_sample_and_commit`
   handles flood + Ctrl-select-similar across the whole layer
   (`app/tools.py`).

### Fixed
2. **`Setting.__init__` now tolerates unknown kwargs.** When a plugin is
   hot-reloaded against a stale cached `app.plugin_api` module, new
   `Setting` fields (e.g. `rows`, `monospace`) no longer crash plugin
   registration with `TypeError: unexpected keyword argument`. Unknown
   kwargs are stripped and a warning recommends an app restart
   (`app/plugin_api.py`).

### Verified
3. **Session save/load on close/open already wired.** `save_session` is
   called from `MainWindow.closeEvent`; `load_session` runs in
   `__init__`. Layers, blend modes, opacity, visibility, offsets, and
   active index round-trip via `session/proj_NNN/`
   (`app/session.py`, `app/main_window.py:117,2141`).

## 2026-05-02 (round 30) — 6 updates

### Added
1. **Filters / Plugins menus support submenus.** `register_filter` and
   `register_action` accept a new `category=` kwarg; entries with the
   same category collapse into a shared submenu. Built-in plugins are
   pre-grouped: **Color** (Grayscale, Invert, Brightness/Contrast,
   Posterize, Gradient Map, Color Replace), **Effects** (Outline,
   Sharpen, Glow/Bloom, Drop Shadow), **Generators** (Make Tileable,
   Normal Map, Pixel Art Resize, Remove Background), **Utilities**
   (Flip H/V, Crop to Center, Toggle Grid). Failed plugins are now
   hidden from the menu (still in the plugin log + `MainWindow.plugins`)
   so users only see actionable entries
   (`app/plugin_loader.py`, `app/main_window.py:_populate_plugin_menu`,
   `docs/PLUGIN_API.md`).

### Fixed
2. **Delete / Backspace now erases the selected pixels.**
   `MainWindow.keyPressEvent` routes `Key_Delete` / `Key_Backspace` to
   a new `_erase_selection()` that zeroes alpha under the selection
   mask (offset-aware) and snapshots history as "Erase selection".
3. **Enter wasn't applying the post-paste transform when focus stayed
   on a side panel.** `_activate_transform_tool` now calls
   `self.canvas.setFocus()` so Return immediately bubbles to
   `MainWindow.keyPressEvent` and `_confirm_selection` flushes the
   transform.
4. **Move tool grabbed the whole layer when a selection was active.**
   `_on_tool_selected("Move")` now redirects to "Sel Transform" while a
   selection exists, so the lifted pixels translate with the cursor
   instead of dragging the entire layer offset.
5. **Brush / eraser painted at the wrong spot on layers with a
   non-zero offset (e.g. clipboard pastes).** `_stamp_color` and
   `_stamp_erase` now translate the canvas-space cursor into
   layer-image space via `layer.offset` before compositing
   (`app/tools.py`).

### Docs
6. **`docs/PLUGIN_API.md` updated for category submenus and the
   hidden-failed-plugins behavior.** New filter example shows
   `category="Color"`; sandbox section explains where to find load
   failures now that they no longer appear in the menu.

## 2026-05-02 (round 29) — 2 updates

### Fixed
1. **Scroll wheel zoomed instead of panning vertically.** `Canvas.wheelEvent`
   now treats unmodified scroll as vertical pan and reserves zoom for
   `Ctrl+scroll`. `Shift+scroll` still pans horizontally
   (`app/canvas.py:wheelEvent`).
2. **Right-click did nothing on the canvas.** `Canvas` mouse handlers now
   accept right-button presses, swap `ToolContext.primary_color` with
   `secondary_color` for the duration of the stroke, and restore them on
   release — so right-drag paints/fills/draws shapes with color 2
   (`app/canvas.py:mousePressEvent`, `mouseReleaseEvent`,
   `_swap_tool_colors`).

## 2026-05-02 (round 28) — 9 updates

### Fixed
1. **Magic wand "copies invisible pixels".** Sample now uses RGB-only
   tolerance and skips fully-transparent (`alpha == 0`) pixels when the
   user clicked a visible pixel; clicking a transparent pixel matches
   only other transparent pixels. Stops the wand from selecting the
   "empty" canvas just because its RGB happened to fall within the
   tolerance band of the clicked color (`app/tools.py:_sample_and_commit`).
2. **Magic wand re-click destroyed prior selection on tolerance retune.**
   `MagicWandTool` now stores the last sample point as a seed
   (`(layer, lx, ly, ctrl_mode)`). A new `reapply()` method re-runs the
   flood from that seed using the current `fill_tolerance`, so editing
   the tolerance slider/spin updates the same selection live instead of
   forcing the user to re-click and accidentally replace the selection
   with an empty mask.
3. **Tolerance changes propagate to the wand live.** `ToolContext`
   gained an `on_tolerance_changed` hook; `ToolPanel._on_tolerance` now
   invokes it after writing `ctx.fill_tolerance`. `MainWindow` wires it
   to a `_tolerance_live_update` that calls `MagicWand.reapply()` so
   the canvas refreshes the moment the slider moves.
4. **Enter/Return wasn't confirming an in-progress transform after the
   user typed in the tolerance / size spinbox.** The spinbox kept
   keyboard focus and consumed Return before it could bubble up to
   `MainWindow.keyPressEvent`. `Canvas` now sets
   `Qt.FocusPolicy.ClickFocus`, so clicking the canvas pulls focus off
   the spinbox and Enter cleanly hits `_confirm_selection`.
5. **Pasted images dropped at the canvas top-left corner.** All three
   `_paste_new_layer` modes now center: *anchor* sets `offset` to
   `((cw-iw)//2, (ch-ih)//2)`; *extend* writes the image at
   `((new_w-iw)//2, (new_h-ih)//2)` in the (possibly enlarged) buffer;
   *crop* draws from the source's center into the destination's center
   so the visually important middle survives both sides of the clip.
6. **Zoom-in lag.** `Canvas.paintEvent`'s checkerboard background
   iterated the full target rect, so zooming ~10× on a 2k canvas ran
   ~1.5M `fillRect` calls per repaint. Iteration now clips to
   `target ∩ widget.rect()` while snapping the start cell to the
   original grid so colour parity stays consistent across pans.

### Added
7. **Translucent selection highlight.** `Canvas.paintEvent` now paints
   a semi-transparent blue fill over the selection mask before drawing
   the marching ants, so a selected region is obvious at a glance even
   when the dashed outline is small or far away. Highlight pixmap is
   cached per `(id(mask), size)` so it costs nothing across pans/zooms
   while the selection is stationary (`_paint_selection_highlight`).
8. **`SliderField` widget.** New shared
   `app/ui/slider_field.py` packs a `QSlider` + `QSpinBox` into one
   widget exposing the QSlider API (`valueChanged`, `value`,
   `setValue`, `setRange`, `blockSignals`). Users can drag *or* type a
   value; the two stay in sync. Replaced every standalone slider in
   `tool_panel.py` (hardness / opacity / spacing / tolerance — both the
   panel layout and the toolbar layout), `layer_panel.py` (layer
   opacity), and `color_panel.py` (HSV value). Old per-slider
   `*_label` widgets are gone — the spinbox doubles as the live value
   readout.
9. **Live filter preview.** `PluginSettingsDialog` now accepts an
   optional `preview_callback(values)`; every settings widget's change
   signal triggers the callback (debounced 80 ms via `QTimer`). Default
   parameters are previewed once on dialog open. `MainWindow._invoke_filter`
   snapshots the original layer image, supplies a callback that re-runs
   the filter on a copy and refreshes the canvas, then either applies
   the chosen settings (Accept) or restores the snapshot (Cancel).
   Errors during preview are swallowed so the dialog stays usable; the
   final apply still surfaces failures through the existing error path.

### Changed
- **`Edit → Invert Selection` shortcut moved from `Ctrl+Shift+I` to
  `Ctrl+I`** so it matches the user's expected single-modifier binding.

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
