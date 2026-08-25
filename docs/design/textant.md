# Design: Textant — the HeDE terminal

A first-class, HeDE-owned terminal emulator: Qt-native, no KDE, no GTK, themed
with the shell and integrated with the world/appearance system — the same way
SeFE is our file manager and Seahorse is our archive front. Named for the
**sextant** — the precision instrument you read the raw sky with, an expert's
measuring tool — folded together with **text**: a terminal *is* a text device.
The sextant supplies the logo and the maritime read; the pun puts the function
in the name. (It also quietly sanitizes the source word — `sextant` carries a
`sex` substring that `textant` does not, which is one less wart in a binary
name, a tab-completion, a log line.)

## Why build one (and why *not* for the reason you'd guess)

HeDE currently ships **foot** as the default terminal (labwc `Super+Return`, the
menu Terminal item, a hard `RDEPEND` in the hede ebuild). foot is excellent —
fast, tiny, and **toolkit-free** (Wayland + cairo + fcft, *no GTK, no Qt*). So
"avoid GTK" is **not** a reason to replace it: foot drags in zero GTK.

The real motivation is **ownership and integration**, the SeFE/Seahorse instinct:

- **Cohesion.** A HeDE terminal can wear the shell's glass — the same
  world-tinted acrylic surface (`#HelmPullout`-style), the labwc titlebar, the
  active-world accent — so the terminal reads as part of the desktop, not a
  bolted-on third-party app.
- **Integration.** It can consume `helm-theme`'s live re-tint on a world switch,
  honour the shared appearance config, and hook HeDE features (drag-a-file-in
  from SeFE, `gest`/`drydock`/`gangway` awareness) that a generic terminal can't.
- **A Qt-native default.** HeDE's shell is Qt; owning the terminal keeps the
  first-party surface coherent and under our control, versioned with HeDE.

foot stays the shipped default until Textant reaches parity — this is additive,
not a rip-and-replace.

## The decision: libvterm + Qt

Terminals are deceptively hard: pty handling, full VT/xterm escape-sequence
emulation, unicode width, reflow, scrollback, selection, performance. Three ways
to get the emulation, only one is right for us:

