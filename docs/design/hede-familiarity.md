# Design: HeDE — the familiarity north-star (Windows muscle memory by default)

*Status: standing principle + acceptance criteria · Scope: where every HeDE control lives out of the box, and the rule for when we're allowed to differ · Applies to: the shell (panel/launcher/tray/notifications), window management, and the ship-themed apps (Seahorse, Porthole, …) · Relates to: [desktop-environment.md](desktop-environment.md), [qt-frontend.md](qt-frontend.md)*

> **North-star: respect Windows users' muscle memory — put controls where their
> hands already expect them — then earn the right to differ.**

## The insight

People don't learn *interfaces*, they learn *locations*. Moving desktops is like
getting into an unfamiliar car and finding the wiper control moved from the stalk
to a dash button — a **"mode error."** The cost isn't difficulty, it's the
betrayal of learned motor programs. That's why Windows refugees bounce off Linux
desktops: everything is "one stalk over."

So HeDE's **default resting position is Windows conventions**, and that is not a
claim they're *better* — they're just where hands already go. Honoring them is
**free familiarity**. We then differ only where it earns delight (the
nautical/Helm identity, tiling, real package management, the Hiedi assistant) —
the way a new car is forgiven a relocated stalk *because* it adds adaptive cruise
or a HUD.

## The one hard rule

**Windows-familiar is the out-of-box default with zero archaeology.** Never make
familiarity a toggle buried three menus deep ("install this extension, edit a
dotfile"). The target user must never have to *discover* that the desktop can
behave the way their hands expect — it already does.

Target user context: someone coming from the Windows-majority world (the
maintainer's own reference: Windows only at work, for Adobe + MS Word parity with
coworkers). HeDE is a first-class Linux desktop for *that* person.

## Acceptance checklist (muscle-memory placements)

Hold every surface against this. ✅ = built and honoring it; ⏳ = not designed yet,
watch when we get there.

| Convention | Where it lands in HeDE | Status |
|---|---|---|
| Start menu **bottom-left** | ⎈ launcher | ✅ |
| Clock + system tray **bottom-right** | panel | ✅ |
| Window buttons **top-right**, order **Min → Max → Close**, close reddens on hover | window decoration | ✅ |
| **Notifications bottom-right**, above the taskbar | toasts | ✅ |
| **Properties at the bottom** of the right-click menu (after a separator) | context menu | ✅ |
| Control-Panel category names → Gentoo concepts (Add/Remove Programs → Programs & Updates, etc.) + intent search | GeST IA | ✅ |
| `Ctrl+C / V / X`, `Ctrl+Z`, `Alt+F4`, `Alt+Tab`, `F2` rename, `Del`, `F5` refresh | Porthole (terminal) + apps | ⏳ |
| Typeable **address / path bar** in the file manager | Seahorse | ⏳ |
| **Double-click opens, single-click selects** (Windows), *not* single-click-open (KDE default) | file manager + desktop icons | ⏳ |
| Drag window to top = maximize; to a side = snap | compositor | ⏳ |
| Taskbar: click app to focus/minimize; pinned + running apps | panel | ✅ (behavior TBD) |

### The ⏳ traps (where Linux desktops classically betray the muscle memory)
- **Terminal copy/paste:** Porthole must map `Ctrl+C` to *copy* when text is
  selected and *SIGINT* otherwise — never require `Ctrl+Shift+C`.
- **File manager:** ship the **typeable address bar** and **double-click-to-open**
  as defaults; don't hand the user single-click-open + breadcrumb-only.
- **Rename** on `F2`, **refresh** on `F5`, **new folder** on `Ctrl+Shift+N`.

## How we're allowed to differ

Identity and capability, never placement of the everyday controls:
- **Visual identity** — the painterly scene frames, glass surfaces, per-world
  themes. These sit *on top of* conventional layout (title left, buttons top-right).
- **Net-new power** — tiling/snapping, real package management, the Hiedi
  assistant, nautical app naming. New value the Windows user *gains*, not learned
  motions they *lose*.

The test for any proposed deviation: *does it move a control the user's hand
already knows, or does it add something new next to it?* Move → no. Add → yes.

## Reference — the Windows-classic touchstone

For the *exact* feel of Windows-classic — the Start menu layout, the file-manager
chrome (up-button, status bar with selected count/size + free space) — we treat
**[Open-Shell](https://github.com/Open-Shell/Open-Shell-Menu)** (MIT; the
community continuation of Classic Shell) as the living behavioural spec. It maps
onto **`helm-menu`** (the Start menu) and **SeFE**'s Explorer chrome
([sefe.md](sefe.md)). It is a **reference, not a dependency**: Windows-only C++
(Win32/COM), so we port concepts into Qt, not code — and we mine its **defaults**,
not its huge toggle surface, because here familiarity *is* the default.
