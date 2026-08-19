# Design: HeDE — the Helm Desktop Environment (a Qt/Wayland shell over GeST)

*Status: vision · Scope: a new project — the session, the shell (panel/launcher/tray/notifications), and the settings integration — built **on top of** GeST's existing `core` + polkit backend · Depends on: the GeST Qt frontend ([gated](#relationship-to-the-qt-frontend-gate) until the TUI/CLI side is declared complete), the polkit-gated D-Bus backend, `layer-shell` · Defers: writing a compositor, a file manager, or the privileged login daemon (adopt greetd — we build only the greeter UI), semantic indexing, systemd · Milestone: the track **after** the Qt frontend lands — this doc scopes the target so the Qt frontend is designed to serve it*

> **Name:** **HeDE — the Helm Desktop Environment.** You take the *Helm* of your
> system; **GeST** is the wheel; **GeSI** (Gentoo System Installer) gets you
> aboard. It slots into the `Ge-`/`He-` family, and — branded as *HeDE* — stays
> distinct from Kubernetes' unrelated "Helm." Session binaries use the `helm-`
> prefix (`helm-session`, `helm-panel`, …); `XDG_CURRENT_DESKTOP=HeDE`.

## Naming across the ecosystem

The suite splits the way macOS does — a **place/vessel** names the environment,
plain **things** name the apps. Here the *harbor* names the apps (mostly
nautical, with two mythological keepers):

| Piece | Name | Role |
|---|---|---|
| Desktop environment | **HeDE** (Helm) | the shell you steer from |
| System settings / Control Center | **GeST** | reused wholesale (§9) |
| Installer (live image) | **GeSI** | Gentoo System Installer (§11) |
| File manager | **Seahorse** | Explorer-like browser |
| Terminal | **Porthole** | the window you peer through |
| Screenshot / magnifier | **Spyglass** | capture + zoom |
| Archive manager | **Hold** | the ship's cargo hold — native, tightly integrated into Seahorse ([hold.md](hold.md)) |
| System monitor | **Crow's Nest** | the lookout / watch |
| Text editor / notes | **Logbook** | the ship's log |
| Document / PDF viewer | **Chart** | nautical charts |
| Image viewer | **Portside** | (or fold into Spyglass) |
| Media player | **Pyrrha** | existing Qt player (mythological) |
| Calculator | **Metis** | Titaness of measure (mythological) |

App names are working choices; the two locked by prior decision are **Pyrrha**
(the existing player) and **Metis**. Throughout this doc the desktop is **HeDE**
and its session binaries carry the `helm-` prefix.

## 0. The one-sentence thesis

**HeDE is not a new desktop stack — it is a thin Qt/Wayland *shell* whose
"Control Center" *is* GeST.** YaST is the settings backbone of a distro;
GeST is Gentoo's YaST; a desktop built around it doesn't reinvent a settings
engine, a privilege path, or a hardware/network/user/software model — it renders
a panel, a launcher, and a login session around the `core` + backend that
already exist. Every other lightweight Qt desktop (LXQt above all) has to bolt on
a settings story after the fact. HeDE starts with one.

This reframes the "feature-rich but ultra-lightweight" tension. The *features*
(software management, network, users, services, disk, kernel, firewall, …) are
already written and polkit-gated in `gest/core`. The *desktop* only has to be
the lightweight part: a shell that launches apps, manages windows, and shows a
tray + clock + notifications. We get feature-rich for free and spend our weight
budget only on the shell.

## 1. The wager (same shape as the installer doc)

The installer doc made the wager that "an installer is not a new subsystem, it's
an orchestration over the modules GeST already has." HeDE makes the parallel
wager one layer up:

> A desktop environment is not a new subsystem. It is **(a)** a Wayland session
> that starts a compositor and a shell, plus **(b)** GeST's Qt frontend serving
> as the system-settings half of that shell. The desktop-specific code is only
> the shell chrome and the session glue.

Consequences, and why this is the right bet:

- **No second settings backend.** Network, display, users, services, software,
  disk, time, firewall — all already flow through `core → backend (polkit)`.
  HeDE's "System Settings" is GeST's Qt Control Center, unmodified. This is the
  single largest scope cut available and it falls out of the architecture for
  free.
