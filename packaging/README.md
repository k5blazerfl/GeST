# Packaging GeST for Gentoo

Ebuilds that install GeST system-wide — the **hardened** install: the root
backend loads the *installed* package from system paths, not a working tree
(unlike the dev `install-backend.sh`). Two are provided:

- **`gest-0.31.1`** — the latest released version (urwid; depends only on
  `::gentoo` packages), from the `v0.31.1` tag tarball (`~amd64`). Recommended —
  fixes a polkit crash that broke all privileged actions on newer PyGObject.
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

## Cutting a new release

1. Bump `__version__` / `pyproject.toml`, merge, then tag: `git tag -a vX.Y.Z && git push origin vX.Y.Z`.
2. Add `gest-X.Y.Z.ebuild` (copy the latest versioned ebuild) and regenerate
   the `Manifest` from the tag tarball:
   `cd packaging/overlay/app-admin/gest && pkgdev manifest`
   (or compute the `DIST` line by hand from
   `https://github.com/k5blazerfl/GeST/archive/refs/tags/vX.Y.Z.tar.gz`).
