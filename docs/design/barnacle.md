# Design: Barnacle — the HeDE panel editor

*Status: charting (2026-08-24) · Scope: how a user reshapes the HeDE panel — the
tool, where it lives, and the config seam that makes edits stick · Depends on:
`helm-common` (config), `helm-appearance` (theming), `helm-apps` (applet/launcher
discovery) · Relates to: [desktop-environment.md](desktop-environment.md) (names
"Panel Layout" as a Control Center module), [sefe.md](sefe.md) (the standalone
themed-app scaffold this copies), [hede-familiarity.md](hede-familiarity.md)
(familiarity-as-scaffold north-star)*

> **Barnacle** is how you rearrange the ship's rail. It is *not* a settings page
> that edits an abstraction of the panel — it drops the **live bar** into an edit
> mode where you grab applets, drag to reorder, add from a drawer, and drag-off to
> remove. Windows makes you *leave* the taskbar to configure it; Barnacle lets you
> edit the bar itself. The lore: a barnacle is the thing that clings to the edge of
> the hull and lives off what sails past — exactly what a panel is.

## The decision: one engine, two doors

There were two competing framings for where the editor lives:

- **A — on the bar.** Right-click the panel → "Edit panel" → direct manipulation
  in place. This is the *transvaluation* move: Windows sends you to a Settings page
  to edit an abstraction; editing the bar in situ is WYSIWYG, no translation layer.
  It is the purest reading of "settings live in the thing they configure" — the
  panel's config lives *in the panel*. Cost: discoverability (right-click-to-edit is a power-user
  gesture) and the harder build (mutating a live `wlr-layer-shell` surface).
- **B — in the Control Center.** A "Panel Layout" module in `gest-settings` that
  writes config through a form. This is the **Windows-familiar default** (right-click
  taskbar → "Taskbar settings" opens the Settings app), it is discoverable, and
  [desktop-environment.md](desktop-environment.md) already reserves the module.
  Cost: it is *taxidermy risk* — an abstract form editing a thing you can't see
  while you edit it — and it depends on the gated Qt frontend.

**They only compete if the editing *engine* must live in one place. It doesn't.**

The decision: **the editing experience is in-place direct manipulation (A); the
Control Center module is a thin doorway into it (B).** The doorway does not
reimplement the editor — its button flips the live bar into edit mode (or embeds
the same view). Both write the same `hede.conf [panel]` surface, so the bar, the
Control Center, and hand-editing never disagree.

This satisfies both house north-stars at once: a **Windows-familiar entry** (right-click
→ settings, or Control Center → Panel Layout), that then drops you **somewhere
Windows can't go** — editing the bar itself. Familiarity is the scaffold, not the
destination ([hede-familiarity.md](hede-familiarity.md)).

The split maps cleanly onto the standard HeDE lib/exe scaffold: a pure
**`barnacle-lib`** (config read/write + the layout model, unit-testable) and a
themed **`helm-barnacle`** Widgets front-end. The Control Center module, when
`gest-settings` matures, re-exposes the *same* `hede.conf` logic — no format
change, no re-work, because the doorway was never the engine.

## The load-bearing problem: the panel doesn't listen yet

Today the applet set and order are **compiled into** the bar. `panel.cpp:38-74`
hard-codes a `QHBoxLayout`: Start (`⎈ Apps`) → `TaskbarWidget` (stretch) →
`MprisApplet` → `UpdatePill`/`NetworkPill`/`BatteryPill` (one shared `CoreClient`)
→ `BrightnessApplet`/`VolumeApplet`/`DndToggle` → `TrayWidget` → `Clock`. The only
panel key read is `[panel] height` (`config.cpp`, `Config::panelHeight()`,
default 46).

So the real engineering is **not** the editor UI — it is teaching `helm-panel` to
obey a config. Until the bar reads a layout, Barnacle is the tragedy of the jester:
it can gesture all it likes and the ship never notices. Three pieces:

1. **Schema** — extend `hede/src/common/config.{h,cpp}` beyond `panelHeight()` with
   an **ordered applet list** plus edge/position, e.g.

   ```ini
   [panel]
   height = 46
   edge = bottom          ; bottom | top (v1); left/right later
   applets = launcher, taskbar*, mpris, update, network, battery, \
             brightness, volume, dnd, tray, clock
   ```

   `taskbar*` marks the stretch/fill child (the `, 1` stretch arg in `panel.cpp:57`).
   Unknown tokens are skipped with a warning, not fatal — forward-compatible.
