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
