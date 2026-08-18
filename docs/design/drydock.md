# Design: Drydock — Wine/Proton apps as first-class HeDE citizens

*Status: vision · Scope: the GeST/core model + launch pipeline + Customs integration + the Gentoo-native prerequisites path for running Windows apps/games locally · Depends on: [Customs](hede-windows-interop.md#2-the-shared-spine--customs-the-foreign-app-integration-layer), the GeST software/USE core (for the Gentoo edge), the Qt frontend (gated, for the management module) · Defers: sandboxing, a curated install-script library, live execution (host-only) · Milestone: interop phases 3–4*

> **This is the most-attempted problem in desktop Linux.** Steam/Proton, Lutris,
> and Bottles have all built "run Windows software seamlessly." Drydock only earns
> its place by being **HeDE-native and Gentoo-native** — the two things none of
> them are — while *reusing*, not reinventing, the runtime the others converged on.

## 0. Thesis

**A Windows program installed into a Drydock barrel should feel like a native
HeDE app: one entry in the launcher with its real icon, one window in the taskbar
with the right title, one double-click to run — with the graphics/runtime tuning
already applied.** The barrel setup is where the work lives; everything after is
seamless. Drydock is not a new Wine — it is a *manager + a launch pipeline + the
Customs integration + the Gentoo prerequisite automation* over runtimes that
already exist.

## 1. What the prior art got right (and what we take)

| Tool | The seamless trick | What Drydock adopts |
|---|---|---|
| **Steam + Proton** | Per-app prefix, a **runtime container** (Steam Linux Runtime) for library consistency, one-click, curated compat | Use the same machinery **via umu** (below) instead of cloning it |
| **umu-launcher** (`umu-run`) | Runs Proton *outside* Steam: the SLR container + Proton + **protonfixes** (per-game fixes) generically | **The foundation for Proton barrels.** We shell to `umu-run`, we don't reimplement the runtime |
| **Lutris** | **Install scripts** automate the tedious per-app setup; per-app runner + graphics config; a library | Per-program graphics/runtime config; (later) an install-script notion |
| **Bottles** | Prefixes as first-class **managed bottles** with presets/dependencies; **exports shortcuts** to the desktop | The barrel model + dependency (winetricks) verbs + desktop export — but export via **Customs**, deeper than a bare `.desktop` |

**The two things none of them do, which are Drydock's whole reason to exist:**
1. **HeDE-native integration via Customs** — not just a `.desktop`, but taskbar
   identity matching, MIME/URI handlers, and consistency with Gangway and the
   rest of the shell.
2. **Gentoo-native prerequisites** — Drydock can *set your USE flags, enable
   multilib, and pull the packages* through GeST's polkit'd software core.
   Bottles-on-Ubuntu physically cannot do this; on Gentoo it's the difference
   between "it works" and "figure out `ABI_X86` yourself."

## 2. The wager

> Running Windows software is not an emulator project. It is **(a)** a barrel
> model over a prefix, **(b)** a *pure* launch pipeline that assembles the right
> env + wrapped argv, **(c)** the Customs integration that makes the result
> native, and **(d)** a Gentoo prerequisite checker that drives GeST's existing
> software/USE path. The runtime — Wine, Proton, umu, DXVK, gamescope — is all
> adopted.

## 3. Foundations (verified 2025–2026 — see the research brief)

- **Proton via umu** (`games-util/umu-launcher`, **GURU overlay** — not in-tree):
  `umu-run <exe>` with env **`GAMEID`** (keys protonfixes), **`PROTONPATH`** (a
  path, a version name in `compatibilitytools.d`, or a codename like `GE-Proton`
  to auto-download), **`WINEPREFIX`**, **`STORE`**, **`PROTON_VERB`**. **Proton
  bundles DXVK + VKD3D-Proton** — so Proton barrels need *no* separate DXVK setup.
- **Plain Wine** (`app-emulation/wine-vanilla`/`wine-staging`/`wine-proton`,
  `virtual/wine`, `eselect wine`): `wine <exe>` with **`WINEPREFIX`**,
  **`WINEARCH`** (win32/win64, fixed at creation), **`WINEESYNC`/`WINEFSYNC`**,
  **`WINEDEBUG`**. 32-bit needs multilib + **`ABI_X86="32"`**. Setup via
  `wineboot -i`, `winecfg`, `winetricks <verbs>`. DXVK/VKD3D added per-prefix via
  `setup_dxvk install` / `setup_vkd3d_proton install` (`app-emulation/dxvk`,
  `app-emulation/vkd3d-proton`).
- **Graphics/runtime wrappers:** `gamescope -W w -H H [-w gw -h gh] -f [-F fsr -S
  scaler --sharpness N] [--hdr-enabled] --mangoapp -- <cmd>` (`gui-wm/gamescope`;
  FSR is now **`-F fsr`**, the old `-U` is gone); `gamemoderun <cmd>`
  (`games-util/gamemode`); **MangoHud**: `MANGOHUD=1`/`mangohud <cmd>` normally,
  but **inside gamescope use `--mangoapp`** (`games-util/mangohud[mangoapp]`), not
  the env var. Runtime tuning env: `DXVK_HUD`, `DXVK_FRAME_RATE`, `VKD3D_CONFIG`,
  `VKD3D_FRAME_RATE`.
- **Icons/desktop:** `wrestool -x -t 14 -n1 app.exe | icotool -x` (`app-arch/
  icoutils`). Wine's **winemenubuilder auto-writes `.desktop` files** to
  `~/.local/share/applications/wine/…` and icons to `~/.local/share/icons/hicolor/…`
  when an installer creates Start-menu shortcuts — **a source we can harvest.**
- **Wayland:** `winewayland.drv` is improving but **opt-in, not the default**;
  Proton still runs Xwayland. Xwayland is the reliable path in 2025–2026; prefer
  the Wine-Wayland driver only where a barrel opts in.

## 4. The barrel model

A **barrel** = a managed prefix + config, under `$XDG_DATA_HOME/hede/drydock/<id>/`:

- **runner**: `{kind: proton-umu | wine, version}` — Proton build name/codename
  for umu, or the `eselect wine` target for plain Wine.
- **arch** (win64/win32), **prefix path**.
- **verbs**: winetricks verbs installed (wine barrels).
- **dxvk/vkd3d**: state (wine barrels only — Proton has them built in).
- **env**: user env overrides.
- **programs**: each installed app = `{name, exe (path in the prefix), args,
  graphics profile, wm_class}`.

A **graphics profile** (per program): `{gamescope: off|{w,h,fsr,hdr,refresh},
gamemode: bool, mangohud: bool, dxvk_hud: str, fps_cap: int, esync/fsync: bool}`.

## 5. The launch pipeline (the crux — where "seamless" is won)

`drydock-run <barrel> <program>` assembles a **pure** (env, argv) pair, then execs:

1. **env** — `WINEPREFIX`, `WINEARCH`; `WINEESYNC/WINEFSYNC` per profile; DXVK/
   VKD3D tuning (`DXVK_HUD`, `*_FRAME_RATE`, `VKD3D_CONFIG`); for Proton:
   `GAMEID`, `PROTONPATH`, `STORE`, `PROTON_VERB`; `MANGOHUD=1` **only when not
   using gamescope**; plus the barrel's env overrides.
2. **argv** — composed outside-in: `gamemoderun` → `gamescope … --mangoapp --`
   → the runner (`umu-run` | `wine`) → `<exe> <args>`. gamescope's `--mangoapp`
   replaces the MangoHud env when present.
3. **exec** — spawn, inheriting the assembled env.

This assembly is the core deliverable — entirely pure and unit-testable (like
Gangway's `commands.py`, but richer). Executing it needs a real Wine/Proton/GPU,
so live launch is validated on a host, not in CI.

## 6. Desktop integration (the HeDE differentiator) — via Customs

Two complementary paths:

1. **Synthesize** (controlled): on registering a program, build a Customs
   `.desktop` (Exec → `drydock-run <barrel> <program>`), extract its icon with
   `wrestool`, set `StartupWMClass` and register it in the Customs identity map so
   the taskbar shows the right icon/title; associate the `.exe`/`.msi` MIME types.
2. **Harvest** (convenience): scan a barrel for the `.desktop` files wine's
   winemenubuilder already generated (installers create Start-menu shortcuts),
   and **adopt** them — rewrite their `Exec` to go through `drydock-run` so they're
   managed and consistent, folding in Customs identity/MIME. Installers do the
   discovery for us; Drydock makes the result native.

## 7. The Gentoo-native edge

A **prerequisites checker**: given a barrel's config, report exactly what's needed
and missing —
- Proton barrel → `games-util/umu-launcher` (**offer to enable the GURU overlay**
  via GeST's repos module) + `media-libs/…` Vulkan.
- Wine barrel → `app-emulation/wine-vanilla[abi_x86_32]` (+ **multilib /
  `ABI_X86="32"`** if a win32 prefix), `app-emulation/dxvk`/`vkd3d-proton` if
  toggled.
- Game mode → `gui-wm/gamescope`, `games-util/gamemode`,
  `games-util/mangohud[mangoapp]`.

The *check + report* is pure/testable (the atom+USE table is data). **Applying**
it routes through GeST's existing polkit'd software/USE core — the same path
every other GeST module uses. This is the piece no other tool has.

## 8. Runner strategy

**The runner is chosen per barrel, with no default** (*resolved*): `drydock
create <name> --runner {proton|wine}` is explicit. Proton-via-umu gives the
Steam-like "just works" (protonfixes + bundled DXVK/VKD3D + the SLR container);
plain Wine is the lightweight, fully-in-tree option (no GURU dep, no container).
One launch pipeline serves both — the runner only changes the env + the
executable — so requiring the choice costs nothing and keeps Drydock unopinionated
about games-vs-apps.

## 9. Buildable now vs. the locked door

- **Pure/testable now:** barrel model + config store; the launch env+argv builder
  (all §5 flag logic); Customs synthesis + wine-`.desktop` harvest/rewrite; the
  Gentoo prereq checker; the `drydock` CLI + `drydock-run` stub.
- **Locked door (host-only):** `wineboot` prefix creation, running installers,
  actually launching apps/games (real Wine/Proton/GPU/gamescope), and package/USE
  installs (root/polkit + real `emerge`). Same wall as Gangway's live client and
  the keyring daemon's real bus.

## 10. Phased roadmap

1. **Bottle model + launch pipeline** — the pure core (env+argv for wine & umu,
   graphics profiles), config store, `drydock`/`drydock-run` CLI. Unit-tested.
2. **Customs integration** — synthesize launchers + harvest wine `.desktop`s;
   icon extraction; identity/MIME.
3. **Gentoo prerequisites** — the checker + the GeST software/USE apply path
   (incl. offering the GURU overlay for umu).
4. **Bottle operations** (host-validated) — create prefix, run installer,
   winetricks verbs, DXVK/VKD3D setup.
5. **Game mode polish** — gamescope FSR/HDR presets, gamemode, mangoapp; the Qt
   management module (gated on the Qt frontend).
6. **Later** — sandboxing (bubblewrap + portals, like Bottles); install-script
   library; optional Lutris/Bottles prefix adoption.

## 11. Decisions

1. **Runner — chosen per barrel, no default** (*resolved*). `--runner
   {proton|wine}` is required at create time.
2. **Desktop entries — synthesize *and* harvest** (*resolved*). Synthesize a
   Customs launcher on register; `drydock scan <barrel>` adopts wine's
   auto-generated `.desktop`s, rewriting their `Exec` through `drydock-run`.
3. **umu (GURU-only) — offer to enable GURU** (*resolved*). Proton barrels work;
   the prereq checker offers to enable the GURU overlay (via GeST's repos module)
   and install umu when it's missing — overlay opt-in, explicit, never silent.
4. **Sandboxing — deferred** (*resolved*). v1 runs apps directly; bubblewrap +
   portals is a later phase (§10.6).

## 12. Non-goals

- **No new Wine/Proton/DXVK.** All adopted; we never fork a runtime.
- **No reimplementing the Steam runtime** — umu gives us the SLR container.
- **No anti-cheat promises** — kernel AC is out of our hands.
- **No game-library/box-art store** — Drydock runs *your* Windows software; it is
  not a storefront.
- **No Lutris/Bottles replacement** — we integrate/adopt, not compete, and stay
  the thin native path.

## 13. Testing

- **Pure/headless (CI):** launch env+argv for wine and umu across graphics
  profiles (gamescope wrapping order, `--mangoapp` vs `MANGOHUD=1`, DXVK/VKD3D
  env, esync/fsync); `.desktop` synthesis + wine-`.desktop` harvest/rewrite;
  prereq checker output vs. the atom/USE table; CLI dispatch with injected
  spawn/store.
- **Host-only (manual/tagged):** prefix creation, an installer run, a real
  app/game launch through the full pipeline, and a USE/package apply.
