# HeDE — the Helm Desktop Environment

A Qt/Wayland desktop shell for Gentoo, built around [GeST](https://github.com/k5blazerfl/GeST)
as its Control Center. See the design docs in GeST's `docs/design/`:
[`desktop-environment.md`](https://github.com/k5blazerfl/GeST/blob/main/docs/design/desktop-environment.md) (the vision) and
[`hede-phase0.md`](https://github.com/k5blazerfl/GeST/blob/main/docs/design/hede-phase0.md) (this scaffold's spec).

> **Early days.** HeDE is in active early development (Phase 1). Design lives in
> the GeST repo's `docs/design/`; this repository holds the shell itself.

## Phase 0 — "Hello Wayland"

The skeleton: `helm-session` brings up **labwc** with a minimal `helm-panel`
(a clock + a Terminal button), launchable from a `greetd` session entry. No
`gest/core`/GeST integration yet — this only proves the frame stands.

## Build

```sh
cmake -S . -B build -G Ninja
cmake --build build
ctest --test-dir build --output-on-failure
```

Requires: Qt 6 (`Widgets`, `Test`), `LayerShellQt`, CMake ≥ 3.21, a C++20 compiler.
Runtime: `labwc`, a terminal (default `foot`), and `greetd` (+ a stock greeter
such as `tuigreet`) for the login path.

## Run

**Panel alone** (fast iteration — inside your *current* Wayland session, any
layer-shell-capable compositor hosts it):

```sh
QT_QPA_PLATFORM=wayland ./build/src/panel/helm-panel
```

**Nested full session** (labwc as a window inside your current session):

```sh
labwc -C data/labwc &        # its autostart launches helm-panel
```

**Real session:** install, then pick "HeDE" at the greeter on a VT.

```sh
cmake --install build --prefix /usr
```

## Layout

```
src/session/   helm-session   — the supervisor (env + exec labwc)
src/panel/     helm-panel     — the bottom layer-shell bar
src/common/    config + pure helpers (unit-tested)
data/          labwc defaults + the wayland-sessions entry
tests/         headless unit tests
packaging/     Gentoo ebuild (live)
```

## Config

`$XDG_CONFIG_HOME/hede/hede.conf` (INI). Phase 0 reads two keys, both defaulted:

```ini
[panel]
height=32

[terminal]
command=foot
```