| Option | Verdict |
| --- | --- |
| **QTermWidget** (Konsole's widget, extracted) | ❌ drags KDE back in — defeats the purpose. |
| **Hand-roll the VT emulator** | ❌ a multi-year tarpit; re-solving a solved problem. |
| **libvterm** (the parser/screen library, as used by Neovim) + **Qt** for UI | ✅ lean, no KDE/GTK, bounded scope. |

libvterm owns the hard part (parse PTY bytes → maintain a screen model → fire
callbacks). Qt owns the part we care about (rendering, input, theming,
integration). This is the whole architectural bet.

## Architecture

```
  pty (forkpty + shell)
     │  bytes ↕ (QSocketNotifier on the pty fd)
  VTermSession  ── wraps libvterm ──┐
     │  screen model + damage/scrollback callbacks
  TerminalView (QWidget)            │  input: Qt key/mouse → pty bytes
     │  paints cells, cursor, selection, glass background
  MainWindow (title, config, tabs-later)
```

- **`pty.{h,cpp}`** — `forkpty()`/`openpty()`, spawn `$SHELL`, expose the master
  fd. A `QSocketNotifier` wakes us on output; `TIOCSWINSZ` on resize. No polling.
- **`vtermsession.{h,cpp}`** — owns a `VTerm*` + `VTermScreen*`. Feeds pty bytes
  in (`vterm_input_write`), drains pty output out (`vterm_output_read`). Registers
  the screen callbacks: `damage` (dirty cells → repaint), `movecursor`, `bell`,
  `settermprop` (title, cursor visibility), `sb_pushline`/`sb_popline`
  (scrollback). Keyboard input encoded via `vterm_keyboard_unichar`/
  `vterm_keyboard_key`.
- **`terminalview.{h,cpp}`** — a `QWidget` (not QML). `paintEvent` draws the
  visible screen: per-cell glyph via `QPainter` in a monospace font, fg/bg from
  the cell's colour (256 + truecolor), reverse/bold/underline attrs, the cursor
  block, and the selection overlay. Repaints are **damage-scoped**
  (`update(dirtyRect)`), never full-screen — that's how a QWidget terminal stays
  fast without a GPU path. Scrollback is a ring buffer of popped lines; a scroll
  offset shifts the render origin.
- **`config.{h,cpp}`** — font, palette, opacity, scrollback size, keybinds; read
  from the HeDE appearance/config surface (see below).
- **`main.cpp`** — `QApplication`, one `MainWindow`, wire the session to the view.

### Rendering & performance

Start with **QWidget + QPainter + damage regions** — correct and fast enough for
a daily terminal (foot itself is CPU-rendered with damage tracking). A **QRhi /
QOpenGL** glyph-atlas renderer is a *Phase 3* option if profiling shows the CPU
path can't keep up under heavy output (`yes`, `cat bigfile`). Do not start there.

Fonts via fontconfig/Qt `QFontDatabase` (monospace, configurable). Ligatures/
HarfBuzz shaping is Phase 3 — most terminal text doesn't need it.

## HeDE integration

- **Glass, like the shell.** The window is `WA_StyledBackground` +
  `WA_TranslucentBackground`; the terminal background is the world-tinted acrylic
  (reuse `helm::paintStyledSurface` / the appearance palette) at a configurable
  opacity, so it composites over the wallpaper like `#HelmPullout`. Default
  fg/bg/palette derive from the active world's accent via `applyAppearance`, and
  Textant calls `helm::watchAppearance()` to **re-tint live** on a world switch.
- **labwc SSD titlebar.** It's a normal xdg-toplevel — labwc server-side-decorates
  it (the `serverDecoration="yes"` rule), so it gets the HeDE titlebar for free.
- **Launched cleanly.** When spawned from the shell it must go through
  `helm::launchDetached`, which scrubs `QT_WAYLAND_SHELL_INTEGRATION` — otherwise
  Textant, being Qt, would inherit the shell's `layer-shell` integration and
  come up as a frameless layer surface (the exact Control Center bug). Being Qt
  makes this non-optional.
- **Default-terminal registration.** Once mature: swap the labwc `Super+Return`
  keybind + menu Terminal item from `foot` to `textant`, register as
  `x-terminal-emulator`, and have `helm-panel`'s Start-menu "Terminal" spawn it.
  Keep `foot` installed as a fallback until parity is proven on hardware.

## Packaging

- Source under `hede/src/textant/`; binary `textant`; a new
  `add_subdirectory(src/textant)` in `hede/CMakeLists.txt`.
- Build dep: `dev-libs/libvterm`. Runtime: same + Qt6 Widgets (already a HeDE
  dep). **No KDE, no GTK.**
- The hede ebuild keeps `gui-apps/foot` as the fallback terminal until Textant
  is the default; then foot moves to a soft/optional dep.

## Phasing (slices)

- **P0 — it's a terminal.** pty + libvterm + `TerminalView` paint + keyboard
  input + resize. Runs `$SHELL`, handles the common escape sequences, basic 16/256
  colour. Ugly but usable. Ship behind nothing; test in QEMU + on metal.
- **P1 — daily-driver.** Scrollback + wheel scroll, mouse selection +
  clipboard (primary + CLIPBOARD), truecolor, bold/underline/reverse, bell, window
  title (`settermprop`), a config file. This is the "I can stop reaching for foot"
  bar.
- **P2 — HeDE-native.** Glass background + world-tint theming + live re-tint,
  configured font/opacity from the appearance surface, URL detection
  (ctrl-click open), `launchDetached` correctness. Register as the default
  terminal (keybind/menu/`x-terminal-emulator`), foot → fallback.
- **P3 — polish/perf.** Optional GPU (QRhi) glyph renderer if needed, ligatures,
  sixel/kitty-image protocol, tabs *or* deliberately none (see non-goals).

## Non-goals (v1)

- **Tabs / splits / a multiplexer.** labwc already tiles windows and tmux exists;
  a v1 terminal is one pty per window. Revisit tabs only if there's real demand.
- **Sixel / image protocols, ligatures, GPU rendering** — Phase 3 at the earliest;
  none are needed to replace foot for the way HeDE is actually used.
- **A configuration GUI.** Config is a file (and, later, a Control Center module
  if warranted) — not a preferences panel in v1.
- **Reinventing VT emulation.** libvterm is the emulator; we never parse escape
  sequences ourselves.

## Name

**Textant** — a portmanteau of **sextant** + **text**. The sextant is the
precision instrument a navigator reads the raw sky with; framing the terminal as
an expert's measuring instrument is exactly the register we want, and it gives us
a ready-made logo. Folding **text** into it puts the function in the name — a
terminal is a text device — so the pun and the meaning are the same thing rather
than decoration bolted on.

Why it's more than a gag:

- **It sanitizes the source word.** `sextant` is `s-e-x-t-a-n-t`; `textant` drops
  the `sex` substring. One less wart in a binary name, a tab-completion, a log
  line, a docs heading.
- **`-ant` reads as an agent suffix.** Like assist*ant* / occup*ant* — "the thing
  that handles text." Even a reader who's never heard "sextant" gets a coherent
  word; the logo then rewards the ones who have. A two-layer name.
- **It's on-brand.** HeDE already runs one salty pun per tool (Barnacle winks at
  *binnacle*, the crab lineage) — a wordplay name here fits the fleet's culture
  where a straight-faced "Sextant" would be a touch too solemn.

Fits the nautical fleet (Helm, Seahorse, Hold, Gangway, Drydock, Flotilla,
Lantern, Barnacle). The one honest risk is the `-ant` ending nudging a reader
toward "text-*ant*" (the insect); the sextant logo is what defuses that. Final
call is the captain's — this is the chosen name, superseding the earlier
**Telegraph** working title.
