# Design: Hold — the archiver, tightly integrated into Seahorse

*Status: charting (2026-08-19) · Scope: HeDE's archive manager AND how it plugs
into Seahorse (SeFE) — the engine, the in-place browsing, the app boundary ·
**Revises** SeFE's "archive browsing is a non-goal" (see [sefe.md](sefe.md)):
SeFE gains archive browsing *via the shared Hold engine* · Depends on:
`hold-core` (new), `libarchive` · Relates to: [sefe.md](sefe.md),
[desktop-environment.md](desktop-environment.md),
[hede-familiarity.md](hede-familiarity.md)*

> **Status update (2026-08-20): SHIPPED — then H4 folded into Seahorse.** All four
> phases (H1 `hold-core` → H2 quick actions → H3 browse-in-place → H4) shipped, and
> H4 (the standalone `hold` app) was then **folded into Seahorse** (#184): there is
> **no separate Hold binary**. Its rich ops — Extract Selected / Extract All from
> inside a browsed archive — live in SeFE, and Seahorse is now HeDE's archive file
> handler. The "Hold-the-app" / "Open with Hold" / app-boundary sections below are
> the original plan-of-record; read them as history. Archive support continues in
> [archive-support.md](archive-support.md) (Seahorse → a full in-place manager).

> **Hold** is HeDE's archiver, but its centre of gravity is *inside Seahorse*:
> an archive is a **browsable folder** (Windows "compressed folder" familiarity),
> backed by a shared engine both apps speak. Hold-the-app owns the heavy path
> (passwords, formats, create wizard); Seahorse owns the everyday path.

## Seahorse is a capital ship

Seahorse is not the flagship — but it is a **capital ship** of the fleet, and its
importance must not be understated (a fleet has several capital ships that aren't
the one the admiral sails on). It is where the user actually *lives*, and the
other vessels dock at it rather than the reverse:

- **Drydock** — double-click a Windows `.exe` in SeFE → runs in Drydock.
- **Gangway** — right-click a folder → shared into the RDP session.
- **Hold** — an archive is a folder you walk into; select files → compress.

So SeFE is HeDE's **integration hub**. Every "I have a *thing*, do the right
action" flows through it. That is why Hold integrates *tightly* — a loose
"opens in another window" handoff would waste the hub. The tighter Hold binds to
the capital ship, the more the whole fleet feels like one vessel.

## The tight model: archives are folders

The loose version: double-click `photos.zip` → a separate archiver window. The
**tight** version (what we build) mirrors Windows compressed folders:

- Double-click `photos.zip` and you are **inside it**, in the *same* SeFE
  window — same Places pane, same address bar showing `photos.zip › vacation`,
  same details/icons views, same selection + context menus.
- Open a file inside → it is extracted on demand to a temp dir and opened.
- "Extract here" / "Extract to…" drop real files out; a selection → "Compress
  to .zip".

Nothing about the window changes when you cross into an archive — that seam is
the whole point.

## Architecture: `hold-core`, shared

The seam that makes it tight *without duplicating archive logic* is a shared
library — **`hold-core`** (a HeDE `helm::` lib, the same pattern as
`helm-theme-lib` / `helm-apps` / `sefe-lib`):

- `list(archive) → entries` (path, size, isDir, mtime)
- `extract(archive, entry | all, dest)`
- `create(files, archive, format)`
- format sniff + a password callback.

Backed by **libarchive** — one C dependency that reads zip/tar/7z/rar/… and
writes zip/tar. (Decision: libarchive over shelling `bsdtar`/`7z` — one linked
engine, real streaming, structured errors, no argv-injection surface.)

Both apps link it:

- **Seahorse** → in-place browsing + quick extract/compress. It speaks archives
  *natively*, not by shelling to a black box.
- **Hold-the-app** → the standalone experience over the *same* core.

## Seahorse touchpoints (concrete, against the shipped code)

- **Model swap on entry.** `SefeWindow::navigateTo` (window.cpp:219) detects an
  archive path — or a path *inside* one, e.g. `…/photos.zip/vacation/` — and
  swaps the views' model from `QFileSystemModel` to a new **`ArchiveModel`**
  (`QAbstractItemModel` over `hold-core` listing). Places, address bar, views,
  selection, context menus are reused unchanged; the breadcrumb naturally reads
  `photos.zip › vacation`. Back/Forward/Up cross the FS↔archive boundary in one
  history stack.
- **`openIndex`** (window.cpp:241) — where we already branch `.exe`→Drydock,
  add: an archive path → navigate *into* it; a file *inside* an archive →
  `hold-core` extracts to temp + `QDesktopServices::openUrl`.
- **Context actions** — reuse the existing action/menu scaffolding: on an
  archive → "Extract here", "Extract to…", "Open with Hold"; on a selection →
  "Compress to .zip…".
- **Status bar** — inside an archive, show entry count + uncompressed size
  (pairs with the classic-Explorer status bar already referenced from
  [hede-familiarity.md](hede-familiarity.md)).

## Where Seahorse stops and Hold-the-app starts

SeFE does the lightweight, inline 90% — **browse, open-an-entry, extract,
quick-zip**. Hold-the-app owns the rich 10%, reached via "Open with Hold" /
"Compress… (advanced)":

- passwords / encryption, split & multi-volume archives,
- format-specific options, a create wizard,
- batch progress for large jobs.

Same philosophy as SeFE↔Drydock: tight for the common path, a real app for the
heavy path — which is also *why Hold earns its own binary*.

## Phasing (slices)

1. **H1 · `hold-core`** — the libarchive engine (list/extract/create) + tests on
   fixture archives. Headless, testable; the foundation both apps consume.
2. **H2 · SeFE quick actions** — "Extract here / to…", "Compress to .zip" via
   `hold-core`. Immediate value, **no model surgery**.
3. **H3 · SeFE browse-in-place** — the `ArchiveModel` + archive-aware navigation
   / extract-on-demand-open. **The flagship-tight experience**; the largest
   build (a nav state machine that seamlessly crosses FS↔archive in one window).
4. **H4 · Hold the app** — a standalone window over `hold-core` for the rich ops
   + the handoff target from SeFE.

Sequenced so H2 lands usable value before the big H3 lift — but **H3 is in the
v1 vision, not deferred**. Go big.

## Decisions & non-goals

- **Engine: libarchive** (decided above).
- **Tightness: browse-in-place (H3) is v1**, not a "later maybe."
- **Mutation boundary:** SeFE is **read + extract + create-new** only.
  Mutating an *existing* archive in place (delete/add entries) means rewriting
  the whole archive (libarchive has no in-place edit) — that lives in
  Hold-the-app, not in the SeFE inline path. This is a deliberate boundary, not
  a gap.
- **Non-goals (v1):** nested-archive drill-in (an archive inside an archive),
  archive repair, and cloud/remote archives.
