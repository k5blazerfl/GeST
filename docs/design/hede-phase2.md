# Spec: HeDE Phase 2 — GeST as the Control Center

*Status: spec (design-only; the build is **gated**) · Scope: make GeST the settings half of HeDE — the **core↔shell seam**, the **embeddable Qt module framework**, **quick-settings applets**, a **polkit agent**, and **appearance/theming** · Depends on: [desktop-environment](desktop-environment.md) (§4 config-via-GeST, §7 config files, §9 the seam), [hede-phase1](hede-phase1.md) (the shell this hangs on), GeST's `core` + polkit backend · Gated by: the standing rule that **the GeST Qt frontend is not started until the TUI/CLI side is declared complete** · Milestone: log in to HeDE, open Settings (= GeST), and change network/appearance/etc.; the panel's quick-settings read live from `core`*

## 0. The gate (read this first)

Phase 2's centre of gravity — "GeST is the Control Center" — **is** the GeST Qt
frontend. That frontend is deliberately gated: it is not to be *started* until
the TUI/CLI side of GeST is declared complete (module polish **and** broad YaST
parity). This document is therefore **design-only**, written now for the same
reason the vision doc was: so that when the gate lifts, the frontend is built
**modular and embeddable from line one** rather than retrofitted.

Each work item below is tagged with when it may begin:

- 🟢 **buildable now** — not the Qt frontend; core/backend or shell work that
  also helps the TUI.
- 🔒 **gated** — is (or hosts) the Qt frontend; waits for the gate to lift.

## 1. Goal

After Phase 1, HeDE is a shell that knows nothing about the system it runs on.
Phase 2 connects it to GeST so that:

1. **Settings *is* GeST.** A windowed Control Center (`gest-settings`) and, hosted
   inside HeDE, the same module widgets in popovers. One codebase, two frames.
2. **The panel reads live system state** — network, volume, battery, brightness,
   "updates available" — *through `core`*, not by re-implementing it.
3. **Every privileged change** still goes `widget → core → polkit backend`. The
   shell gains no new privilege by being "the desktop."

## 2. The core↔shell seam (the real problem)

GeST `core` is **Python**; the HeDE shell is **C++/Qt**. They cannot share a
process. Reads today happen *in-process* in the user-space core (the Portage
Python API, `core/*` readers); mutations already go over the **system** bus to
the root, polkit-gated backend. So the design question Phase 2 must answer is:
**how does a C++ panel applet get `core` reader data?**

Decision — **a GeST session-bus "shell service" for reads; the existing polkit
system backend for writes.** 🟢 (This is `core`/backend work, not the Qt frontend,
and it also gives the TUI a clean IPC path — so it may begin before the gate.)

- **Reads + change signals:** a small **unprivileged** GeST process on the
  **session** bus (working name `org.gentoo.gest.Shell`) exposes exactly what the
  shell needs, each backed by an existing `core` reader:
  - `UpdateCount` / `UpdatesChanged` — `core/software` (`@world` pending).
  - `Network` state summary + `NetworkChanged` — `core/network` + `core/wifi`.
  - `Battery`, `Brightness`, `Volume` (+ their changed signals) — `core/hardware`
    where modelled; where a reader is missing it is a **small `core` addition**
    (per §9 of the vision), reusable by the TUI, *not* a shell-side bypass.
- **Writes:** unchanged — HeDE calls the existing **polkit-gated system backend**
  directly over D-Bus (set Wi-Fi, apply brightness, start an update). The polkit
  agent (§5) handles the auth prompt.
- **HeDE side:** thin C++ D-Bus client stubs (`src/coreclient/`) wrapping the
  session read service + the mutation calls — the *only* place HeDE touches GeST.
- **Rejected:** having applets read UPower/NetworkManager/PipeWire directly. It
  works but forks the source of truth; the vision's whole thesis is that `core`
  is the one model. (Fallback allowed only if a datum has no `core` home *and* no
  value in adding one — documented per-applet if so.)

```
 HeDE panel applet (C++)                     GeST
   ├─ read  ─session bus→  org.gentoo.gest.Shell ─→ core/* readers
   └─ write ─system bus──→  polkit backend ──(polkit)──→ core mutations
```

## 3. The embeddable Qt frontend 🔒

The sharpened restatement of vision §9 — the contract to build the frontend to:

- **A module = a widget + a descriptor** (`id`, `title`, `icon`, `category`,
  `capabilities`). Modules never assume their host.