- **The golden rule still holds.** GeST's rule — *frontends never touch Portage
  or D-Bus directly; they call `core`* — extends cleanly: the shell is just
  another consumer of `core`. A battery applet reads `core/hardware`; a network
  applet drives `core/network` / `core/wifi`; "Update available" in the tray is
  `core/software`'s reader. No privileged surface is added; the backend is
  reused.
- **It informs the gated Qt frontend.** Designing HeDE now, before the Qt
  frontend is built, is the point: it turns "a Qt app" into a concrete
  requirement — the Qt frontend must be **modular and embeddable** so the same
  module widgets run standalone (`gest-settings`) *and* hosted inside the shell.
  See §9.

## 2. The central tension, and the levers that resolve it

"Feature-rich **and** ultra-lightweight" is a real contradiction only if you
build like Plasma. Plasma is QML top-to-bottom, rides KDE Frameworks (KF6) +
Baloo + a heavyweight KWin, and pays for it in RAM and Gentoo build time. HeDE
gets rich features from GeST and spends its weight only where it must. The levers:

| Lever | Heavy (Plasma) | HeDE's choice | Why it's still rich |
|---|---|---|---|
| Toolkit surface | QML/QtQuick everywhere | **QtWidgets-first** for chrome (panel, menus, tray, settings); QML *only* where motion pays (launcher, overview) | Widgets on Wayland are tiny in RAM and instant to draw; features come from `core`, not from a scene graph |
| Frameworks | Full KF6 | **QtBase + QtWayland only**, plus one or two micro-deps (`layer-shell-qt`) | The "framework" is `gest/core`, which we already own |
| Compositor | KWin (heavy, KDE-coupled) | **Adopt a wlroots compositor** (labwc), don't write one | wlroots gives us mature protocol support; labwc is a stacking WM Windows users already understand |
| Indexing | Baloo always on | **Off by default**, optional add-on | Search the launcher + `core` readers, not the whole disk |
| Config | KConfig + daemon | **QSettings INI** in `$XDG_CONFIG_HOME` | Zero daemon, human-editable, GeST can read/write the same files |
| Session | plasma-session | **One small supervisor** + XDG autostart | Lazy-starts components; nothing runs until needed |

Concrete budget target to hold ourselves to: **idle desktop (compositor + shell
+ tray + notifications, no apps) under ~150 MB RSS** on amd64. LXQt+labwc lands
near there; Plasma is multiples of it. If a design choice blows the budget, it
loses.

## 3. Adopt vs. build (the most important table in this doc)

Writing a whole DE from scratch is how projects die. HeDE *builds* only the parts
that are its identity (the shell + the GeST integration) and *adopts* everything
that is a solved, undifferentiated problem. On Gentoo especially, adopting is
cheap — it's a `DEPEND`, and the user compiles it anyway.

| Component | Decision | Choice / rationale |
|---|---|---|
| Wayland compositor | **Adopt** | labwc (see §4). Optionally support wayfire for eye-candy. |
| Panel / taskbar | **Build** | Our identity; Qt layer-shell surface (§5). |
| App launcher / Start menu | **Build** | Windows-welcome centerpiece (§5, §6). |
| System-tray host | **Build** (thin) | StatusNotifierItem host in the panel. |
| Notification daemon | **Build** (thin) | `org.freedesktop.Notifications` → toasts. |
| **System settings** | **Reuse GeST** | GeST Qt Control Center = the settings app (§9). |
| Polkit auth agent | **Adopt** (or thin build) | `lxqt-policykit` works today; Qt reimpl later if desired. |
| File manager | **Adopt** | `pcmanfm-qt` (LXQt) — Explorer-like already. Build later only if it becomes an identity piece. |
| Login daemon (PAM/seat/VT) | **Adopt** | `greetd` — tiny, UI-less; owns the root/PAM/session-launch plumbing (§10). |
| Login screen (greeter) | **Build** | `helm-greeter` — our own UI, a greetd client sharing HeDE's toolkit/theme (§10). |
| Screen lock / idle | **Build** (thin) | `ext-session-lock-v1` surface + idle via compositor; **shares the greeter's UI** (§5). |
| xdg-desktop-portal | **Adopt + config** | `xdg-desktop-portal-wlr` (screenshot/screencast) + a file-chooser portal. |
| Terminal, text editor, image viewer | **Adopt** | LXQt/Qt apps or user choice; not our job. |
| Archiver | **Build** | **Hold** — native, browses in place inside Seahorse; shared `hold-core` (libarchive). See [hold.md](hold.md). |

