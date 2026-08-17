# GeST / Helm — Roadmap

**GeST** is a modular system-administration tool for Gentoo (frontend → core →
root/polkit backend), with two frontends — an urwid **TUI** and a **Qt** Control
Center. That same Qt Control Center is the settings surface for **HeDE**, the
**Helm Desktop Environment**: a Qt/Wayland desktop for Gentoo built to feel
familiar to people coming from Windows.

**North star:** a feature-rich, first-class Gentoo desktop **and** a CLI that can
facilitate a full Gentoo install end-to-end.

> Status: **v0.52.3** — bootable amd64 GeSI ISO into HeDE, with the Control
> Center at TUI parity and a palette-driven titlebar skin landing. This file is
> the durable plan; the "In flight" / "Now" sections below are the only parts
> that date.

---

## Guiding principles

- **Familiarity first.** Windows-familiar control placement by default (muscle
  memory), then earn the right to differ. Familiarity is never buried in a toggle.
- **One backend, thin frontends.** Frontends never touch Portage/D-Bus directly;
  `core` is the only thing that speaks to the root backend. A second frontend is a
  new renderer, not a rewrite.
- **Brother-and-sister frontends.** TUI and Qt share one Windows-11-Settings-style
  information architecture. The TUI carries the Gentoo system/session-config
  subset (system vs. look: auto-login is in scope, wallpaper/skins are Qt-only);
  it stays first-class for headless/SSH and the installer.
- **systemd only.** HeDE targets logind/systemd directly; no init-agnostic hedging.
- **Shared design language.** Every HeDE surface (shell, Start menu, Control
  Center) themes itself from one place — `hede.conf [appearance]` (palette +
  accent) + the freedesktop icon theme — so nothing needs a rewrite to match.

---

## Done — shipped on `main`

- **Core architecture** — frontend/core/backend split, D-Bus + polkit, both
  frontends (urwid TUI, Qt Control Center; Qt shipped v0.51.0).
- **HeDE shell scaffold** under labwc/Wayland — panel, taskbar, tray,
  quicksettings, session, Start menu (modelled on Open-Shell), theme/palette lib.
- **GeSI live-CD** builds *and boots* end-to-end into an interactive HeDE
  (amd64, QEMU-verified) — **v0.52.1**.
- **Committed to systemd** as the single init system.
- **Control Center at TUI parity** — one shared category map across TUI, Qt, and
  the gestd catalog; Qt grew 21 → 34 modules, rail mirrors the TUI one-for-one —
  **v0.52.2** *(#80, #81)*.
- **Design language A–C** — the Control Center consumes the shared Helm palette +
  icons from `hede.conf`; monospace for terminal-like views — **v0.52.2** *(#82)*.
- **Foundations + services on systemd** — systemd commitment, familiarity
  north-star, HeDE theme package, Services module migrated to systemd —
  **v0.52.2** *(#76–79)*.
- **Frameless-window fix** — menu-launched apps now get server-side decorations
  at the source (the Start menu is the Control Center's main launch path) —
  **v0.52.3** *(#85)*.

## In flight — written, in review (open PRs, *not yet on `main`*)

- **Design language D — window chrome.** A palette-driven Helm titlebar skin for
  labwc: `helm-theme` generates a `themerc` from `dark`+`accent`, regenerates it
  live on theme change, ships a Harbor default to `/usr/share/themes`, and the two
  `rc.xml` copies are reconciled. *(#88)*

## Now — the immediate heading

1. **Land Design D (#88)** onto `main`, then bump Amphitheater's `gui-apps/hede`
   and rebuild the ISO so the live image ships the titlebar skin — at which point
   the two livecd overlay stopgaps (`overlay/.../labwc/rc.xml` + the overlay
   `themes/Helm`) can be dropped.
2. **Appearance the user drives** — layer the bespoke painterly titlebar art (the
   `helm-titlebar-skins` pipeline, `.helmtheme` bundles) on top of the
   palette-driven default, and make wallpaper/background a first-class,
   Control-Center-driven system. *(the near-term slice of "the gold" below.)*
3. **Shell-surface polish** — mature notifications, quicksettings, tray, taskbar,
   and the launcher from "the frame stands" to "lived in."

---

## The gold — a feature-rich desktop

What stands between here and a complete, daily-driver HeDE, by area:

### Shell surfaces (scaffold → polish)
Notifications, quicksettings, tray, taskbar, a real app launcher, lock screen,
wallpaper/background, session management — matured from "the frame stands" to
"lived in."

### Appearance & theming
The theme package (tokens + component contract) + titlebar skins + wallpaper as a
first-class, palette-driven system the user actually drives from the Control
Center. Bespoke titlebar art (the Helm titlebar-skin pipeline) layered on top of
the palette-driven default.

### Control Center depth
Close the last coverage gaps (World custom-set editing, richer table previews for
Update/Clean-Up) and surface any remaining system domains. Decide, when it
matters, whether the Control Center stays embedded-Python or goes native C++/QML
inside the shell — deferred while both remain Qt and share the palette.

### Hiedi — the assistant
A first-class, local-first AI project-planning assistant (Ollama by default,
optional Claude), reusing the Qt frontend and Keychain; a nautical
"Voyage / Chart / Logbook" model.

### Keychain — secrets
Our own Secret-Service provider (a vault + session daemon), rather than adopting
gnome-keyring/kwallet; Gangway is its first consumer.

### Installer to the finish line (the CLI north star)
GeSI facilitating a full Gentoo install end-to-end — partitioner, kernel,
bootloader — with an already-root/no-polkit path for the live-CD. Close the
Apple-Silicon/Asahi gap (Asahi kernel + m1n1) so it installs beyond x86.

### The TUI, kept first-class
The headless/SSH + installer sibling stays maintained within its scope — Gentoo
system/session configuration — never drifting into desktop-look territory.
