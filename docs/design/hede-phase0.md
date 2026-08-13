# Spec: HeDE Phase 0 — "Hello Wayland"

*Status: spec · Scope: the HeDE skeleton — `helm-session` brings up **labwc** with a minimal `helm-panel` (a clock + a button that opens a terminal), launchable from a `greetd` session entry · Depends on: [desktop-environment](desktop-environment.md) (§5 components, §10 login, §12 roadmap) · Defers: everything touching `core`/GeST, plus tray, launcher, window list, notifications, wallpaper, `helm-greeter`/`helm-lock`, theming, QML · Milestone: log in → a bottom panel with a live clock and a Terminal button appears on labwc → open a terminal → log out cleanly*

## 0. Definition of done

One sentence: **you pick "HeDE" at the login greeter, land on a labwc desktop
with a bar across the bottom showing the time and a Terminal button, click it, a
terminal opens, and logging out returns you to the greeter — with nothing from
`gest/core` involved yet.**

Phase 0 is a *skeleton*, deliberately. It exists to prove the plumbing (session
bring-up, layer-shell, the greetd session entry, QtWidgets-on-Wayland) end to
end, so every later phase is adding a component to a frame that already stands —
not debugging the frame.

## 1. What Phase 0 proves — and what it doesn't

**Proves:**
- **The session entry.** `greetd` (with its stock text greeter) can launch a
  `wayland-sessions/*.desktop` that runs `helm-session`, and a full session
  starts and stops cleanly. (The *graphical* greeter, `helm-greeter`, is Phase 3;
  Phase 0 rides greetd's built-in `agreety`/`tuigreet`.)
- **The compositor seam.** labwc runs, windows stack/move/focus, and HeDE ships
  labwc a default config it actually reads.
- **Layer-shell in Qt.** `helm-panel` is a QtWidgets app that binds a
  `wlr-layer-shell` surface via `layer-shell-qt`, anchors to the bottom, and
  reserves an exclusive zone so maximized windows don't cover it.
- **The supervisor pattern.** `helm-session` sets the session environment, execs
  the compositor, and the panel comes up under it; session end tears down cleanly.
- **The weight thesis, in miniature.** A QtWidgets panel on Wayland is tiny — we
  measure it now and set the baseline the budget (§2 of the parent) is held to.

**Does *not* touch** (all later phases): `gest/core`/GeST, the system tray,
launcher/Start menu, window-list taskbar, notifications, wallpaper, quick
settings, the graphical greeter/lock UI, theming, multi-monitor polish, QML.

## 2. Repo, language, build

- **New repo `hede`** (per parent §13 decision 5 — a separate repo on its own
  cadence; the shared Qt frontend still lives in GeST). Binaries keep the
  `helm-` prefix.
- **Language: C++ (Qt 6, Widgets).** No QML in Phase 0 (parent §7 — Widgets-first).
- **Build: CMake + Ninja** (Qt6's first-class tooling: `qt_add_executable`,
  automoc). *Meson is a viable alternative; CMake chosen for Qt6 ergonomics.*
- **Layout:**

```
hede/
  CMakeLists.txt
  src/
    session/      helm-session   (supervisor)
    panel/        helm-panel     (main.cpp, Panel, Clock, LauncherButton)
    common/       layer-shell helper, config reader (grows later)
  data/
    wayland-sessions/hede.desktop        # the greetd/DM session entry
    labwc/{rc.xml,autostart,menu.xml}    # shipped compositor defaults
  tests/
  packaging/                             # ebuild lands end of Phase 0 (optional)
  README.md
```

## 3. Components

### 3.1 `helm-panel` — the only real UI work in Phase 0

A QtWidgets `QWidget` promoted to a layer-shell surface:

- **Surface:** layer `Top`, anchored `Bottom | Left | Right`, height **32px**,
  exclusive zone **32** (so it reserves space), keyboard interactivity **None**.
- **Contents:** a single horizontal layout —
  - **left:** a `LauncherButton` labelled "Terminal" that spawns the configured
    terminal via `QProcess::startDetached`;
  - **stretch** in the middle (where the window list will later go);
  - **right:** a `Clock` (`QLabel` updated by a `QTimer` aligned to the minute).
- **Layer-shell wiring** (via `layer-shell-qt`, the one KF6 micro-dep the parent
  §7 allows):

```cpp
LayerShellQt::Shell::useLayerShell();          // before the window is shown
QWidget panel;
panel.winId();                                  // realise the platform window
auto *ls = LayerShellQt::Window::get(panel.windowHandle());
ls->setLayer(LayerShellQt::Window::LayerTop);
ls->setAnchors(Anchor::AnchorBottom | Anchor::AnchorLeft | Anchor::AnchorRight);
ls->setExclusiveZone(32);
ls->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
panel.show();
```

Model/view split from day one: clock-string formatting and the launcher's
command construction are pure functions (unit-tested headless, §9), the widget
just renders them.

### 3.2 `helm-session` — the supervisor

Phase 0 keeps it minimal (a small C++ binary; a shell script is acceptable for
the very first cut):

1. Export the session environment: `XDG_CURRENT_DESKTOP=HeDE`,
   `XDG_SESSION_TYPE=wayland`, `QT_QPA_PLATFORM=wayland`.
2. `exec` labwc pointed at HeDE's shipped config dir (`labwc -C <hede config>`),
   whose `autostart` launches `helm-panel`.
3. When labwc exits, `helm-session` exits → the session ends (greetd returns to
   the greeter). No child-respawn logic yet; that hardens later.

### 3.3 labwc defaults (shipped by HeDE)

- **`autostart`** — one line: `helm-panel &`.
- **`rc.xml`** — minimal: default theme; two keybinds to make the desktop usable
  before there's a launcher — `Super+Return` → terminal, `Super+Q` → close
  window (`W-Return`/`W-q` in labwc syntax). This is also where GeST will later
  write shortcuts (parent §4).
- **`menu.xml`** — a stub root menu (terminal + exit), so right-click-desktop works.

### 3.4 The session entry — `data/wayland-sessions/hede.desktop`

```ini
[Desktop Entry]
Name=HeDE
Comment=Helm Desktop Environment
Exec=helm-session
Type=Application
DesktopNames=HeDE
```

Installed to `/usr/share/wayland-sessions/`. greetd (and any DM) discovers it;
selecting it runs `helm-session`.

## 4. Config (establish the pattern, keep it tiny)

Per parent §7, config is **QSettings INI** under `$XDG_CONFIG_HOME/hede/`. Phase 0
reads exactly two keys, both with defaults, so the pattern exists early without
scope creep:

- `panel/height` (default `32`)
- `terminal/command` (default `foot`)

No settings UI — hand-edited only. GeST will own this surface later.

## 5. Dependencies (Gentoo atoms)

- **Build:** `dev-qt/qtbase[widgets,wayland]`, `kde-frameworks/layer-shell-qt`,
  `dev-build/cmake`, a C++20 compiler.
- **Runtime:** `gui-wm/labwc`, a terminal (default `gui-apps/foot` — lightweight,
  Wayland-native; user-swappable via config), `gui-libs/greetd` (+ a stock
  greeter such as `tuigreet`) for the integration path.

## 6. Dev workflow (fast iteration without a VT switch)

- **Panel alone:** run `helm-panel` *inside your current Wayland session* — any
  layer-shell-capable compositor hosts it — to iterate on the bar without labwc.
- **Nested full session:** run labwc on the wlroots **Wayland backend** (nested
  as a window inside your existing session) and launch `helm-panel` into it — the
  whole Phase 0 flow, debuggable from your normal desktop.
- **Real session:** select HeDE at greetd on a VT for the end-to-end check.

## 7. Task breakdown

- **T1 — Skeleton:** repo, `CMakeLists.txt`, CI (build + `clang-format`).
- **T2 — Panel surface:** `helm-panel` as a bottom layer-shell bar (empty),
  correct anchors + exclusive zone; runnable standalone in any compositor.
- **T3 — Clock:** minute-aligned `QLabel`; formatting as a pure, tested function.
- **T4 — Launcher button:** spawns the configured terminal (`QProcess`).
- **T5 — labwc defaults:** `rc.xml` (keybinds) + `autostart` (→ panel) + `menu.xml`.
- **T6 — Supervisor:** `helm-session` (env + `exec labwc -C …`).
- **T7 — Session entry:** `hede.desktop`; verify greetd launches it with a stock
  greeter, session starts and exits cleanly.
- **T8 — Tests + docs:** headless CI smoke test, panel unit tests, README
  (build/run/nested-dev), optional `packaging/` ebuild stub.

## 8. Acceptance criteria

- [ ] greetd shows "HeDE"; selecting it starts a labwc session.
- [ ] `helm-panel` is visible at the bottom, full width, 32px tall.
- [ ] The clock shows the correct time and advances.
- [ ] The Terminal button **and** `Super+Return` open a terminal.
- [ ] A maximized window does **not** cover the panel (exclusive zone honoured).
- [ ] Windows move/focus/close (labwc stacking works).
- [ ] `Super+Q` closes the focused window; the labwc menu exits the session.
- [ ] Logging out returns to the greeter with no orphaned processes.
- [ ] Idle `helm-panel` RSS recorded as the baseline for the parent's budget (§2).

## 9. Testing (GeST patterns, extended to the shell)

- **Pure logic** (parent §"Testing"): clock formatting and launcher-command
  construction are functions tested headless — no compositor needed
  (model/view split).
- **Headless integration:** in CI, run labwc on the wlroots **headless backend**
  (`WLR_BACKENDS=headless`, `WLR_LIBINPUT_NO_DEVICES=1`), launch `helm-session`,
  and assert `helm-panel` starts and binds a layer-shell surface (log/protocol
  probe + process liveness). This becomes the smoke harness all later phases reuse.
- **Format/lint:** `clang-format`, `clang-tidy` in CI.

## 10. Non-goals (Phase 0)

- Anything reading `gest/core` or the backend — no network/battery/update/tray
  data. The panel shows a clock and launches a terminal; nothing more.
- Tray, launcher, window list, notifications, wallpaper, quick settings.
- The graphical greeter (`helm-greeter`) and lock (`helm-lock`) — Phase 3.
- Theming, multi-monitor layout, child-respawn/session hardening, QML.

## 11. Open questions

1. **`helm-session`: binary or script for v1?** A shell script ships fastest; a
   small C++ binary matches the rest. Recommend: script the first cut, replace
   with a binary in T6 once the flow is proven.
2. **`layer-shell-qt` version pin** — confirm the KF6 release's API matches the
   snippet in §3.1 (the `Shell::useLayerShell()` + `Window::get()` pattern).
3. **Default terminal** — `foot` (recommended, lightweight/Wayland-native) vs.
   leaving it unset and requiring config. Recommend `foot` as the shipped default.
4. **CMake vs Meson** — recommend CMake; revisit only if Gentoo packaging favors
   Meson for the desktop bits.
