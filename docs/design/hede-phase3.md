# Spec: HeDE Phase 3 — Windows-welcome polish

*Status: spec · Scope: the shell niceties that make a switcher feel at home — Aero-Snap, an Alt-Tab overlay, the shared login/lock UI, jump-list actions, do-not-disturb, MPRIS media controls, a quick-settings flyout · Depends on: [hede-phase1](hede-phase1.md) (panel/taskbar/tray/notifyd), [desktop-environment](desktop-environment.md) §6 (the Windows-welcome brief) · Not gated: all of Phase 3 is HeDE shell + compositor config — no GeST Qt frontend · Milestone: the desktop feels finished, not just functional*

## 0. Goal

Phases 1–2 made HeDE usable and connected. Phase 3 is the layer of expected-desktop
behaviours — the things whose *absence* a Windows user notices. None of it touches
the gated Qt frontend.

## 1. Components & order

Ordered by self-containment (build top-down):

1. **Aero-Snap + `Super`+arrows.** *[this increment]* Compositor keybinds:
   `Super+←/→` half-tile, `Super+↑` maximize, `Super+↓` minimize. labwc config
   HeDE ships (GeST will generate it later); edge-drag snapping is labwc-native.
2. **Jump-list `.desktop` actions.** *[this increment]* Right-click a launcher
   result → its declared actions (e.g. "New Window", "New Private Window").
   Parse `Actions=`/`[Desktop Action …]`; pure, unit-tested.
3. **Alt-Tab overlay.** A centred overlay listing open toplevels, cycled with
   Alt-Tab. Reuses the foreign-toplevel model from `helm-taskbar`. (labwc has a
   native cycler; the overlay is the themed HeDE version — optional.)
4. **Shared login/lock UI** — `helm-lock` (`ext-session-lock-v1`) + `helm-greeter`
   (the greetd greeter), one component (design-doc §5). PAM. The bigger lift.
5. **Do-not-disturb.** A notifyd toggle that suppresses toasts (queued to
   history). Small, testable.
6. **MPRIS media controls.** A tray/panel applet over `org.mpris.MediaPlayer2.*`
   (play/pause/next/prev + title). Testable model.
7. **Quick-settings flyout.** The slider popover deferred in Phase 2 — needs
   xdg-popup-on-layer-shell; the risky-Wayland bit, so it comes once the simpler
   items are in.

## 2. This increment

- **Aero-Snap** — labwc `rc.xml` keybinds (`SnapToEdge`, `ToggleMaximize`,
  `Iconify`). Config only; verified by the headless smoke session later.
- **Jump-list actions** — extend `helm::DesktopEntry` with a group-aware parser
  that reads `Actions=` and the `[Desktop Action <id>]` groups into a
  `QVector<DesktopAction>`; `helm-menu` shows them in a right-click menu and
  launches the chosen action's `Exec` (field codes stripped, as for the main
  launch). Pure parsing unit-tested.

## 3. Testing

- **Parsing** (`desktopentry`): actions parsed (name/exec), main entry unaffected,
  field codes stripped in action execs. Headless.
- **Shell logic**: Alt-Tab cycle order, DND queue behaviour, MPRIS state — pure
  model/view, tested headless as in earlier phases.
- **Config**: the labwc keybind file is shipped data; the smoke harness can grow
  a check that labwc parses it.

## 4. Non-goals

- The GeST Qt frontend / embedded modules (that's gated Phase 2 work).
- A bespoke compositor cycler (reuse labwc's; the overlay is cosmetic).
- Effects/overview/multi-monitor-layout UI (Phase 4).