The through-line: **build the shell and the GeST seam; adopt the rest.** This is
exactly how LXQt stays lightweight and shippable, and LXQt is the closest
existing thing to what's being asked for — a lightweight, compositor-agnostic Qt
desktop. HeDE's differentiator over LXQt is the deep GeST integration.

## 4. The compositor decision

This is the single biggest architectural fork, so it gets its own section. We are
**not writing a compositor** — that's years of protocol-edge-case work and adds a
huge privileged/hardware surface. We adopt a wlroots-based one and configure it
through GeST.

Candidates considered:

| Option | Verdict | Notes |
|---|---|---|
| **labwc** (wlroots, stacking, Openbox-like) | **Recommended** | Ultra-light; *stacking* window model = title bars, taskbar, click-to-focus — exactly the Windows mental model. XML/INI config GeST can generate. Mature layer-shell + foreign-toplevel + session-lock. |
| wayfire (wlroots, Compiz-like) | Supported alt | More eye-candy (wobbly, cube, expo) for the "feature-rich" crowd; heavier. Offer as an opt-in "effects" profile. |
| QtWaylandCompositor (build in Qt/QML) | Rejected for v1 | Most Qt-native, but *we'd own the compositor* — the exact scope we're refusing. Revisit only if adoption proves limiting. |
| KWin | Rejected | Feature-rich but heavy and KDE-coupled; contradicts the weight budget. |
| Smithay (Rust) / hyprland | Rejected | Not Qt-adjacent; hyprland is tiling-first (wrong default for Windows users). |

**Recommendation: labwc as the default, wayfire as an optional "effects"
profile.** labwc's stacking, title-barred, taskbar-driven model is the most
Windows-familiar Wayland compositor that exists, and its light footprint protects
the budget. GeST owns the config: the user edits shortcuts, snapping, and focus
policy in GeST's settings, and GeST writes labwc's `rc.xml` / wayfire's `.ini`.
The shell talks to whichever compositor via **standard protocols only**
(layer-shell, foreign-toplevel-management, xdg-output, session-lock), so
swapping compositors never touches the shell.

## 5. Shell component architecture

Everything the shell draws on-screen is a Wayland **layer-shell** surface
(`wlr-layer-shell` via `layer-shell-qt`); everything it *knows* about the desktop
comes from standard protocols and from `gest/core`. Components, each a small
process the session supervises:

1. **`helm-session`** — the supervisor. Launched by `greetd` via a
   `helm.desktop` / `wayland-sessions` entry. Launches: compositor → portals →
   polkit agent → panel → notification daemon → wallpaper; then honors
   `$XDG_CONFIG_DIRS/autostart`. Owns clean shutdown. ~one file of glue.
