# Packaging GeST for Gentoo

Ebuilds that install GeST system-wide — the **hardened** install: the root
backend loads the *installed* package from system paths, not a working tree
(unlike the dev `install-backend.sh`). Two are provided:

- **`gest-0.49.7`** — the latest released version (urwid; depends only on
  `::gentoo` packages), from the `v0.49.7` tag tarball (`~amd64`). Recommended —
  Software Repositories gains a per-repo "Refresh" flag: flagged overlays sync
  when Software Management opens (the main gentoo tree excluded), keeping their
  package lists current without a full tree sync; the selection is stored in
  GeST's own `/etc/portage/gest/refresh` file. The Sync screen reports
  `emerge --sync` per repository, so a single failed overlay reads as
  "Partially synced" (naming the culprit) instead of a flat "Failure". Fixes
  `emerge --sync` (and merges) failing with "Command not found:
  rsync/git": the D-Bus–activated root backend now guarantees a sane PATH so
  emerge finds its sync/unpack helpers. Also fixes a failing install locking the TUI while memory
  climbed: the Apply screen now caps its on-screen log and spills the full log to
  a file, the backend batches merge output instead of one signal per line, and a
  corrected end-of-stream check stops the backend read loop from spinning. Software
  Management gains an "Updates available" view and a `↑` flag marking
  installed packages with a newer in-slot version. The ebuild runs the pytest
  suite at build time (`FEATURES=test`) and the package uses a PEP 639 SPDX
  license expression. A finished Apply run shows an unmistakable result prompt
  (Completed / Failed / Not started). The Apply screen shows an installation
  progress bar (emerge N-of-M); Software Management distinguishes source- vs
  binary-installed packages (ⓑ glyph + Origin detail) and can install the
  binary version (--getbinpkg).
- **`gest-9999`** — a live ebuild that builds the current `main` (for
  hacking on the tree).

## Install via a local overlay

```bash
# 1. register this directory as a local repository
sudo mkdir -p /etc/portage/repos.conf
sudo tee /etc/portage/repos.conf/gest.conf >/dev/null <<REPO
[gest]
location = /home/charron/GeST/packaging/overlay
masters = gentoo
auto-sync = no
REPO

# 2. accept the ~amd64 keyword and emerge the released version
echo "app-admin/gest ~amd64" | sudo tee /etc/portage/package.accept_keywords/gest
sudo emerge -av app-admin/gest

#    (to track main instead, unmask and emerge the live ebuild:
#     echo "=app-admin/gest-9999 **" | sudo tee /etc/portage/package.accept_keywords/gest
#     sudo emerge -av =app-admin/gest-9999 )

# 3. reload D-Bus so it sees the new policy/activation
sudo rc-service dbus reload
```

Then just run `gest`. The backend bus-activates on first privileged action.

## What the ebuild installs

- the `gest` package into site-packages, plus `gest` and `gest-backend` scripts
- `/usr/share/dbus-1/system.d/org.gentoo.gest.conf` (D-Bus policy)
- `/usr/share/dbus-1/system-services/org.gentoo.gest.service` (activation)
- `/usr/share/polkit-1/actions/org.gentoo.gest.policy` (polkit actions)
- `/usr/libexec/gest-backend` (runs the installed package as root)

## Dependencies

`dev-python/dbus-next` may not be in `::gentoo`; if `emerge` can't find it,
add an overlay that provides it (or it can be pip-installed for development).

## The two overlays — one source of truth

GeST is installed from a Gentoo overlay maintained in **two** places:

- **`packaging/overlay/`** (this repo) — the **authoritative** overlay. Full
  version history with a complete `Manifest`. Everything else is derived from it.
- **[Amphitheater](https://github.com/k5blazerfl/Amphitheater)** — the **lean**
  overlay Portage actually installs from (`/var/db/repos/amphitheater`). It
  carries only the *latest* release ebuild + `gest-9999` + a `Manifest` with the
  single current `DIST` line. It is **generated** from the authoritative overlay,
  never hand-edited.

The historical failure was drift: an ebuild bumped without its `Manifest` `DIST`
digest, so `emerge` failed with "Insufficient data for checksum verification".
Two guards now make that impossible to ship:

- **`tests/test_overlay_manifest.py`** (runs in CI) fails if any `gest-X.Y.Z.ebuild`
  in the authoritative overlay lacks a matching `DIST` line.
- **`packaging/release-overlay.py`** generates both overlays from the tag tarball
  in one step, so the ebuild and its `DIST` are always written together.

## Cutting a new release

1. Bump `__version__` + `pyproject.toml`, commit, then tag and push:
   `git tag -a vX.Y.Z -m "…" && git push origin main vX.Y.Z`.
2. The **Overlay sync** GitHub Action (`.github/workflows/overlay-sync.yml`) fires
   on the tag: it adds `gest-X.Y.Z.ebuild` + the `Manifest` `DIST` to this repo,
   and — once the deploy key is configured (below) — regenerates and pushes the
   lean Amphitheater overlay. **With the Action enabled, do not hand-create the
   packaging commit.**

To do it by hand (or offline), run the same generator locally after tagging:

```bash
packaging/release-overlay.py            # dry run: shows what it would change
packaging/release-overlay.py --push     # commit+push the GeST overlay AND Amphitheater
# scope with --gest-only / --amphitheater-only; version defaults to pyproject
```

It downloads `https://github.com/k5blazerfl/GeST/archive/refs/tags/vX.Y.Z.tar.gz`,
computes the `DIST` (byte-identical to `pkgdev manifest`), writes the versioned
ebuild + Manifest here (full history), and regenerates Amphitheater's lean
`app-admin/gest/` from this overlay (latest release ebuild only, older ones
pruned; `metadata.xml` and `gest-9999` copied from here — this overlay is the
single source of truth for all of them).

### Enabling the Amphitheater auto-sync (one-time)

The Action syncs Amphitheater only when it can push there. Add an SSH deploy key:

1. `ssh-keygen -t ed25519 -f amphi_deploy -N ""` — no passphrase.
2. Add `amphi_deploy.pub` to **Amphitheater → Settings → Deploy keys** with
   **Allow write access**.
3. Add the private key `amphi_deploy` as a **GeST** repo secret named
   **`AMPHI_DEPLOY_KEY`** (Settings → Secrets and variables → Actions).

Until the secret exists, the Action updates only the GeST overlay and logs that
it skipped Amphitheater — the run still succeeds.
