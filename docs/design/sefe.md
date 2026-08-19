# Design: SeFE — the Seahorse File Explorer

*Status: charting (2026-08-19) · Scope: HeDE's native file manager — the app,
its architecture, behaviour contract, and interop seams · **Supersedes** the
"adopt pcmanfm-qt" line for the file manager in [desktop-environment.md](desktop-environment.md)
· Depends on: `helm-appearance` + `helm-common` (theming/config), the Customs
MIME layer (open dispatch) · Relates to: [hede-familiarity.md](hede-familiarity.md)
(the behaviour contract), [hede-windows-interop.md](hede-windows-interop.md)
(the interop hooks), [hede-theme.md](hede-theme.md) (the look)*

> **SeFE** (Seahorse File Explorer — styled like GeST) is an Explorer-familiar
> file manager that **is** HeDE: Windows muscle-memory by default, re-tinted by
> the active biome, and wired into the ship's interop — double-click an `.exe`
> and it runs in Drydock; share a folder and it appears in the RDP session.

## The decision: build, not adopt

[desktop-environment.md](desktop-environment.md) named the file manager
**Seahorse** but set the strategy to **adopt** `pcmanfm-qt`, to "build later only
if it becomes an identity piece." It has become one. Three things make it
identity, not furniture:

1. **It carries the familiarity promise.** The file manager is where a Windows
   switcher's muscle memory is most exercised (address bar, double-click,
   `F2`/`Del`/`F5`). [hede-familiarity.md](hede-familiarity.md) already writes
   those as hard acceptance criteria — easier to *own* than to bend pcmanfm-qt to.
2. **It is the interop surface.** [hede-windows-interop.md](hede-windows-interop.md)
   routes "run this `.exe` in Drydock" and "share this folder to the session"
   *through the file manager*. That is a native integration, not a config knob.
3. **It re-tints with the biome.** A HeDE app gets the world's look for two lines
   of `main()`; a foreign app does not.

`pcmanfm-qt` remains the **fallback** if native slips — nothing here removes the
option, it just stops being the default plan. This doc is the authority; the
table in desktop-environment.md is annotated to point here.

## What it is — the layout (Windows-familiar first)

Explorer's frame, in the order a Windows user reaches for it
([hede-familiarity.md](hede-familiarity.md) §"File manager"):

- **Left Places pane** — Home, Desktop, Documents / Downloads / Pictures / …,
  mounted drives, Trash. Drives are static for v1; a later slice can source them
  from `gest/core/disk` (mounts/`fstab`).
- **Address bar** — a **breadcrumb** by default that clicks into a **typeable
  path field** (Windows behaviour: both, breadcrumb-first).
- **Main view** — **details** (Name / Size / Type / Modified, sortable columns)
  with a large-icons toggle. **Double-click opens, single-click selects** — the
  Windows default, explicitly *not* KDE single-click-open.
- **Toolbar + status bar**, a menu bar, and per-item + background context menus.

## Architecture

- **Qt6 Widgets, C++20** — matches all of HeDE (no QML anywhere). SeFE is the
  **first ordinary xdg-toplevel window** in the tree; every existing hede binary
  (`helm-panel`/`menu`/`bg`/`notify`) is a `wlr-layer-shell` surface. So SeFE
  *defines* the plain-window pattern. Closest template is `hede/src/panel/main.cpp`
  minus the layer-shell lines: `QApplication` → `setApplicationName` /
  `setDesktopFileName` → theming → `QMainWindow::show()`.
- **Model/view**: `QFileSystemModel` as the backing model; a `QTreeView` for
  Places and a `QTreeView` (details) / `QListView` (icons) for the main view over
  a shared `QItemSelectionModel`. There is no file-model code in the repo today —
  this is introduced fresh.
- **Home & build**: lives at `hede/src/sefe/`, binary **`sefe`** (its own
  identity, like `gest` — not the `helm-` shell prefix). `qt_add_executable(sefe …)`,
  links `Qt6::Widgets helm-appearance helm-common`, installs to `…/bin`. Can be
  split to its own repo later if it grows; in-tree keeps v1 simple and themed.

## Behaviour contract (hard requirements)

From [hede-familiarity.md](hede-familiarity.md) §47–56, treated as acceptance
criteria for the operations slice:

| Input | Action |
|---|---|
| Double-click | Open (file → default handler; folder → navigate) |
| Single-click | Select |
| `F2` | Rename in place |
| `Del` | Move to Trash |
| `F5` | Refresh |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / Cut / Paste |
| `Alt+F4` | Close window |
| Type in address bar | Navigate to path |

## Interop — the part that makes it HeDE

- **Open dispatch through Customs.** Reuse the GeST core: `gest/core/customs/mime.py`
  (`xdg-mime` default/query, `MimeType=`), `desktop.py` (write/parse `.desktop`,
  strip Exec field codes), `icons.py` (icon-theme resolution). The C++ read/launch
  side reuses `hede/src/apps/desktopentry.*` (`parseDesktopEntry`, `commandArgv`,
  `scanDesktopEntries`) for the "Open with" chooser and icon lookup.
- **Windows files → Drydock.** Double-clicking `.exe` / `.msi` / `.lnk` goes
  through the Customs MIME handler to **"Run in Drydock"**
  ([hede-windows-interop.md](hede-windows-interop.md)).
- **Folder → session.** A "Share this folder to the session" action wires RDP
  folder redirection (same doc).
- Child processes launch via `helm::launchDetached()` (`hede/src/common/launch.h`)
  so the decoration env is correct.

## Theming

Two calls in `main()` — `helm::applyAppearance()` then `helm::watchAppearance()`
(include `appearance/palette.h`, link `helm-appearance`) — and SeFE picks up the
Fusion palette + shell stylesheet and **re-tints live** when the biome/accent
changes (`QFileSystemWatcher` on `hede.conf`). Window decoration is **labwc SSD**:
the app drops Qt CSD (`QT_WAYLAND_DISABLE_WINDOWDECORATION=1`, already exported by
the session and per-child by `launchDetached`), and labwc draws the Helm titlebar.
Opt-in painterly CSD via the `helm-decoration` nine-patch plugin is a later polish.

## Packaging

- `install(TARGETS sefe RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)`.
- Ship **`share/applications/sefe.desktop`** (`Name=Seahorse`,
  `Exec=sefe %U`, `MimeType=inode/directory;`). hede ships no per-app `.desktop`
  today, so this **establishes** that convention; `helm-menu` auto-discovers it via
  `scanDesktopEntries(defaultApplicationDirs())`.
- Register SeFE as the `inode/directory` default (`xdg-mime default`) so folders —
  including "Open containing folder" from other apps — land in SeFE.

## Phasing (slices)

1. **Hull** — the `sefe` target + a themed window skeleton + `sefe.desktop`; opens
   Home read-only. (Establishes the xdg-toplevel + theming pattern.)
2. **Navigation** — Places pane, breadcrumb/typeable address bar, details + icons
   views, open/select semantics.
3. **Operations** — copy / cut / paste, move, rename, delete-to-Trash, new folder,
   properties — the full keyboard contract above.
4. **Interop** — Customs "Open with" + icons; `.exe` → Drydock; folder → session
   share.
5. **Polish** — thumbnails, column sort/config, richer context menus, opt-in
   painterly CSD.

## Non-goals (v1)

Tabs, dual-pane, an embedded terminal (that's **Porthole**), archive browsing
(that's **Hold**), network/SMB shares, and a privileged path for editing
system-owned directories (v1 is user-space file operations only). The system-wide
open/save dialog stays the adopted **xdg-desktop-portal** file chooser — separate
from the SeFE app.