2. **`helm-panel`** — the taskbar (bottom, Windows-style). A layer-shell surface
   hosting applets:
   - **Launcher button** (Start menu) — opens `helm-menu`.
   - **Window list** — one button per open toplevel via
     `wlr-foreign-toplevel-management`; click to focus/minimize; grouping later.
   - **System tray** — StatusNotifierItem/`org.kde.StatusNotifierWatcher` host.
   - **Quick settings** — volume, network, battery, brightness applets driven by
     `core/hardware`, `core/network`, `core/wifi` (readers) and the backend
     (mutations). *This is where GeST's `core` powers desktop chrome directly.*
   - **Clock / calendar**, **update pill** (`core/software` reader → "N updates,
     click to open GeST"), **session menu** (lock/logout/reboot/shutdown).
3. **`helm-menu`** — the searchable Start menu. Indexes `.desktop` files
   (freedesktop menu spec), Win-key to open, type-to-search, categories +
   favorites + recents. Optional: search also queries `core/software` ("install
   *gimp*?") — a natural GeST tie-in.
4. **`helm-notifyd`** — `org.freedesktop.Notifications` daemon → bottom-right
   toasts + a history flyout. Honors urgency, actions, and (later) do-not-disturb.
5. **`helm-bg`** — wallpaper as a `background` layer-shell surface; slideshow +
   per-output config, stored in QSettings.
6. **`helm-lock` / `helm-greeter`** — **one login/lock UI, two contexts.**
   `helm-lock` is the in-session `ext-session-lock-v1` surface; `helm-greeter`
   is the pre-session `greetd` greeter (§10). Both are the *same* Qt
   password-prompt over the HeDE wallpaper, doing PAM auth — shared theme,
   widgets, clock/battery. GNOME and Plasma unify login and lock the same way;
   `greetd` lets HeDE do it cheaply.
7. **Settings** — *not a new binary* — this is GeST's Qt Control Center
   (`gest-settings`), plus a handful of desktop-only panels (appearance, panel
   layout, wallpaper, shortcuts) that live as **desktop modules** inside the same
   frontend (§9).

Protocol dependency map (all standard, all compositor-agnostic):

- `wlr-layer-shell-v1` — every panel/menu/notification/wallpaper/lock surface.
- `wlr-foreign-toplevel-management-v1` — the window-list taskbar + Alt-Tab.
- `xdg-output` / `wlr-output-management` — multi-monitor layout (surfaced in GeST).
- `ext-session-lock-v1` — the lock screen.
- `wlr-screencopy` + `xdg-desktop-portal` — screenshots/screencast.
- `idle-notify` / `idle-inhibit` — screen blank, "keep awake during video."
- `input-method` / `virtual-keyboard` — later, for touch/tablet.

## 6. The "make a Windows user feel welcome" design language

The brief is precise: adopt Linux/KDE norms under the hood, but the *surface* must
feel like Windows to a switcher. That's a layout-and-defaults problem, not an
architecture problem — the fdo/KDE norms and the Windows feel are not in conflict,
they're different layers.

**What a Windows user reaches for → how HeDE answers (and the fdo/KDE norm beneath):**

| Windows expectation | HeDE default | Norm underneath |
|---|---|---|
| Taskbar at the bottom, Start on the left | `helm-panel`, bottom, launcher left | layer-shell, `.desktop` menu spec |
| Start menu: press key, type, launch | `helm-menu` on Win/Super, type-to-search | freedesktop menu + `.desktop` |
| Window buttons min/max/close, top-right | labwc title bars, right-aligned controls | xdg-shell / xdg-decoration |
| Alt-Tab through windows | Alt-Tab overlay via foreign-toplevel list | `wlr-foreign-toplevel-management` |
| Aero Snap (drag to edge → half/quarter) | labwc edge-snap + `Super+←/→`; snap zones | compositor tiling/snap |
| System tray + clock, bottom-right | tray host + clock applet | StatusNotifierItem, MPRIS |
| Toast notifications, bottom-right | `helm-notifyd` toasts + history | `org.freedesktop.Notifications` |
| Explorer-like file manager | pcmanfm-qt (tree left, path bar) | Qt file dialogs, XDG dirs |
| One "Settings" app, categorized, searchable | **GeST Control Center** | polkit, `core` modules |
| Right-click context menus everywhere | Qt context menus in shell + apps | — |
| "Check for updates" | tray update pill → GeST Software module | `core/software` |

Defaults that carry the feeling: single-click *doesn't* open by default (Windows
uses double-click); focus-follows-mouse **off**; a visible, always-present
taskbar; a real Start button with an icon and label; window title bars on. All of
these are opt-out in GeST settings for the Linux crowd — welcoming Windows users
is about *defaults*, not about removing power.

Where we lean KDE (the norms worth inheriting): StatusNotifierItem trays (not the
dead XEmbed tray), MPRIS media controls in the tray, `.desktop` actions
(jump-list-like right-click entries), global-menu-capable apps, proper
XDG_CURRENT_DESKTOP so portals and apps behave, and honoring the freedesktop
icon/cursor/color-scheme specs so third-party Qt *and* GTK apps theme correctly.

## 7. Lightweight strategy, made concrete

The weight budget from §2 is enforced by rules, not vibes:

- **QtWidgets for chrome.** The panel, menus, tray, and settings are Widgets.
  QML/QtQuick (and its GPU scene graph) is loaded *only* by `helm-menu`'s
  animation and an optional overview — and even those can fall back to Widgets.
- **No KF6 hard dependency.** Allowed micro-deps: `layer-shell-qt` (small, does
  one job well). Anything larger must justify itself against the budget.
- **Lazy everything.** The supervisor starts the minimum; wallpaper slideshow,
  overview, and search-in-`core/software` spin up on first use.
- **No indexing daemon.** Launcher search is over `.desktop` files (cheap);
  content search is an optional add-on, never default.
- **Config is files, not a daemon.** QSettings INI under `$XDG_CONFIG_HOME/helm`.
  GeST reads and writes the same files, so "panel settings" in the Control Center
  and hand-editing agree.
- **Gentoo-native leanness.** USE flags gate optional features (effects,
  indexing, wayfire support) at build time — the Gentoo way to ship "feature-rich
  *or* minimal" from one source tree. This is a genuine advantage of building
  *for* Gentoo: the user compiles exactly the desktop they want.

## 8. Theming and the app ecosystem

A desktop is judged by how *other people's* apps look in it.

- **Qt apps** — HeDE ships a Qt **platform theme** plugin (or reuses
  `qt6ct`-style config) so all Qt apps pick up the color scheme, icon theme,
  fonts, and cursor from one place — set, of course, in GeST's appearance panel.
- **GTK apps** — write matching `gtk-3.0`/`gtk-4.0` settings + a GTK theme
  mapping so GIMP/Firefox/etc. don't look alien. GeST's appearance panel writes
  both Qt and GTK config from one choice.
- **Icons / cursors / colors** — freedesktop icon-theme + XDG cursor + the
  color-scheme spec, so third-party themes just work.
- **Fonts** — fontconfig; a sane default stack; hinting/antialias in settings.
- **Dark/light + accent** — one toggle in GeST propagates to Qt platform theme,
  GTK, and the shell's own QSettings palette.

## 9. GeST integration — the seam, in detail

This is the reason HeDE exists and the constraint it places back on the (gated)
Qt frontend.

**The Qt frontend must be built modular and embeddable.** Today's TUI is a
`core`-driven set of module screens. The Qt frontend should be the same modules
as **self-contained widgets** with a common interface — so the exact same
`SoftwareModule`, `NetworkModule`, `UsersModule` widget runs in two hosts:

1. **Standalone** — `gest-settings`, a windowed Control Center (the YaST-app
   experience, KDE System Settings-like sidebar + module pane).
2. **Embedded** — hosted by HeDE: the panel's network applet opens the
   `NetworkModule` widget in a popover; the update pill opens the
   `SoftwareModule`; "Display" in a monitor's right-click opens the display
   module. Same widget, different frame.

Design rules that follow, to record now so the Qt frontend is built to fit:

- **Module = widget + a descriptor** (id, title, icon, category, capabilities).
  The host (standalone shell *or* HeDE panel) discovers and frames modules; it
  doesn't know their internals.
- **Desktop-only modules live with their subject** (per the *settings live in
  their module* principle): Appearance, Panel Layout, Wallpaper, Shortcuts,
  Notifications are HeDE modules that plug into the *same* frontend registry as
  the system modules — the Control Center shows both, seamlessly.
- **Privilege path unchanged.** Embedded or standalone, mutations go
  `widget → core → backend (polkit)`. The panel is unprivileged; it never gains
  new powers by being "the desktop." A network change from the tray prompts the
  same polkit dialog as from the standalone app.
- **Shell reads via `core` readers.** Battery %, SSID, volume, update count,
  disk usage — all existing/near-existing `core` readers. Where a reader is
  missing (e.g. live volume/brightness), it's a small `core` addition following
  the `model/reader/commands/backend_client` convention, reusable by the TUI too.

Net effect: the desktop makes the Qt frontend *more* valuable and gives it a
sharper spec, while the frontend gives the desktop its entire settings story.
They are two renderers over one `core` — GeST's founding idea, taken one hop
further.

## 10. Session, login, portals, autostart

- **Login — `greetd` + `helm-greeter` (build our own greeter, adopt the daemon).**
  `greetd` is a tiny, UI-less login daemon that owns the privileged plumbing —
  PAM auth, seat/VT management, session launch — and nothing else. It runs a
  minimal compositor (labwc or `cage`) with **`helm-greeter`** as its only
  client: a layer-shell greeter over the HeDE wallpaper, reusing the shell's
  widgets and theme (§5), so the login screen *is* a mini-HeDE and genuinely
  ours — without us reimplementing root/PAM code. On success `greetd` launches
  `/usr/share/wayland-sessions/helm.desktop` → `helm-session`. Prior art:
  `qtgreet` (an existing Qt greetd greeter) proves the path.
  - **The privilege boundary is deliberate.** The greeter runs as **root, before
    any user session exists**, so it shares HeDE's *code and look*, not its
    process — the same "frontends never hold privilege directly" discipline as
    GeST's polkit backend. Writing the DM *daemon* ourselves is a non-goal (too
    much high-risk root code); building the *greeter UI* is squarely our job.
  - **GeST owns the login config.** Autologin, default session, the user list,
    "remember last user" — all written to `/etc/greetd/config.toml` through the
    polkit backend, exactly as GeST writes labwc's `rc.xml`. First-boot user
    creation is already `core/users`.
