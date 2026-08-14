# Spec: HeDE Phase 1 — the daily-drivable shell

*Status: spec · Scope: turn the Phase 0 skeleton into a shell someone can use all day — a **launcher**, a **window-list taskbar**, a **system-tray host**, a **notification daemon**, and a **wallpaper** · Depends on: [hede-phase0](hede-phase0.md) (the panel + session + layer-shell + smoke harness), [desktop-environment](desktop-environment.md) (§5–§6) · Defers: anything reading `gest/core` (Phase 2), theming, quick-settings, the graphical greeter/lock · Milestone: log in, launch apps from a searchable menu, see and raise open windows from the taskbar, get notifications, on a wallpaper*

## 0. Goal

Phase 0 proved the frame stands. Phase 1 hangs the everyday components on it, each
a small process the session supervises, each still **shell-only** (no `core` yet).
After Phase 1, HeDE is a real (if plain) desktop you could live in.

## 1. Components & delivery order

Ordered by self-containment / testability — build top-down:

1. **`helm-menu` — the launcher (Start menu).** *[done]* Reads freedesktop
   `.desktop` files from the XDG dirs, searchable, launches apps. Pure core
   (parse/scan/filter/argv) → fully unit-tested; a layer-shell popup UI. Opened
   by the panel's Start button.
2. **Window-list taskbar.** *[done]* A panel applet (`src/taskbar`) over
   `wlr-foreign-toplevel-management-v1` (vendored XML → `qtwaylandscanner` +
   `QWaylandClientExtension`): one button per open toplevel, left-click
   activates or minimizes (if already active), middle-click closes, active
   window shown checked. Pure `Toplevel` model (upsert/remove/label) unit-tested;
   the Wayland glue is thin. Fills the stretch the panel reserved.
3. **`helm-notifyd` — notifications.** A `org.freedesktop.Notifications` D-Bus
   service rendering bottom-right toasts + a small history. Model (queue/urgency)
   unit-tested; toasts are layer-shell surfaces.
4. **System-tray host.** A `StatusNotifierItem` / `org.kde.StatusNotifierWatcher`
   host applet in the panel (adopt the `StatusNotifier` D-Bus contract).
5. **`helm-bg` — wallpaper.** *[done]* A `background`-layer surface per output
   (exclusive-zone −1, under panels), solid colour or an image with fit modes
   (fill/fit/stretch/center/tile). Pure geometry (`parseFit`,
   `computeImageTarget`) + config loading unit-tested. Slideshow deferred.

## 2. This increment — `helm-menu`

- **Core (`src/apps`, pure, tested):**
  - `DesktopEntry` — name, exec, icon, comment, type, noDisplay/hidden/terminal.
  - `parseDesktopEntry(text)` — the `[Desktop Entry]` group only; ignores
    locale-suffixed keys (`Name[fr]`).
  - `scanDesktopEntries(dirs)` — globs `applications/*.desktop` across
    `$XDG_DATA_HOME` + `$XDG_DATA_DIRS`, keeps `Type=Application`, drops
    `NoDisplay`/`Hidden`/empty, dedupes by desktop-file id (first wins).
  - `filterEntries(entries, query)` — case-insensitive over name/comment/exec,
    name-sorted; empty query → all.
  - `commandArgv(entry)` — strips Exec field codes (`%f %u %U %i %c …`, `%%`→`%`)
    and splits to argv.
- **UI (`src/menu`):** a layer-shell **Overlay** surface anchored bottom-left
  above the panel — a search field + results list (icons via `QIcon::fromTheme`),
  type-to-filter, ↑/↓ to move, Enter/click to launch, Esc to close. Launches via
  `QProcess::startDetached` and quits.
- **Panel wiring:** the left button becomes **Start** (opens `helm-menu`);
  Terminal moves into the menu (still on `Super+Return` in labwc).
- **Shared:** the layer-shell setup is factored into `src/wayland`
  (`applyLayerShell` + an `edges()` helper) — reused by panel, menu, and every
  later surface (toasts, wallpaper, lock).

## 3. Testing

- **Pure core** (the `apps` library): parse (fields, locale keys, field-code
  stripping), scan over a `QTemporaryDir` fixture (NoDisplay/Hidden/non-Application
  excluded, dedup), filter (case-insensitivity, empty query). No compositor.
- **Menu UI**: model/view split — the list model is `filterEntries` output, tested
  headless; the widget just renders it.
- **Smoke**: the Phase 0 headless harness extends to assert `helm-menu` also binds
  a layer-shell surface (later).

## 4. Non-goals (Phase 1)

- Any `gest/core` data (battery/network/updates/tray-from-core) — Phase 2.
- Single-instance menu toggle, pinned/favourites/recents, categories tree — the
  first cut spawns a fresh menu per click and lists all apps flat.
- Theming, quick-settings, greeter/lock. Multi-monitor beyond "wallpaper per
  output."