2. **A registry** — the hard-coded `new XWidget(this)` calls become a
   **name → factory** map (`"clock" → …`, `"tray" → …`, `"update"/"network"/"battery"
   → CoreClient-backed`). `panel.cpp` iterates `applets` and instantiates in order.
   The shared `CoreClient` (`panel.cpp:62`) is constructed once and injected into any
   pill the list requests.
3. **Live reload** — `helm-panel` watches `hede.conf` (`QFileSystemWatcher`, the
   idiom `sefe`/appearance already use via `helm::watchAppearance()`) and rebuilds
   its layout in place when `[panel]` changes, so Barnacle's writes apply without a
   restart. This is what makes in-place editing feel live.

Only piece 3's watcher is new plumbing; 1 and 2 are refactors of existing code and
are worth doing on their own merit (they make the bar configurable at all).

## Architecture

- **Qt6 Widgets, C++20**, matching all of HeDE (no QML). `helm-barnacle` is an
  ordinary window; the `sefe` scaffold ([sefe.md](sefe.md) §Architecture) is the
  template — `QApplication` → `setApplicationName`/`setDesktopFileName` →
  `helm::applyAppearance()` + `helm::watchAppearance()` → show.
- **Home & build**: `hede/src/barnacle/`, split like `hede/src/sefe/` into a
  `barnacle-lib` static lib (Core-only: parse/serialize `[panel]`, the layout model,
  the applet catalog) + a `helm-barnacle` executable linking
  `Qt6::Widgets helm-common helm-appearance helm-apps`. Binary name **`helm-barnacle`**
  follows the `helm-*` shell-tool convention (it is a shell utility, not a
  standalone end-user app like `sefe`).
- **`barnacle-lib` is the shared engine.** Both the bar's edit mode and the future
  Control Center module consume it. It knows the *catalog* of available applets
  (built-ins by name; later, `helm-apps` `.desktop` launchers to pin) and the
  read/write of `hede.conf [panel]`. It has no Qt-Widgets dependency so it unit-tests
  like `sefe-lib`/`config`.
- **Two front-ends over one lib:**
  - *Edit mode on the bar* — `helm-panel` enters an editing state (grab-handles,
    a "+" add-drawer, drag-off-to-remove). Reordering mutates the model →
    `barnacle-lib` writes `[panel]` → the watcher (piece 3) re-lays the bar. v1 may
    ship this as a compact popup/overlay rather than fully draggable chrome if
    live-surface DnD proves heavy — the model and config are identical either way.
  - *Control Center doorway* — a `panel.py` module under `gest/qt/modules/`
    registered in `gest/qt/registry.py` (mirrors `appearance.py`), whose primary
    action opens/flips the bar into edit mode. Built only when `gest-settings`
    matures; not a v1 blocker.

## Packaging

- `hede/CMakeLists.txt` — add `add_subdirectory(src/barnacle)` (beside the `sefe`
  line); if it ships a launcher, add `barnacle.desktop` to the
  `install(FILES data/applications/…)` block.
- New `hede/src/barnacle/CMakeLists.txt` — copy `hede/src/sefe/CMakeLists.txt`.
- `hede/tests/` — `test_barnacle.cpp` (round-trip parse/serialize of `[panel]`,
  registry resolution, unknown-token tolerance) wired in `hede/tests/CMakeLists.txt`,
  mirroring `test_sefe.cpp`/`test_config.cpp`.
- `hede/packaging/hede-9999.ebuild` installs via `cmake_src_install` — likely no
  change.

## Phasing (slices)

1. **Make the bar listen** — schema (`config.*`) + applet registry + iterate
   `[panel] applets` in `panel.cpp`; keep the current lineup as the built-in
   default so behaviour is unchanged when the key is absent. *No editor yet* — this
   is the load-bearing refactor and ships value alone (a hand-editable panel).
2. **Live reload** — `helm-panel` watches `hede.conf` and rebuilds in place.
3. **`barnacle-lib`** — extract the layout model + catalog + read/write into the
   testable lib; `test_barnacle.cpp`.
4. **Edit mode on the bar** — `helm-barnacle` / the in-place reorder+add+remove
   experience, writing through `barnacle-lib`. The delightful core.
5. **Control Center doorway** — `panel.py` module in `gest-settings` that opens
   edit mode. Deferred until the Qt frontend is ready.

## Non-goals (v1)

Free-floating/multi-monitor panels, multiple panels, per-applet deep settings
panes (an applet configures itself; Barnacle arranges *which* and *where*),
left/right vertical edges (bottom/top first), and third-party/scriptable applets
(the catalog is HeDE's built-ins plus pinned `.desktop` launchers). Barnacle
arranges the rail; it does not reinvent what each applet does.