- **Session bring-up order** — compositor → `dbus-activation` env
  (`XDG_CURRENT_DESKTOP=HeDE`, `XDG_SESSION_TYPE=wayland`) → portals → polkit
  agent → panel/notifyd/wallpaper → XDG autostart.
- **Portals** — `xdg-desktop-portal` + `-wlr` (screenshot/screencast/screencopy)
  + a file-chooser portal, so Flatpak/browser file dialogs and screen sharing
  work out of the box.
- **Polkit agent** — adopt `lxqt-policykit` initially; a small Qt agent later if
  we want the dialog to match the theme.

## 11. Live-image tie-in (closes GeST's north-star loop)

`packaging/livecd` already scaffolds a catalyst-built live image — **GeSI, the
Gentoo System Installer**. HeDE is the natural face of it:

> Boot the **GeSI** live image → land in the **HeDE** desktop → open **GeST** →
> **install Gentoo** onto disk (the installer track), with a real browser,
> terminal, and file manager available while you do it.

That's the whole "CLI end goal: Gentoo install" north star delivered as a
product: a graphical live installer environment that is *also* a preview of the
desktop you're about to install. It also gives HeDE a built-in QA loop — the live
image is a disposable, reproducible test bed for the shell.

**Done (Phase 4 start):** HeDE is wired into `packaging/livecd` — `gui-apps/hede`
(+ elogind/seatd/greetd) is in the image package set (both `gest.packages` and
the stage1 spec), and a greetd **autologin** overlay boots root straight into
the HeDE session (`overlay/etc/greetd/config.toml`, services via `livecd/rcadd`).
So the ISO now boots into the desktop; the motd points at GeST's "Install
Gentoo". (Unverified end-to-end — building the ISO needs catalyst on a Gentoo
host; the catalyst keys/service names may need per-host tuning.)

