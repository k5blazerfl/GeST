# HeDE Default Theme — the packaged UI language

Status: **design contract** · Companion to [hede-familiarity](./hede-familiarity.md)
and the [systemd stack](./hede-systemd-stack.md) · Tokens:
[`assets/hede-tokens.yaml`](./assets/hede-tokens.yaml)

This document packages the whole HeDE visual language into one theme so the
shell and every GeST module render the same way. It is the contract the
systemd-stack implementation builds against: greeter, session chrome, and the
Control Center all read these tokens and components.

The art itself is produced locally through the **hiedi "helm-titlebar-skins"
Voyage** (SDXL via ComfyUI on the Strix Halo `gfx1151` GPU, `gemma4:12b` for
prompt-writing and vision QA — fully offline). The bundles live at
`Voyages/helm-titlebar-skins/resources/dist/*.helmtheme`.

## What "the theme" is

Three layers, packaged together:

1. **Tokens** (`hede-tokens.yaml`, schema `helm.theme/0.1`) — fonts, radii,
   spacing, motion, the three surface materials, and the accent *role*.
2. **Component contracts** — the locked rules for every surface (below).
3. **World skins** (schema `helm.world/0.1` / `helm.skin/0.4`) — the painterly
   art + palette. One **accent per world** re-tints every surface at once.

A world is `{frame scene, wallpaper scene, panel art, accent, bar tint}`.
Switching worlds swaps art and re-tints the entire shell off the single accent —
no per-surface recolor. Default world: **Harbor** (Mistreef skin, teal).

| World | Skin | Accent | Feel |
|-------|------|--------|------|
| Harbor | `mistreef` (+ `palmshore` alt) | teal `#3aa6c4` | soft, hazy, light water |
| Emberforge | `emberforge` | ember `#c8632f` | forge-lit, warm, ocean |
| Stormwatch | `stormwatch` | slate `#5b7a8c` | cold, overcast, open sea |

## Three materials

Everything is built from one of three tiers (see `surfaces:` in the tokens):

- **Solid** — opaque bodies: window content, the Manifest organizer's light
  panel (`#f6fafb`).
- **Glass** — the bar and most chrome: translucent, blurred, world-tinted, with
  the **silver border** (`rgba(255,255,255,.22)`) and a top highlight.
- **Acrylic** — pullouts, launcher, tab strips: heavier blur so the **wallpaper
  reads through**.

Corners are tight and square-leaning (3–8px). Accent is a **role**, not a fixed
color — it drives selection, focus rings, toggles, sliders, links, active tabs,
primary buttons, and the shut-down cue, and is supplied by the active world.

## Component contracts (locked)

### Window decoration — 9-slice scene frame
Keep the painterly art; slice it into a resizable frame. `slice: 44`, `fill`
(frosted center at `0.72` over the body), border `30/8/8/8` (tall titlebar,
minimal reveal on the other three edges), edges **stretch** with **bevel + seam**
detailing. Mirrors `decoration_art` in `helm.skin/0.4`, so any skin drops in.

**Window buttons are edgeless** — glyph only until hover ("nothing is there").
Square, `radius 3`, `24×20`, order min/max/close; min/max hover to a glass chip,
**close hovers red**.

### The pullout standard
Everything that comes off the bar obeys one rule: it **emerges from behind the
bar**. The bar sits in front (higher z-index); the pullout's bottom edge is
**flat and borderless** (tucks behind the bar), with the silver border on top +
sides only and 7px top corners. It anchors to the **left edge of its trigger**.
This governs the launcher, the Hatch, group columns, tray applets, and quick
menus — they all read as attached to, and growing out of, the bar.

### The bar + pin model
One glass bar, tight corners, edgeless pin tiles. **No grouped system tray** —
applets (wifi, sound, battery, calendar, notifications…) live as **pins** in the
same single reorderable stream as apps. Apps launch/focus (right-click = jump
list); applets open a pullout. Only the **clock is anchored**.

