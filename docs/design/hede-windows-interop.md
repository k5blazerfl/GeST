# Design: HeDE — Windows interop (RDP + Wine/Proton), a first-class-foreign-app plan

*Status: vision · Scope: two switcher-facing integrations for HeDE — **remote** Windows (RDP) and **local** Windows apps (Wine/Proton) — built as GeST Control Center modules plus a small shell-side integration layer · Depends on: the GeST Qt frontend ([gated](desktop-environment.md#relationship-to-the-qt-frontend-gate)) and its module=widget+descriptor seam ([§9](desktop-environment.md#9-gest-integration--the-seam-in-detail)); HeDE's foreign-toplevel taskbar and `.desktop` launcher; the deferred Keychain secrets module · Defers: writing a hypervisor, an anti-cheat story, or reimplementing Lutris/Bottles wholesale · Milestone: after the Qt frontend lands, alongside the HeDE app-suite work*

> This doc is the concrete build-out of one row and one promise from the vision
> doc. §6 ("make a Windows user feel welcome") lists *"Check for updates"*, a
> Start menu, Aero-Snap — the everyday switcher reflexes. The two reflexes it
> **doesn't** yet answer are the ones that keep people on Windows: *"I still need
> that one Windows program"* and *"I need to reach my work PC."* Wine/Proton and
> RDP are those two answers. This doc makes them feel native, not bolted-on.

## 0. The one-sentence thesis

**A foreign Windows program — whether it runs on a remote host over RDP or in a
Wine/Proton prefix locally — should be a first-class HeDE citizen: its own native
window in the taskbar, its own launcher entry with a real icon, its own
double-click file association.** Everything below is in service of that single
sentence. The two subsystems differ only in *where the program runs*; the
integration surface that makes it feel native is the **same** surface.

## 1. The wager

The installer doc wagered an installer is orchestration over existing modules;
the desktop doc wagered a DE is a shell over `core`. This one wagers:

> Windows interop is not an emulator project and not a remote-desktop client
> project. It is **(a)** two thin launchers over mature engines (FreeRDP,
> Wine/Proton via umu), **(b)** a GeST module each to manage profiles/prefixes
> with the *Gentoo-native* advantage of driving USE/make.conf, and **(c)** one
> shared "foreign-app" layer that turns a remote app or a prefix'd `.exe` into a
> `.desktop` + icon + MIME handler + taskbar identity.

We write almost no interop engine. FreeRDP already does RemoteApp, clipboard,
drive/audio redirection, GFX/H.264, and gateways. Wine/Proton already run the
apps; **umu-launcher** already runs Proton outside Steam; DXVK/VKD3D/gamescope
already exist. Our value is *management + native integration + Gentoo prereqs*,
not the runtime.

## 2. The shared spine — "Customs" (the foreign-app integration layer)

Before either subsystem, name the thing they share. A foreign vessel entering the
harbor clears **Customs**: it gets a berth, papers, and a place on the manifest.
Customs is a small library (HeDE C++ side, with a thin `core` helper where GeST
needs it) that both Gangway (RDP) and Drydock (Wine) call. Four jobs:

1. **`.desktop` synthesis** — generate/refresh a launcher entry whose `Exec`
   points at the Gangway/Drydock launcher stub (`gangway-open <profile>` /
   `drydock-run <barrel> <app>`). This is what lands a foreign app in `helm-menu`
   and lets it be pinned to `helm-panel`, with `.desktop` Actions for jump-lists.
2. **Icon extraction** — pull an icon from a Windows `.exe`/`.lnk` (icoutils
   `wrestool`/`wrestool`), from an installer's Start-menu shortcut inside the
   prefix, or from an RDP RemoteApp icon blob; install it into the XDG icon
   theme so the launcher *and* taskbar show the right glyph.
3. **MIME + URI registration** — associate `.rdp`, `application/x-rdp`, `rdp://`
   (Gangway) and `.exe`/`.msi`/`.lnk`/`.bat` (Drydock) so double-click in
   **Seahorse** and links Just Work.
4. **Toplevel identity matching** — map a running window's Wayland `app_id` /
   Xwayland `WM_CLASS` back to its synthesized `.desktop`, so HeDE's
   `wlr-foreign-toplevel-management` taskbar (see
   `hede/src/taskbar/foreigntoplevel.*`) shows the correct icon/title and groups
   windows under one launcher — instead of a generic "freerdp"/"wine" blob.

Customs is the reason "tight" is achievable without touching either engine: both
engines already produce real Wayland/Xwayland toplevels; Customs just gives those
toplevels a *name, an icon, and a home in the menu*.

---

## 3. Gangway — remote Windows over RDP

**Engine:** FreeRDP 3 (`net-misc/freerdp:3`, USE `client sdl wayland X gfx`).
Primary client is **`sdl-freerdp`** (SDL3 — most actively maintained, runs well
under Wayland via SDL's Wayland backend); `wlfreerdp` (native Wayland) is the
fallback. Gangway is a **profile manager + launcher**, not a new protocol.

**What FreeRDP already gives us → how Gangway wires it into HeDE:**

| RDP capability | FreeRDP flag | HeDE wiring |
|---|---|---|
| Clipboard sync | `cliprdr` | bridged to `wl-clipboard`; a per-profile toggle |
| Folder redirection | `/drive:HeDE,$HOME` | Seahorse "share this folder to the session" action |
| Audio out / mic in | `rdpsnd` / `audin` | routed to HeDE's PipeWire; toggles |
| Dynamic resolution | `/dynamic-resolution` | session follows the HeDE window resize |
| Multi-monitor | `/multimon` | maps to HeDE outputs |
| Performance pipeline | `/gfx:AVC444` (H.264) | a quality profile: **LAN / Balanced / WAN** |
| Reach a firewalled host | `/gateway:g,...` | RD Gateway field; ties to GeST net |
| Auth | `/sec:nla` (CredSSP) | credentials from the **Keychain** module |
| **Seamless single app** | `/app:` **RemoteApp/RAIL** | see the honesty note below |

**The "super tight" bit — RemoteApp (RAIL).** RemoteApp renders *one* Windows
program in *its own window* instead of a whole desktop. When it works, that
window is a real toplevel and Customs makes it a first-class taskbar/launcher
citizen — indistinguishable from a local app. **Honesty:** RAIL's seamless local
windowing was engineered around X11; under Wayland/SDL the per-window
integration is less mature. So the roadmap ships the **rock-solid full-desktop
session first**, and treats **seamless RemoteApp windows as an advanced,
explicitly-experimental phase** — not a Phase-1 promise. Full-desktop RDP is
100% reliable today; that's the floor we ship on.

**GeST module (`gest/qt/rdp.py` + `gest/core/rdp/`).** Profile CRUD (host, user,
domain, gateway, resolution/scaling, redirection prefs, quality profile), stored
as `.rdp`-compatible files under `$XDG_CONFIG_HOME/helm/gangway/`. Follows the
`model / reader / commands / backend_client` convention — **but note the
privilege split:** launching a client and reading/writing profiles is a *user*
action needing **no polkit** (unlike the system modules). Gangway is one of the
first largely-unprivileged Control Center modules; only touching a *system* RDP
*server* (xrdp for inbound) would cross into the polkit path.

**Secrets.** RDP credentials are the concrete forcing-function for the deferred
Keychain
module: store host+user in the profile, the secret in the keychain (Secret
Service / `org.freedesktop.secrets`). This is the first real consumer that
justifies building the two-tier secrets manager.

**Shell hooks.** Each profile can emit a Customs `.desktop` ("Connect to
`<host>`") so it's searchable in `helm-menu` and pinnable. Optional LAN discovery
(mDNS / port-3389 scan) surfaces reachable hosts; Hyper-V "enhanced session"
guests via xrdp are a documented target, not special-cased.

---

## 4. Drydock — local Windows apps via Wine/Proton

**Engines:** `app-emulation/wine-vanilla` or `wine-staging` (Wine), **Proton via
[umu-launcher](https://github.com/Open-Wine-Components/umu-launcher)** — the
generic, Steam-less Proton runner (runtime + Proton-GE), which is the modern
standard for running Proton outside Steam — plus `proton-ge-custom`, DXVK,
VKD3D-Proton, `winetricks`, `gamescope`, and MangoHud. Drydock manages **barrels**
and generates native integration; it does **not** reimplement the runtime.

**A *barrel* (a berth in the drydock)** = `{ runner (wine-N / proton-ge / umu),
WINEPREFIX, arch (win64/win32), installed apps, DXVK/VKD3D state, winetricks
verbs, env overrides }`, stored under `$XDG_DATA_HOME/hede/drydock/<barrel>/`.
Bottles-like, but HeDE-native and **Gentoo-aware**.

**The Gentoo-native advantage nobody else has.** Because GeST already owns
`make.conf`, USE flags, and the Software module, Drydock can run a
**prerequisites check** that drives them through `core`: enable `ABI_X86`
(multilib / `abi_x86_32`), the `vulkan`/`dxvk`-relevant USE flags, and pull
`gamescope`/mesa Vulkan — *with the same polkit path as any Software change*.
Bottles-on-Ubuntu can't set your USE flags; Drydock can. Clean privilege split:
**making a prefix and running apps is unprivileged**; *installing packages / flipping
USE* goes through the existing polkit'd Software path.

**Tight desktop integration (the crux), via Customs:**

| Want | How |
|---|---|
| App in the Start menu with a real icon | On `.exe`/`.msi` install into a barrel, Customs synthesizes a `.desktop`; `wrestool` extracts the icon (or reads the installer's in-prefix Start-menu `.lnk`) |
| Double-click an `.exe`/`.msi`/`.lnk` in Seahorse | Customs MIME handler → "Run in Drydock" chooser (pick barrel/runner) |
| Correct taskbar icon + grouping | Customs maps the app's Xwayland `WM_CLASS` / Wayland `app_id` to its `.desktop` for the foreign-toplevel taskbar |
| Per-app runner + graphics | Bottle/app record toggles wine-vanilla vs proton-ge vs umu; DXVK/VKD3D/esync/fsync; Drydock builds the `umu-run`/`wine` launch line |
| Game mode | Launch through `gamescope` (+ `gamemoderun`) with a chosen resolution/upscaler (FSR); one fullscreen toplevel HeDE treats like any window |

**Wayland forward-path (honesty note).** Wine's native Wayland driver
(`winewayland.drv`, usable in recent Wine) is the path to drop Xwayland for
plain apps; Proton still runs Xwayland + gamescope for games today. Drydock
should *prefer* the Wine-Wayland driver where a barrel's runner supports it and
fall back to Xwayland — Customs' identity-matching handles both.

**GeST module (`gest/qt/wine.py` + `gest/core/wine/`).** Barrels CRUD; runner
management (list installed Wine via `eselect`, offer to fetch Proton-GE);
winetricks verbs; per-app config; the prerequisites check above. Optional
"advanced" escape hatch: hand a barrel off to Lutris/Bottles/Heroic if the user
already lives there — we integrate, we don't forbid.

---

## 5. Phased roadmap

Both subsystems are **post-Qt-frontend** (they're Control Center modules + shell
hooks). Order is: prove the floor, then add seamless polish.

1. **Customs core.** `.desktop` synthesis + `wrestool` icon extraction + MIME
   registration + toplevel identity-matching helper, unit-tested headless (pure
   parse/generate). Nothing user-facing yet; both subsystems build on it.
2. **Gangway v1 — full-desktop RDP.** `sdl-freerdp` launcher + GeST profile
   module (no polkit), Keychain-backed creds, clipboard/drive/audio toggles,
   quality profiles, `.rdp` MIME handler. The reliable floor.
3. **Drydock v1 — barrels + native launchers.** Create/manage prefixes over
   wine/umu; install an `.exe` → Customs `.desktop` + icon in `helm-menu`;
   `.exe`/`.msi` MIME handler; the Gentoo prerequisites check via `core`.
4. **Drydock v2 — runners & game mode.** Proton-GE/umu runner selection,
   DXVK/VKD3D toggles, gamescope + MangoHud game mode, Wine-Wayland preference.
5. **Gangway v2 — seamless RemoteApp (experimental).** RAIL single-app windows
   as first-class taskbar citizens via Customs, flagged experimental with an
   honest capability note; LAN discovery.
6. **Polish.** Seahorse "share folder to RDP", per-app jump-list Actions, tray
   affordances (active RDP sessions, running barrels), pin-to-panel.

## 6. Non-goals

- **No hypervisor / VM path.** Running a *whole* Windows in qemu/KVM (and RDP-ing
  into it for enhanced session) is a separate story; Gangway is a *client*.
- **No anti-cheat miracles.** Kernel-anti-cheat titles are out of our hands;
  we surface umu/Proton compatibility, we don't promise it.
- **No Lutris/Bottles reimplementation.** We build the thin native path and
  *integrate with*, not replace, the big game managers.
- **No new protocol or emulator engine.** FreeRDP and Wine/Proton are adopted
  wholesale; we never fork the runtime.
- **No inbound RDP server story here.** Hosting xrdp (Linux-as-RDP-host) is a
  system-service concern for a GeST services/sshd-style module, not Gangway.

## 7. Open decisions (resolve before building)

1. **Names.** Proposed: **Customs** (integration layer), **Gangway** (RDP),
   **Drydock** (Wine/Proton). All in-theme (harbor); none locked. Alternatives
   considered for RDP: *Longboat*, *Signal*.
2. **Build Keychain now?** Gangway needs credential storage. Either build the
   two-tier secrets module as a Gangway prerequisite, or ship Gangway v1 against
   the raw Secret Service and retrofit. Recommendation: build Keychain — it's the
   first real consumer and unblocks more later.
3. **Native Drydock vs. wrap Bottles.** Recommendation: thin native manager over
   umu/wine + winetricks (owns the Gentoo prereq advantage), with an optional
   hand-off to Bottles/Lutris for power users.
4. **Xwayland vs. Wine-Wayland default.** Prefer `winewayland.drv` where the
   runner supports it; Xwayland fallback. Revisit per Wine release.

## 8. Testing (when building begins)

- **Customs (pure, headless):** `.desktop` generation round-trips; icon
  extraction against fixture `.exe`s; MIME/URI registration syntax; identity
  matching (`WM_CLASS`/`app_id` → `.desktop`) — all unit-testable without a
  display, like the existing HeDE `test_desktopentry`.
- **Gangway/Drydock modules:** launch-line construction (flags/env for a given
  profile/barrel) is pure and unit-tested; the *engines* are integration-tested
  behind a manual/smoke harness, never in CI (they need a real host / GPU).
- **Privilege path:** profile/barrel CRUD asserts **no** polkit prompt;
  prerequisite USE/package changes assert they route through the existing
  polkit'd Software path — same guarantee as every other GeST module.
