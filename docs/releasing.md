# Releasing (Tidelock)

A release is: **bump the version, tag, push.** CI (`.github/workflows/overlay-sync.yml`,
on any `v*` tag) does the rest — do **not** hand-create packaging/overlay commits.

```sh
# from main, after merging everything for the release
$EDITOR pyproject.toml gest/__init__.py     # bump version = "X.Y.Z"
git commit -am "release: vX.Y.Z — <summary>"
git push origin main
git tag vX.Y.Z && git push origin vX.Y.Z     # fires overlay-sync
```

## What the tag fires

One GeST tag ships **both** packages:

| Target | Automated by | Needs |
|---|---|---|
| **gest ebuild** — authoritative overlay (`packaging/overlay/`, this repo) | `release-overlay.py` (built-in `GITHUB_TOKEN`) | always runs |
| **gest ebuild** — lean Amphitheater overlay | `release-overlay.py --push` | `AMPHI_DEPLOY_KEY` secret |
| **hede source** — mirror `hede/` → `k5blazerfl/HeDE` (`main` + `vX.Y.Z` tag) | `mirror-hede.py --push` | `HEDE_DEPLOY_KEY` secret |

Each external step **skips with a notice** if its key is absent, and the workflow
still succeeds. Both keys are **SSH deploy keys** with write access to their repo,
added under repo Settings → Secrets → Actions.

## Why the HeDE mirror

HeDE is developed here in **`GeST/hede/`** (canonical), but its ebuild builds from
the standalone **`k5blazerfl/HeDE`** repo, and `gui-apps/hede` in the Amphitheater
overlay builds from *that*. Nothing carried `hede/` across, so a `hede/`-only
change landed in GeST but never shipped — that was the manual step. The mirror
makes the HeDE repo a byte-for-byte copy of `hede/` at the tagged commit
(`GeST/hede` is the source of truth; direct edits to the HeDE repo are
overwritten) and tags it, so:

- the live **`hede-9999`** ebuild (git-r3 on HeDE `main`) tracks GeST immediately, and
- the versioned ebuild's `SRC_URI` (`HeDE/archive/.../vX.Y.Z.tar.gz`) resolves.

## Still manual (next increment)

The Amphitheater **`gui-apps/hede`** *versioned* ebuild (bump + Manifest DIST of the
HeDE tag tarball) is not yet generated automatically — a natural extension of
`release-overlay.py`'s Amphitheater sync. Consumers on `hede-9999` (live) get the
change from the mirror alone; versioned `gui-apps/hede` consumers need that bump.

## Dry runs

Both generators write nothing without `--push`:

```sh
packaging/release-overlay.py X.Y.Z            # shows the gest ebuild/Manifest it would write
packaging/mirror-hede.py X.Y.Z                # clones HeDE read-only, shows the mirror diff
```