**Groups** are movable buttons (not pinned by the clock): left-click emerges a
column list (anchored to the group's left edge); right-click is a quick menu
(Expand-in-bar / Manage…). Actually *organizing* pins happens in the dedicated
**Manifest window** — the bar itself stays simple.

### The launcher (⎈)
Adopts **Open-Shell**'s Windows-7 **two-pane** layout (the reference classic
Start menu — see [Open-Shell provenance](#open-shell-provenance)) in the Helm
glass skin. Emerges from the ⎈, acrylic, tight corners.

The **menu style is a setting** (mirroring Open-Shell's Menu Style), a
conditional variant off the same tokens: **`win7_two_pane`** (default, below),
**`classic`** (a single dense column with the signature vertical caption strip;
All-apps and jump lists **fly out** as cascading submenus rather than expanding
in-place; power pinned at the bottom), and **`classic_two_column`** (XP-style —
pinned + recent programs left, customizable system links right). All three
re-tint per world.

- **Left pane — apps & search:** a **Pinned** list, a separator, then
  auto-tracked **Recent** (MRU/MFU) programs, then **All apps ›** which expands
  **in-place** in the left pane (not a fly-out), and a **search box at the
  bottom**. Search focus is a setting (auto-focus / arrow-reachable /
  **Tab-only**, so arrow keys navigate the menu as if the box weren't there).
  Each program shows a right-arrow **jump list** on hover.
- **Right pane — places & system rail:** the user **avatar** at top, then the
  places (Home, Pictures, Music, Computer), a separator, **Control Center**
  (GeST) + **Settings**, then **Run… / Help**, and a split **Power** button
  bottom-right (Sleep / Restart / Log out / Lock / Shut down fly-out).

Windows-familiar by default per [hede-familiarity](./hede-familiarity.md):
Control Center sits where Control Panel does, Power sits bottom-right. Session
and power actions are logind calls in the `systemd --user` session. Search
sources **`.desktop`** entries (Name/GenericName/Keywords/Exec) + **`$PATH`**
binaries + a file index (Tracker/`plocate`) with client-side **fuzzy** ranking;
jump lists come from **`.desktop` Actions** + `recently-used.xbel`.

### The Hatch
Full-width quake-style terminal pullout (Porthole inside), emerges from the bar,
F12 toggle, grip-resize. Porthole honors the **Ctrl+C rule** (copy only with a
selection; otherwise interrupt).

### The Manifest window
The pin organizer as a **dedicated window** (scene frame, solid light body):
live bar preview, draggable group cards, editable names, per-pin show-on-bar
eye, +New group. GeST-module-ready.

### In-window controls & surfaces
Tabs use an **acrylic strip** with the **active tab bleeding into the content**;
toggles/sliders/selection/focus rings/primary buttons all take the accent.
Toasts anchor bottom-right (acrylic); context menus put **Properties** at the
bottom (Windows-familiar); privileged dialogs carry a polkit accent shield.

## Open-Shell provenance

The launcher's information architecture and several interaction patterns are
pulled from **[Open-Shell](https://github.com/Open-Shell/Open-Shell-Menu)**
(formerly Classic Shell), the reference open-source classic Windows Start menu.
Open-Shell is **MIT-licensed**, so its design *and* source assets are reusable.

What we pull:

- **The Windows-7 two-pane IA** (§ launcher) — the single strongest
  familiarity win, and the reason to reference Open-Shell at all.
- **Its skin parameter model**, which informs `hede-tokens.yaml`: per-bitmap
  **9-slice** metrics (`_slices_X/Y`), **4-state color quads** (normal / hover /
  disabled / drag-target), a glass **opacity** keyword, **mask-recolor** (one
  grayscale bitmap re-tinted at runtime from the accent — how a world re-tints
  cheaply), and **conditional variants via toggles** (icon size, caption,
  two-column) encoded in one token set.
- **Interaction behaviors**: live search-as-you-type, the Tab-only search-focus
  option, right-arrow jump lists, drag-to-pin/reorder, MRU/MFU recents.

What we do **not** pull:

- **No code.** Open-Shell is C++/ATL/WTL on Win32 + COM + GDI/DWM — nothing is
  portable to Wayland/Qt. We reimplement the patterns.
- **No Windows-look bitmaps.** Its Aero/Win7/XP skins recreate Windows chrome
  (trade-dress risk independent of MIT). We author our own nautical Helm art via
  the [[helm-titlebar-skins-voyage]] and keep the Helm skin.
- **Not the compiled `.skin` DLL packaging** (a resource-only PE) — Open-Shell's
  own users ask for loose directories instead; our `.helmtheme` bundles already
  are manifest + loose PNGs.

## How it's consumed

- **The shell** reads `hede-tokens.yaml` for materials/accent/geometry and the
  active `*.helmtheme` for art. World switch = swap skin + re-tint off one accent.
- **GeST modules** render controls from the same tokens, so the Control Center
  and the desktop match. When the Qt frontend (the `qt` USE flag) is built
  embeddable, HeDE reuses GeST as its Control Center with this exact language.
- **The greeter / lock** (a systemd unit) uses the Harbor world by default so
  first boot already looks like the desktop.

## Provenance

All art is generated locally and reproducibly via the hiedi Voyage; each skin
carries its prompt model, pipeline, and QA score in its `helm.skin/0.4`
manifest. Nothing here depends on a network service at build or run time.
