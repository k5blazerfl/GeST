# Session supervision & General Quarters

Two halves of one promise: when something in the session breaks, HeDE either
heals it before you notice (supervision) or gives you a surface that answers
(General Quarters). Together they define HeDE's rescue ladder:

1. An app misbehaves → EzRA (Ctrl+Shift+Esc), End task.
2. A shell component crashes → systemd user units restart it (supervision).
3. The session needs interrupting → **Ctrl+Alt+Del → General Quarters**:
   Lock / Task Manager / Sign out / Restart / Shut down.
4. The compositor itself is wedged → VT switch (Ctrl+Alt+F2), console.
5. The kernel is wedged → SysRq.

Rungs 3 and below are honest about their limits: inside a Wayland session,
Ctrl+Alt+Del is a compositor keybind, not Windows' kernel-guaranteed Secure
Attention Sequence. A hung compositor answers nothing — that is what rungs
4–5 are for. (The SAS *trust* half — "only the OS can draw this screen" —
is largely covered on Wayland by the platform itself: clients cannot snoop
global input. It becomes relevant again when Keychain prompts for secrets;
noted there, not built here.)

## Supervision: shell components as systemd user units

The shell used to come up from labwc's autostart file with `&` — if
helm-panel or helm-notifyd crashed, nothing restarted it. HeDE is
systemd-only, so the shell becomes **systemd user units**:

- `hede-session.target` — the session umbrella; `Wants=` each component.
- Component services (`helm-panel`, `helm-bg`, `helm-notifyd`,
  `helm-autostart` (oneshot), `gest-shell`, the polkit agent, the idle
  lock): `PartOf=hede-session.target`, `Restart=on-failure`,
  `RestartSec=1`. Optional binaries are gated with `ConditionPathExists`
  so a missing tool skips cleanly instead of flapping.
- The labwc autostart imports the session environment
  (`WAYLAND_DISPLAY`, `XDG_CURRENT_DESKTOP`, Qt decoration vars) into the
  user manager + D-Bus activation environment, then starts the target.
  If the user manager is unreachable it falls back to the legacy `&`
  spawns — no regression on a broken user session.
- helm-session no longer `exec`s the compositor: it runs it, and stops
  `hede-session.target` when the compositor exits, so shell units don't
  outlive the session.
- helm-theme (pre-shell oneshot, ordering matters) and helm-pet
  (hede.conf-conditional) stay script-managed.

What this buys beyond restarts: journal logging per component for free,
and a future EzRA Services follow-up — a System/User bus toggle so the
task manager can see and manage the shell itself.

**Verification caveat:** the dev box runs OpenRC (no systemd user
manager); the units are review-verified and the legacy fallback preserves
current behavior. Runtime verify happens on the live ISO / a GeSI install,
same as the EzRA Services tab.

## General Quarters (`helm-gq`)

The all-hands interrupt surface — the theming stops at the name; the
screen itself is plain verbs. A full-screen `LayerOverlay` layer-shell
surface (helm-menu's backdrop pattern) with exclusive keyboard, a dark
scrim, and one centered column:

- **Lock** — `swaylock -f` (same as Super+L)
- **Task Manager** — launches `ezra`
- **Sign out** — logind `TerminateSession($XDG_SESSION_ID)`
- **Restart** / **Shut down** — logind `Reboot(true)` / `PowerOff(true)`
- **Cancel** — Esc, or a click on the scrim

Single-instance (a lock file in `$XDG_RUNTIME_DIR`); Ctrl+Alt+Del binds to
`helm-gq` in the labwc config, while Ctrl+Shift+Esc keeps going straight
to EzRA — the exact Windows relationship: the chord for "menu that
includes Task Manager" vs the chord for the tool itself.

## Follow-ups

- EzRA Services tab: System/User bus toggle (manage the shell units).
- Keychain design: trusted-prompt note (the SAS trust half).
- A compositor watchdog (rung 3.5) if labwc hangs prove real in practice.
