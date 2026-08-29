# EzRA — the HeDE task manager

**EzRA** (Ezekiel Resource Arbiter), binary `ezra`, lives at `hede/src/ezra/`.

A task manager is a core power-user surface; HeDE ships one free, and it aims
to match the OG Windows Task Manager's muscle memory, then exceed it with the
things Linux can do honestly. The theming stops at the name: below the
masthead this is a plain, legible system tool — standard labels, standard
verbs, no flavor in the UI.

## Match (muscle memory)

- **Ctrl+Shift+Esc** opens it (bound in `data/labwc/rc.xml`), same reflex as
  Windows.
- The OG tab set as the destination: **Processes, Performance, Startup,
  Users, Details, Services**.
- The same verbs in the same places: End task (bottom-right button and
  context menu), right-click → open file location.

## Exceed (Linux-native honesty)

- **Services** = real systemd over D-Bus — start/stop/restart units, not a
  facsimile.
- Process tree by **cgroup** — what actually belongs to what.
- **Startup** = systemd user units + XDG autostart in one list.
- Per-process **journal** tail; per-process **GPU** via DRM fdinfo.

## Architecture

Barnacle pattern — an engine the window sits on:

- **ezra-lib** (static, Qt Core only, unit-tested — `tests/test_ezra.cpp`):
  - `sampler.{h,cpp}` — pure parsers over `/proc` text (`/proc/stat`,
    `meminfo`, `net/dev`, `diskstats`, `<pid>/stat` — the last anchored on
    the final `)` because comm may contain spaces and parentheses), plus two
    stateful samplers that turn consecutive readings into rates:
    `ProcessSampler` (per-process CPU% as a share of the whole machine, like
    the OG) and `SystemSampler` (machine CPU/memory/disk/network).
  - `processmodel.{h,cpp}` — the Processes table model. Rows merge in place
    by pid each tick so selection and scroll position survive a refresh;
    sorting goes through `SortRole` raw values under a
    `QSortFilterProxyModel`.
- **ezra** (Qt Widgets): `window.cpp` (tabs, filter box, table, End task,
  context menu, status-bar footer), `graph.cpp` (palette-driven history
  graphs: percent graphs fixed 0–100, rate graphs autoscaled to the window
  peak). An ordinary xdg-toplevel like barnacle — labwc draws the SSD
  titlebar; appearance comes from `helm::applyAppearance()` and re-tints
  live on a world switch.

Because GeST's Control Center can consume ezra-lib later, a mini-monitor in
the cockpit costs a window, not a second engine.

## Slices

1. **Shipped in this slice:** Processes (filter, sort, End task/Force kill,
   open file location, copy command line) + Performance (CPU, memory, disk,
   network history graphs), Ctrl+Shift+Esc, `ezra.desktop`, unit-tested
   parsers.
2. Details tab (full column set: PPID, state, threads, nice, command line)
   and per-core CPU view.
3. Services (systemd D-Bus) + Users.
4. Startup (systemd user units + XDG autostart).
5. cgroup tree view, per-process journal tail, GPU via DRM fdinfo.
6. **Shipped:** Startup tab over XDG autostart — and the session half of the
   story: HeDE never ran autostart entries at all, so this slice adds
   `helm-autostart` (in helm-apps, sharing `scanAutostart` with the tab),
   launched from the labwc autostart file. User file shadows system by id;
   disabling writes a user override (`Hidden=true` stub for system entries,
   in-place for user ones); OnlyShowIn/NotShowIn gate by
   `$XDG_CURRENT_DESKTOP`.
7. **Shipped, folded into Performance** (instead of separate Thermals/Energy
   tabs): GPU busy% + VRAM (amdgpu sysfs), hottest temperature (hwmon), and
   package watts — RAPL when readable, else an hwmon power sensor (amdgpu's
   PPT; RAPL's `energy_uj` is root-only since the side-channel mitigations),
   plus battery draw while discharging. Tiles appear only where the hardware
   reports them.
8. **Partly shipped:** tick dropped to the OG's 1 s "Normal" speed.
   Remaining: interpolate between samples if the meters should read
   smoother.
9. Still open: a Summary landing view (the Performance grid now covers most
   of the at-a-glance case — revisit whether a separate tab earns its
   place), cgroup tree, per-process journal tail, per-process GPU via DRM
   fdinfo.

Slices 6–7 are informed by TMOG (tmog.org), the cross-platform freemium
task manager whose Linux build is Qt 6 — its Summary, Energy, and Thermals
views are the fresh ideas worth having. The structural advantages stay
ours: EzRA is in the OS, free, bound to Ctrl+Shift+Esc on a fresh install,
and reaches systemd/cgroup/journal depth that a shared cross-platform core
cannot express.