## 12. Phased roadmap

Each phase is independently demoable, matching GeST's release cadence.

- **Phase 0 — "Hello Wayland."** `helm-session` starts labwc + a bare
  `helm-panel` (clock only) that can launch a terminal. Proves the session,
  layer-shell, and the `greetd` session entry. *No `core` yet.*
- **Phase 1 — Daily-drivable shell.** Launcher (`helm-menu`), window-list
  taskbar (foreign-toplevel), tray host, `helm-notifyd`, wallpaper. This is the
  first thing a person can *use* all day. Add to the live image.
- **Phase 2 — GeST is the Control Center.** *(Requires the Qt-frontend gate to
  have lifted.)* Embed GeST modules: settings app + panel applets
  (network/volume/battery/brightness/update) driven by `core`. Polkit agent.
  Appearance panel writing Qt+GTK theming.
- **Phase 3 — Windows-welcome polish.** Aero-Snap zones + `Super+arrows`,
  Alt-Tab overlay, the shared login/lock UI (`helm-lock` + the `greetd`
  `helm-greeter`), quick-settings flyout,
  do-not-disturb, MPRIS in the tray, jump-list `.desktop` actions.
- **Phase 4 — Product.** Effects profile (wayfire opt-in), overview/expo,
  multi-monitor layout UI (in GeST), theming polish, and the live-installer
  experience hardened into a shippable ISO.

