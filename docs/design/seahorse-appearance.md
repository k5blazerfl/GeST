# Seahorse (SeFE) — Appearance Overhaul

Implementation plan for SeFE's chrome: a default menu bar, a promoted status
logo, full biome theming, light & dark modes, and a painterly scene-framed
window. Locked from an iterated mockup pass (2026-08-20).

The one-line vision: **the chrome is the world, the content is glass.**

> **Status — SHIPPED.** All four phases landed on `main` on 2026-08-20:
> A (menu bar, #179), B (light/dark + follow-the-sun `mode = dark|light|auto`,
> #180), C (biome glass interior scoped to `#HelmAppWindow`, #181), and D (the
> frameless painterly scene chrome + `HelmTitleBar`, #182). Two deviations from
> the plan below, both intentional: the window **min/maximize/close controls
> landed on the right** (Windows-familiar, per the HeDE familiarity north-star)
> rather than the mockup's schematic left dots; and the interactive
> move/resize uses Qt's standard Wayland `startSystemMove` / `startSystemResize`
> path, still pending an on-device pass. Per-world scrim tuning, a day/night scene
> pair, and a compact header for small windows remain the parked follow-ups.

## The locked composition

The window is one continuous world scene forming a painterly **header** and
**footer**, joined by a thin scene **side trim**, with an opaque **glass content
body** floating inset between them.

```
┌───────────────────────────────────────────────┐  ← window scene (world art)
│  ● ● ●            captain — Seahorse           │  titlebar (drag + controls)
│  File Edit View Go Tools Help          ┌─────┐ │  menu bar
│  ← → ↑  [ home › captain            ]  │ 🌙  │ │  toolbar (nav + breadcrumb)
│                                        └─────┘ │  + 66px status logo (throbber)
│ ┌────────────────────────────────────────────┐│  ← glass body (light/dark),
│ │ Places │  Name          Size  Type  Modified││    inset ~7px (side trim shows
│ │ Home ● │  📁 Downloads    —   Folder …       ││    the scene)
│ │ …      │  🗜️ backup.zip  48M  ZIP    …        ││
│ └────────────────────────────────────────────┘│
│  5 items · 1 selected      /home/captain/…     │  footer: status over the scene
└───────────────────────────────────────────────┘
```

Held decisions:

- **Menu bar on by default** — `File · Edit · View · Go · Tools · Help`, all
  wired to SeFE's existing `QAction`s. Hideable via `View → Menu Bar` (Ctrl+M).
- **Tools** menu holds the interop — Run in Drydock · Share Folder to Session
  (Gangway) · Open with Hold. Selection-aware (grey out when N/A).
- **Status logo** — the moon-and-Helm throbber promoted to **66px** on the right
  of the chrome (spins on work, rests on tonight's moon, clicks Home). Buffer
  ~6px top / ~10px bottom.
- **Painterly header + footer** — the active world's scene fills the top chrome
  (titlebar/menu/nav/logo) and the bottom status band; controls float over it
  with a legibility scrim. One continuous scene → **no slice seams** and full
  edge theming for free.
- **Light & dark modes** — the accent hue is constant; the glass **body** flips
  light/dark. The header/footer stay the scene (a painterly "photo" band) in both.
- **Tight corners** — 5px on panels, 3px on inner controls, as a global token.

## Menu → action map (all actions already exist in `window.cpp`)

| Menu | Items |
|------|-------|
| **File** | New Folder (⌃⇧N) · Open · Open With… · ─ · Extract Here · Extract To… · Compress to .zip · ─ · Properties (⌥↵) · Close (⌃W) |
| **Edit** | Cut · Copy · Paste · ─ · Rename (F2) · Delete (Del) · ─ · Copy Location (⌃⇧C) · Select All (⌃A) |
| **View** | Details · Icons · ─ · Refresh (F5) · Columns ▸ · ─ · ✓ Menu Bar (⌃M) |
| **Go** | Back (⌥←) · Forward (⌥→) · Up (⌥↑) · ─ · Home · Desktop · Documents · Downloads · Pictures · Music · Videos · ─ · Computer |
| **Tools** | Run in Drydock · Share Folder to Session · Open with Hold |
| **Help** | About Seahorse |

Reuse the existing `QAction`s so the menu bar, toolbar, and context menu stay in
sync (one action, three surfaces). The only new actions: `Menu Bar` (checkable,
Ctrl+M) and `About Seahorse`.

## Phasing

Ordered so each phase ships value and de-risks the next.

### Phase A — Menu bar · status · logo (additive, low-risk)
Works with the current labwc decoration; no window-management change.
- Add a `QMenuBar` to `SefeWindow`, populated from the existing actions per the
  map above. Add the `Menu Bar` toggle + `About` dialog.
- Promote `HelmThrobber` to a 66px right-corner widget with the top/bottom buffer.
- **Ships the "familiar by default" win on its own.**

### Phase B — Light & dark mode (shell-wide, not just SeFE)
- `hede.conf [appearance] mode = dark | light | auto`.
- `applyAppearance()` / `buildPalette(bool dark, accent)` / `styleSheet(bool dark,
  accent)` already take the flag — wire the config read, plus a shell quick-toggle
  and an Appearance-module control. `watchAppearance()` gives the live flip.
- **`auto` = follow-the-sun** — light after sunrise, dark after sunset; pairs with
  the moon throbber (which already tracks the lunar phase). Compute from date +
  a coarse location/latitude or a fixed civil-twilight table; no network.

### Phase C — Biome glass interior
- SeFE chrome surfaces (menu bar, toolbar, Places, status) take the world's
  `barTint()` glass + accent via `styleSheet(dark, accent)`.
- Confirm SeFE (an xdg-toplevel, not a layer-shell bar) actually picks up the
  shared shell stylesheet — the known gap, since `styleSheet`/`barTint` were built
  for the glass-bar surfaces.

### Phase D — Painterly scene chrome (the headline)
The big architectural piece. SeFE draws its own frame so the scene can span
titlebar → menu → toolbar → content → status as **one Qt-painted region**
(crossing the usual decoration/content boundary is what makes it seamless).
- Make SeFE a **frameless / client-decorated** top-level: it paints a custom
  titlebar (title, window controls) and the header/footer bands itself.
- Paint the **active world's scene** once as the window background; the header
  (top), footer (bottom), and the ~7px side margins reveal it. The content body
  is an opaque glass panel inset within.
- Legibility scrims: top-darkening on the header, bottom-darkening on the footer;
  controls get translucent-glass backgrounds. Light text in the bands regardless
  of body mode.
- Window management for a frameless Wayland toplevel: wire move (titlebar drag →
  `xdg_toplevel` move), edge/corner resize, and min/max/close buttons; keep
  keyboard shortcuts and tiling behaviour intact.
- **Scene source:** the active world's `data/worlds/<id>/wallpaper.png` (or a
  purpose-cut header/footer band), NOT the nine-patch `frame.png`. The header/
  footer approach supersedes the nine-patch trim *for SeFE's chrome* — the
  nine-patch `frame.png` frames stay in use for labwc/other decoration paths.

## Parked / follow-ups

- **Day/night scene pair per world** — a light (day) variant so the header/footer
  brighten with the mode, not just the body. Same pipeline, a second render per
  world.
- **`make-frame.py` textured trim** — today it paints the titlebar from the scene
  but fills the L/R/bottom borders with *solid accent* (verified: every trim pixel
  is flat `#3aa6c4`). If the nine-patch path is kept for other apps, change it to
  sample the scene at each edge. (Moot for SeFE once Phase D uses the scene
  directly.)
- **Compact header variant** for small windows — collapse the banner to a single
  titlebar + menu/nav row.

## Risks & watch-items

- **Frameless CSD on Wayland** — move/resize/snap must be handled manually and not
  regress the labwc SSD integration other HeDE apps rely on. Prototype the
  toplevel move/resize first.
- **Legibility across all worlds × light/dark** — scrim tuning + contrast checks
  per world so controls and status text stay readable over any scene.
- **Header height** — taller than a plain titlebar; needs the compact variant for
  small windows (see parked).

## Files touched

- `hede/src/sefe/window.{h,cpp}` — menu bar, `Menu Bar` toggle, About, status,
  the 66px logo corner, and (Phase D) the frameless chrome + scene painting.
- `hede/src/sefe/` — a new header/footer chrome widget (Phase D).
- `hede/src/appearance/` — `mode` (dark/light/auto) in `applyAppearance()` +
  `styleSheet()`; the follow-the-sun calc.
- `gest` Appearance module — the light/dark toggle, if surfaced there too.
- `hede/data/worlds/` — scene sourcing for the header/footer bands.

## Relation to existing work

- Accent theming is **already wired** (`applyAppearance()` + `watchAppearance()` →
  palette Highlight = biome accent, live on world switch). Phases B/C/D build on it.
- The nine-patch `frame.png` + `helm` decoration plugin remain the decoration path
  for labwc/other apps; SeFE's Phase D chrome sources the world scene directly.
- Ships on top of the merged SeFE (H3/H4) + throbber work.
