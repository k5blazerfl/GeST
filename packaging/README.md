# Packaging GeST for Gentoo

A live (`9999`) ebuild that installs GeST system-wide — the **hardened** install:
the root backend loads the *installed* package from system paths, not a working
tree (unlike the dev `install-backend.sh`).

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

# 2. unmask the live ebuild and emerge it
echo "app-admin/gest **" | sudo tee /etc/portage/package.accept_keywords/gest
sudo emerge -av app-admin/gest

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
