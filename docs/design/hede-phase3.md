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
3. **Alt-Tab overlay.** *[deferred — compositor-gated]* A normal Wayland client
   can't globally grab Alt-Tab; **labwc's native cycler already handles it**. A
   themed HeDE overlay would need a compositor protocol/hook — not simple client
   work, so it stays on labwc's cycler for now.
4. **Lock screen.** *[done — adopted]* A native `helm-lock` is blocked:
   **QtWidgets can't take the `ext-session-lock` surface role** (no Qt
   integration, unlike LayerShellQt for layer-shell). So HeDE **adopts
   `swaylock` + `swayidle`** (like labwc/lxqt-policykit): `Super+L` locks,
   `swayidle` locks after 10 min and before sleep. Native themed `helm-lock` /
   `helm-greeter` deferred until a Qt session-lock integration exists.
5. **Do-not-disturb.** *[done]* notifyd suppresses toasts under DND (critical
   urgency breaks through); `org.gentoo.hede.Notifications` interface + panel
   bell toggle. Pure `shouldShowToast` unit-tested.
6. **MPRIS media controls.** *[done]* `src/media` panel applet over
   `org.mpris.MediaPlayer2.*` (prev/play-pause/next + track), live via
   PropertiesChanged/NameOwnerChanged. Pure helpers unit-tested.
7. **Quick-settings flyout.** *[deferred]* The slider popover — needs
   xdg-popup-on-layer-shell; scroll-to-adjust (Phase 2) covers the function
   meanwhile.

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
