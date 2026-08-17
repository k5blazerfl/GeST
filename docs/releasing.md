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
| **hede ebuild** — Amphitheater `gui-apps/hede` (versioned) | `amphi-hede.py --push` | `AMPHI_DEPLOY_KEY` + `HEDE_DEPLOY_KEY` |

Each external step **skips with a notice** if its key is absent, and the workflow
still succeeds. Both keys are **SSH deploy keys** with write access to their repo,
added under repo Settings → Secrets → Actions.

## HeDE's version is its own

HeDE keeps a **separate version line** from gest (it's at `v0.3.x`, gest at
`v0.52.x`). Its source of truth is `hede/CMakeLists.txt` — `project(hede VERSION
X.Y.Z)`. **Bump that when you cut a HeDE change**; `mirror-hede.py` /
`amphi-hede.py` read it to tag the HeDE repo and stamp the ebuild. A GeST tidelock
is only the *trigger*; the HeDE artifacts carry the HeDE version.

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

## Dry runs

Every generator writes nothing without `--push`:

```sh
packaging/release-overlay.py X.Y.Z    # gest ebuild/Manifest it would write (GeST version)
packaging/mirror-hede.py              # clones HeDE read-only, shows the mirror diff (HeDE version)
packaging/amphi-hede.py 0.3.1         # downloads a HeDE tag tarball, shows the gui-apps/hede diff
```
