# GeSI Repositories & Mirrors — the Handbook's "Repo Mirror Selection", GeSI-native

Status: **implemented** (installer-repos-mirrors). Triggered by baremetal dogfood,
2026-08-25: the installed system's Portage repos/mirrors weren't fully owned by GeSI,
so it couldn't cleanly update itself.

## Motivation

Three gaps surfaced once a real HeDE box booted:

1. **Amphitheater present but never refreshed.** The overlay's `repos.conf` was written
   `auto-sync = no`, so `emerge --sync` never pulled new HeDE/GeST — day-2 desktop
   updates were stranded at the ISO's snapshot.
2. **The main gentoo repo looked "missing."** GeSI never wrote an explicit
   `repos.conf/gentoo.conf`; it leaned on the stage3's *built-in* default
   (`/usr/share/portage/config/…`). It works at install time but is invisible,
   unmanaged, and mirror-less.
3. **No mirror selection.** `GENTOO_MIRRORS` was never set (and couldn't be until the
   `WriteMakeConf` no-op was fixed — that writer wasn't running), so distfiles came off
   Gentoo's default rotation with no regard for proximity/speed.

The Handbook's [Repo Mirror Selection](https://wiki.gentoo.org/wiki/GENTOO_MIRRORS)
covers exactly this: choosing distfile mirrors (`GENTOO_MIRRORS`) and the sync source.
GeSI should too — **staying firmly on Gentoo's own mechanisms** (no fork of the infra).

## Principle — Helm's plan, firmly Gentoo-based

Helm supplies *opinionated defaults* (auto-pick the fastest mirrors; refresh HeDE/GeST
by default), but every mechanism is standard Gentoo: `repos.conf` `sync-uri`,
`GENTOO_MIRRORS`, optional `PORTAGE_BINHOST`. Nothing here diverges from a plain Gentoo
system — an admin can inspect and change it all by hand.

## What ships

**Core — `gest/core/portage/mirrors.py`** (pure + a light probe):
- `Mirror` / `CATALOG` — a bundled offline snapshot of well-known official mirrors,
  region-tagged, so selection works with no live mirror list (offline-first, like the
  timezone list). Refreshable against `api.gentoo.org/mirrors/distfiles.xml` later.
- `probe_latency()` — a TCP-connect timing probe (no download), injected in tests.
- `select_mirrors()` — auto-pick the fastest reachable mirrors, falling back to the
  regional default (US-East, matching the audience) when offline.
- `render_gentoo_mirrors()` / `gentoo_repos_conf()` — the pure make.conf / repos.conf
  renderers.

**Engine:**
- `WriteReposConf` (new, state-marked, before `SyncTree`) writes an explicit
  `repos.conf/gentoo.conf`: `location=/var/db/repos/gentoo`, the chosen `sync-uri`,
  `auto-sync = yes`. Also points *this install's* own `emerge --sync` at the fast mirror.
- `WriteMakeConf` renders `GENTOO_MIRRORS` from the plan (empty → Gentoo's rotation).
- `desktop.repos_conf()` (Amphitheater) flips to **`auto-sync = yes`** so HeDE/GeST
  refresh by default.
- `InstallPlan` / `InstallSelections` gain `gentoo_mirrors`, `sync_uri`, `sync_type`.

**UX — Get Online gate (auto-pick, folded in):**
- The network warm-up (and the Get Online gate) run `select_mirrors()` in the
  background once online — no prompt. The **Mirrors** row shows the pick
  (`mirrors.mit.edu +2 (auto-picked)`), with **Re-pick fastest mirrors** and a manual
  **Choose mirrors…** checklist. Offline → the row reads "Gentoo default rotation".
- Placed at Get Online because mirrors are a networking/download concern; the auto-pick
  runs from the same warm-up so it happens even when Get Online is skipped (already
  online).

## Relationship to the WriteMakeConf fix

`GENTOO_MIRRORS` rides `WriteMakeConf`, which was a no-op until the state-marker fix
(the firmware-mask root cause). This feature stacks on that fix.

## Non-goals / follow-ups

- **Live mirror-list refresh** (`distfiles.xml`) — the catalog is a curated snapshot for
  now; growing/refreshing it is a follow-up.
- **PORTAGE_BINHOST as a Helm binary source** — the Amphitheater/B2 binhost could be a
  default binary source; wired via standard `binrepos.conf` when we turn it on.
- **Per-download-latency ranking** (vs connect-time) — connect-time is enough to rank
  proximity cheaply; a size-timed probe could refine it.