## 13. Open decisions (resolve before Phase 0)

1. ~~**Name.**~~ **Decided: HeDE — the Helm Desktop Environment** (see the
   naming section up top). App suite named; `Pyrrha` and `Metis` locked.
2. **Compositor default** — labwc (recommended) vs. wayfire-first. Recommend
   labwc; wayfire as an opt-in profile.
3. **QML scope** — Widgets-only for v1, or allow QML in `helm-menu` from day one?
   Recommend Widgets-first, QML confined to the launcher.
4. **KF6 micro-deps** — is `layer-shell-qt` acceptable, or bind `wlr-layer-shell`
   ourselves to keep KF6 at absolute zero? Recommend accepting `layer-shell-qt`.
5. **Repo layout** — new top-level repo, or `gest/desktop/` in-tree? Recommend a
   **separate repo** that depends on published GeST `core` — the desktop and the
   admin tool have different release cadences, but the Qt frontend (shared by
   both) stays in GeST.

## Non-goals

- Writing a compositor or a file manager (adopt both), or the privileged login
  *daemon* — adopt `greetd`; we build only the `helm-greeter` UI on top of it.
- A second settings/privilege backend — GeST's `core` + polkit backend is *the*
  backend, full stop.
- ~~systemd support (OpenRC only).~~ **Reversed:** HeDE is systemd-only — greetd,
  logind/systemd D-Bus, and the seamless stack all assume it. GeST is dropping its
  init-agnostic hedging (see `hede-systemd-stack.md`); OpenRC support is what's now
  out of scope for HeDE.
- Semantic/file-content indexing on by default.
- Tiling-WM-first workflows as the default (offer snap/tiling as opt-in; the
  default is stacking + taskbar for the Windows-welcome brief).
- Starting **any** of this before the Qt frontend gate lifts (see below). This
  doc is the *target*, written now precisely so the Qt frontend is built to hit it.

## Relationship to the Qt-frontend gate

GeST's standing rule: **the Qt/KDE frontend is not started until the TUI/CLI side
is declared complete** (polish + broad YaST parity). HeDE sits *downstream* of
that frontend — Phase 2 onward literally *is* the Qt frontend embedded — so
nothing in Phases 0–1 requires the gate to lift, and nothing past Phase 1 begins
until it does.

The productive move available *now*, with the gate closed, is exactly this
document: let the desktop's needs shape the Qt frontend's design so it's born
**modular and embeddable** (§9) rather than retrofitted. Designing the target
before building the renderer is the same discipline that made GeST's `core`
frontend-agnostic in the first place.

## Testing (when building begins)

Follow GeST's established patterns, extended to the shell:

- **`core` readers/commands** the shell relies on: injected `Runner`/paths over
  fixtures (the `datetime/reader.py` pattern); pure-argv command builders.
- **Shell logic** (menu indexing, toplevel-list model, notification queue,
  snap-zone math): pure unit tests, no compositor needed — model/view split so
  the model tests headless.
- **Protocol integration**: a headless wlroots/labwc instance in CI to smoke the
  layer-shell surfaces and foreign-toplevel wiring.
- **Privilege**: every mutation path from a shell applet re-uses and re-tests the
  backend contract (device/path allow-listing, server-side re-validation, no
  partial state) — the panel must never be a privilege shortcut around polkit.
- **The live image** as an end-to-end bed: boot-to-desktop-to-installer as the
  integration test.