- **Two hosts, one widget:**
  1. **`gest-settings`** — standalone Control Center (YaST-app / KDE
     System-Settings feel: category sidebar + module pane).
  2. **Embedded in HeDE** — the panel opens a module widget in a popover
     (network applet → `NetworkModule`; update pill → `SoftwareModule`; a
     monitor's right-click → `DisplayModule`).
- **Desktop-only modules live in the same registry** (per *settings live in their
  module*): **Appearance**, **Panel**, **Wallpaper**, **Shortcuts**,
  **Notifications** — HeDE-provided modules that appear alongside the system
  modules in the one Control Center.
- **Language boundary:** the module widgets are part of the **GeST Qt frontend**
  (so, Python+Qt via PySide, *or* a C++/Qt frontend over the seam — an open
  decision, see §8). Either way they consume `core`, never the shell.

## 4. Quick-settings applets (panel) 🔒 for the popover, 🟢 for the indicator

Each panel applet has three parts; the indicator can land before the gate, the
rich popover is the embedded module:

| Applet | Reads (seam) | Mutates | Popover (embedded module) |
|---|---|---|---|
| Network | `Network` + `NetworkChanged` | backend: connect/disconnect, Wi-Fi | `NetworkModule` |
| Volume | `Volume` | backend/system audio | slider + `SoundModule` |
| Battery | `Battery` | — (read-only) | power/`BatteryModule` |
| Brightness | `Brightness` | backend: set brightness | slider |
| Update pill | `UpdateCount` | opens Software module | `SoftwareModule` |

- 🟢 **Indicator** (icon + tooltip + simple state) needs only the read seam →
  buildable pre-gate as a HeDE applet.
- 🔒 **Popover** that embeds a full GeST module → gated. Interim: a minimal native
  popover (e.g. a bare volume slider) until the module exists.

## 5. Polkit agent 🟢

HeDE mutations trigger polkit prompts from the GeST system backend, so the
session needs **exactly one** polkit agent. Adopt **`lxqt-policykit`** first
(ship it in `helm-session`'s bring-up); a themed Qt agent is a later nicety, not
Phase 2. Non-gated (a session component, not the frontend).

## 6. Appearance & theming 🔒 (module) / 🟢 (write targets)

The **Appearance** module (a HeDE desktop module in the Control Center) turns one
choice — light/dark + accent + icon/cursor/font — into config the whole session
honours (vision §8):

- **Qt apps:** a platform-theme config (qt6ct-style) so all Qt apps pick it up.
- **GTK apps:** matching `gtk-3.0`/`gtk-4.0` settings so GTK apps don't look alien.
- **Shell:** HeDE's own `hede.conf` palette keys (already read by the panel).

🟢 The *write targets* (which files, what format) can be specced/prototyped as a
plain writer now; 🔒 the Appearance *UI* is a module → gated.

## 7. Config ownership

Per vision §4/§7, **GeST owns the config; HeDE reads it.** Phase 2 nails down who
writes what into `$XDG_CONFIG_HOME/hede/hede.conf` (and friends):

- HeDE keys GeST's modules will manage: `panel/*`, `wallpaper/*`, `terminal/*`,
  `launcher/*`, appearance palette, shortcuts.
- GeST writes them via the same INI HeDE already reads (Phase 1's `Config`), so
  hand-editing and the Control Center agree. No new config system.

## 8. Open decisions

1. **Frontend language** — PySide6 (reuse `core` in-process, one language with
   the TUI) **vs.** a C++/Qt frontend over the seam (matches the shell, heavier
   duplication). Leaning PySide6 for `core` reuse; revisit at gate-lift.
2. **Read seam transport** — session-bus service (recommended) vs. a local socket
   / shared lib. D-Bus fits the existing backend idiom.
3. **How much hardware goes through `core`** vs. direct system services — resolve
   per datum against the "single source" principle (§2).
4. **Embedding mechanism** — module widgets hosted via a Qt layer-shell popover
   owned by the panel; confirm the process model (in-panel vs. a spawned
   `gest-settings --embed <module>`).

## 9. Sub-milestones

- **2a — the read seam** 🟢 *[started]* `org.gentoo.gest.Shell` (session bus)
  over `core` readers + HeDE `src/coreclient` stubs + indicator-only applets.
  **Done: `UpdateCount`** — GeST `gest/shell` service (dbus-next, backed by
  `core/software.list_upgradable`) + HeDE `CoreClient` + the panel **update
  pill** (graceful when GeST is absent). Remaining datums (Network/Battery/
  Brightness/Volume) follow the same shape.
- **2b — polkit agent** 🟢 *[done]* adopt `lxqt-policykit` — the session
  autostarts one `lxqt-policykit-agent`; `lxqt-base/lxqt-policykit` is an RDEPEND
  (as is `app-admin/gest`, the Control Center + seam).
- **2c — the module framework** 🔒 the embeddable module = widget + descriptor;
  `gest-settings` standalone shell.
- **2d — embedded popovers** 🔒 panel applets open real modules.
- **2e — appearance/theming** 🔒 the Appearance module writing Qt+GTK+shell config.

## 10. Testing

- **Seam:** GeST-side readers tested with the established injected-`Runner`/paths
  pattern; the session service tested with a fake bus; HeDE `coreclient` stubs
  unit-tested against a mock service (model/view split, no live bus).
- **Applets:** indicator state as pure functions over the seam's data
  (model/view), rendered headless.
- **Modules:** each module widget tested as a unit against `core` fakes (the
  standalone host makes this straightforward).

## 11. Non-goals (Phase 2)

- Starting the Qt frontend before the gate lifts. **This doc is the target, not a
  build order to execute now.**
- Re-implementing system state the shell can get from `core` (no forked source of
  truth).
- A bespoke polkit agent, DBusMenu-rich tray, or systemd support.
- Phase 3+ polish (effects, overview, multi-monitor layout UI).
