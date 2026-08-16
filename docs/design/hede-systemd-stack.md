# Design: HeDE — the systemd stack (init commitment)

*Status: decided (2026-08-16) · Scope: the init system HeDE targets, and what that unlocks/simplifies across the shell, the greeter, boot theming, and GeST · Supersedes: the "Defers: systemd / adopt greetd" stance in [desktop-environment.md](desktop-environment.md) · Audience: single maintainer*

> **DECISION: HeDE targets systemd only.** No OpenRC, no elogind, no
> init-agnostic support. This is an opinionated, single-maintainer choice to
> **cut fragmentation** — the desktop is built around one toolset, tuned to work
> seamlessly, and optimized for the maintainer's experience and maintenance
> ceiling rather than for maximizing the init-choice audience.

## Why (the short version)

A "support both" init path taxes the one resource a solo project can't scale:
maintainer time. The features HeDE already commits to — lock, idle, sleep,
shutdown, session/seat, a polished boot→login→desktop sequence — are **native to
systemd** and only *approximated* on OpenRC (via `elogind`, a lagging fork of
`systemd-logind`, plus hand-written Plymouth/greeter glue). Picking systemd:

- makes **logind** first-party instead of a second-hand copy,
- makes the **Plymouth → greeter** handoff turnkey instead of scripted,
- adds **service supervision** (restart/watchdog), **timers**, **socket/dbus
  activation**, and **journald** for free,
- keeps us **fully Gentoo** — it is just the `systemd` profile.

Accepted cost: the anti-systemd Gentoo audience. Acceptable, because the desktop
is opinionated-by-design; we are deliberately *not* offering the choice.

## 0. Base

- **Gentoo systemd profile** (`eselect profile set …/systemd`), global
  `USE=systemd`, **`elogind` dropped** everywhere.
- **Initramfs: dracut** (not genkernel) — it carries real `plymouth` +
  `crypt`/LUKS modules. This is the load-bearing installer change.
- Bootloader: **GRUB** today; **systemd-boot** an easy UEFI option later.

## 1. Boot → greeter (turnkey)

- **Plymouth** ships as one Helm theme (assets: logo + nautical loader +
  LUKS-prompt styling). systemd's `plymouth-start` / `plymouth-quit-wait` units
  order it automatically.
- **Greeter is a systemd unit** on `graphical.target`, `After=plymouth-quit-wait.service`;
  Plymouth `quit --retain-splash` gives a **flicker-free** GRUB → splash →
  greeter → desktop, all sharing the world's wallpaper/palette/accent.
- LUKS passphrase prompt lives in the dracut initramfs, styled to match.

> This **replaces the earlier "adopt greetd, build only the greeter UI" plan** —
> the greeter is our own Wayland UI launched/ordered as a systemd unit.

## 2. Session / seat / power — logind-native

Everything the shell and lock/login screens do maps to
**`org.freedesktop.login1`** (systemd-logind), called directly, no elogind seam:

- lock / unlock, idle → lock via **inhibitor locks**,
- suspend / hibernate, **shutdown / reboot** (the power buttons),
- seat/session for the Wayland compositor; lid/idle (`HandleLidSwitch`, `IdleHint`).

## 3. The desktop session (`systemd --user`)

- HeDE shell, GeST daemon, hiedi, and applets run as **user units** with
  **socket/dbus activation** and **restart policies + watchdogs** (a crashed
  panel comes back).
- Periodic work (update checks, index refresh) = **systemd timers**, not cron.

## 4. Logging

- **journald** throughout; `journalctl --user -u helm-*`. The solo-dev
  debugging kit.

## 5. Networking

- **NetworkManager** (D-Bus, desktop-friendly) — the Wi-Fi/Bluetooth tray
  applets talk to NM/BlueZ directly. `systemd-networkd` stays a headless option.

## 6. GeST drops its init-agnostic hedging

The real simplification — GeST modules target systemd's D-Bus services directly,
one code path:

| GeST module | Now targets |
|---|---|
| Services | `systemctl` / systemd-manager D-Bus (units) — not OpenRC `rc-service` |
| Date & Time | `systemd-timedated` |
| Keyboard / locale | `systemd-localed` |
| Hostname | `systemd-hostnamed` |
| Boot & Kernel | dracut + systemd-boot/grub |
| Privilege | polkit (systemd's polkit integration) |
| Users | accountsservice; optionally `systemd-homed` later |

The `core` backend keeps its polkit-gated seam; its **init abstraction is
removed**.

## 7. Net effect

One toolset, no forks: **GRUB → Plymouth → HeDE greeter → `systemd --user`
session**, with logind for power/seat, journald for logs, timers for chores, and
GeST speaking systemd D-Bus natively. Every "support both" branch is deleted.

## Follow-on work

- Greeter `.service` + ordering; dracut/Plymouth theme layout.
- GeST `Services` module: OpenRC `rc-service` → `systemctl` D-Bus.
- Installer (GeSI): install the systemd profile + dracut + systemd; retire the
  genkernel/OpenRC assumptions.
- Update [desktop-environment.md](desktop-environment.md) "Defers" line to point
  here.
