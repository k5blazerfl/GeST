# Design: Gangway Phase 5 — seamless RemoteApp/RAIL scope

*Status: scope · Scope: what it actually takes to turn a remote Windows app (on a VM or a dedicated machine) from "a full desktop in a window" into a first-class HeDE toplevel with its own taskbar identity · Depends on: [Gangway v1](hede-windows-interop.md#3-gangway--remote-windows-over-rdp) (shipped), the Customs layer ([§2](hede-windows-interop.md#2-customs--the-shared-foreign-app-integration-layer)), HeDE's foreign-toplevel taskbar · Defers to upstream: FreeRDP's RAIL-on-Wayland maturity · Companion to: [hede-windows-interop.md](hede-windows-interop.md) §5 roadmap item #5*

> This doc is the concrete build-out of **Phase 5** from the interop roadmap
> ([hede-windows-interop.md §5](hede-windows-interop.md#5-roadmap)). The interop
> doc's "honesty note" already flags RAIL-on-Wayland as experimental; this doc
> says *how* experimental, *what* code it touches, and *why* it should not be
> scheduled as a single push. Read the interop doc first — this assumes its
> vocabulary (Gangway, Customs, RAIL).

## 0. The one-sentence verdict

**Phase 5 is not a flag addition — it is a FreeRDP client swap plus building the
Customs identity spine that was designed but never wired.** The RAIL-specific
code is small-to-medium; it sits on top of (a) a foundational identity layer that
is 0% connected today and (b) an upstream FreeRDP RAIL story that is still
unreliable as of August 2026. Neither of those is a line-count problem.

## 1. Two structural facts that drive everything

### 1a. The hardcoded engine cannot do it

Gangway v1 hardcodes `CLIENT = "sdl-freerdp"` (`gest/core/rdp/commands.py:12`).
As of FreeRDP 3.23, the SDL client **still has no RAIL support** — upstream itself
names RemoteApp "the biggest missing feature" of the SDL client and advises that
*"xfreerdp is still the best option (even on Wayland) until SDL3 catches up."* The
SDL/Wayland clients render into a single surface; they have no per-remote-window
local-toplevel model, so `/app:` under `sdl-freerdp` yields one window, not N
first-class Wayland toplevels.

Per-window RAIL therefore means shelling **`xfreerdp` (the X11 client) under
Xwayland**, which creates one real toplevel per remote window with a distinct
`WM_CLASS`. That WM_CLASS branch is exactly what Customs' identity map already
anticipates (`gest/core/customs/identity.py:19-25`). Consequence: the single-client
assumption in `commands.py` is a **structural pivot point**, and the identity key
for RAIL is X11 `WM_CLASS`, not Wayland `app_id`.

Client status references:
- `wlfreerdp` deprecated; SDL2 client deprecated since FreeRDP 3.13.0; SDL3 is the
  forward path but lacks RAIL.
- Live upstream regression: [FreeRDP #12391](https://github.com/FreeRDP/FreeRDP/issues/12391)
  — RemoteApp windows silently fail to appear on `xfreerdp3` in 3.23.0 (regressed
  from 3.22.0). **Even the mature X11 path is currently fragile** and must be
  host-validated against a pinned FreeRDP version.

### 1b. The seamless spine is 0% wired

The whole "first-class taskbar citizen" promise rests on Customs §2.4 (map a
foreign window's identity → a synthesized `.desktop`). That spine exists as pure
code on the GeST side and is consumed by nothing:

- `gest/core/customs/identity.py` — `IdentityMap` (`app_id`/`WM_CLASS` → `desktop_id`)
  is clean and correct, but **imported by nothing**: no writer, no serialization to
  a file HeDE can read, no C++ reader. `launcher.py` imports `customs.mime` and
  `customs.desktop`, never `customs.identity`.
- HeDE consumer side (`hede/src/taskbar/`) — buttons are **text-only**
  (`taskbarwidget.cpp:67`, `setToolButtonStyle(Qt::ToolButtonTextOnly)`); the
  `app_id` captured off `wlr-foreign-toplevel` (`foreigntoplevel.cpp:62`) is used
  only as fallback button text. There is **no icon resolution and no identity
  resolution at all** — no `setIcon`, no `QIcon::fromTheme`, no `app_id → .desktop`
  lookup anywhere in the taskbar.

So even a *perfect* per-app WM_CLASS coming out of `xfreerdp` would land today as an
untitled generic text button. **The identity spine is not RAIL polish — it is
foundational work that Drydock needs too** (a Wine `.exe` toplevel has the identical
"which `.desktop` is this window?" problem). Build it once; both subsystems benefit.

## 2. Work breakdown

Sized as small / medium / large, with file anchors. "Small" = pure, unit-testable,
localized. "Large" = cross-language and/or foundational.

| # | Work item | Files | Size | Notes |
|---|---|---|---|---|
| A | Engine pivot: client selection + `/app:` argv branch | `gest/core/rdp/commands.py:26-70` | **medium** | Full-desktop stays `sdl-freerdp`; RAIL mode → `xfreerdp` + `/app:program:/name:/cmd:`, drop `/f`/`/size:`. The risk lives here (see §1a, #12391). |
| B | RemoteApp profile fields + `.rdp` round-trip + CLI args | `model.py:23-59`, `rdpfile.py:45,72`, `gest/tui/gangway/cli.py:50-59,147-164` | **small** | Add `remote_app` mode + `remote_app_program/cmd/name/workdir`; `is_valid()` requires program in RAIL mode; map to *native* `.rdp` keys (`remoteapplicationmode/program/name/cmdline`) — faithful, not invented; `--app`/`--app-name` args. All pure. |
| C | Identity spine: writer + install-path registration → HeDE reader | `gest/core/customs/identity.py`, `cli.py:115` (`cmd_install`), **new C++ in** `hede/src/taskbar/` | **large** | Python: serialize `IdentityMap` to a file HeDE reads; register `WM_CLASS`→`desktop_id` on install. C++: read it (or use Qt `desktopFileName` resolution), `QIcon::fromTheme`, switch `TaskButton` off text-only, group windows under one launcher. **None of this scaffolding exists.** |
| D | Per-app `.desktop` synthesis | `gest/core/rdp/launcher.py:32-42` | **small-medium** | Today: one launcher/profile, hardcoded `sdl-freerdp` WM_CLASS + `icon="gangway"`. RAIL: per-app ids (`gangway-<profile>-<app>`), the app's own icon/name, a WM_CLASS matching what `xfreerdp` reports. |
| E | RemoteApp icon acquisition | `gest/core/customs/icons.py:18,24` | **medium** | `wrestool` needs a local `.exe`; a RemoteApp icon arrives as a **blob over the RAIL channel** (window-icon PDUs), not a file. New acquisition path; `icon_install_path()` half is reusable. |
| — | MIME (`.rdp` + `rdp://`) | `gest/core/customs/mime.py:11-14` | **done** | A RAIL profile is still a `.rdp` file. No change. |

Roughly **~60% of Phase 5's cost is item C** — the identity spine — which is not
RAIL-specific and pays off Drydock too.

## 3. Recommended sequencing — do NOT ship as one push

### Phase 5a — the spine (do first, ship independently)

Items **C + D**. Wire `IdentityMap` end-to-end and give the taskbar real icons and
identity for *full-desktop* Gangway **and Drydock** windows. Valuable on its own,
fully testable, de-risks the hard part, and is where the C++ work lives — so it
parallelizes with someone else spiking FreeRDP. Nothing here depends on RAIL
working.

### Phase 5b — the engine (gated on a spike)

Before committing to **B + A + E**, run a **1–2 day host-validation spike**
(host-validated, never CI — matches `gest/core/rdp/__init__.py:9`):

1. On a real Windows VM/host, run `xfreerdp /app:program:...` under Xwayland on a
   **pinned** FreeRDP version.
2. Confirm you get **distinct toplevels** with usable, stable `WM_CLASS` per remote
   app.
3. Confirm [FreeRDP #12391](https://github.com/FreeRDP/FreeRDP/issues/12391) is not
   blocking on that version (pin below or above the regression as needed).

- **Green** → B (small) + A (medium) + E (medium) follow, feeding the 5a spine.
- **Red** → Phase 5b is **gated on upstream**. The honest move is to say so and hold;
  full-desktop Gangway + the 5a identity spine remain the shipped ceiling. This is
  precisely what the interop doc's Phase-5 honesty note hedges.

## 4. Non-goals (unchanged from interop doc)

- **No hypervisor / VM lifecycle.** Gangway stays a *client*
  ([hede-windows-interop.md §6](hede-windows-interop.md)). A local Windows VM is just
  another `host:port` that must already be up — no libvirt/QEMU orchestration,
  auto-start, or enhanced-session special-casing. A Hyper-V enhanced-session guest is
  reached as `host:3389` like any other.
- **No inbound RDP server** (xrdp / Linux-as-host) — separate future services module.

## 5. Bottom line

The seamless "a Windows app that looks like it lives here" experience is, today,
**design-only**. The current ceiling is a single full-desktop RDP window that is
correctly named/grouped in the taskbar. Closing the gap is mostly the identity spine
(build it regardless — Drydock wants it), plus a RAIL-specific remainder that is
small-to-medium *code* sitting on an upstream FreeRDP RAIL path that is not yet
dependable. Spike-gate the engine; ship the spine now.

---

*Sources: [FreeRDP #12391 (RemoteApp on xfreerdp3 regression)](https://github.com/FreeRDP/FreeRDP/issues/12391) · [FreeRDP Discussion #11595 (which client on Wayland)](https://github.com/FreeRDP/FreeRDP/discussions/11595) · [FreeRDP RAIL / window management (DeepWiki)](https://deepwiki.com/FreeRDP/FreeRDP/5.1.2-window-management-and-rail) · [Arch: SDL2 client deprecated](https://gitlab.archlinux.org/archlinux/packaging/packages/freerdp/-/issues/5)*
