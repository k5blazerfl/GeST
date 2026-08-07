# GeST privileged backend

The backend is the single component that runs as **root**. The unprivileged
frontend reaches it over the **system** D-Bus bus (`org.gentoo.gest`), and every
mutating method is gated by **polkit**. This is the same model YaST, Cockpit,
and GNOME's control center use.

## What it exposes

Interface `org.gentoo.gest.Software` on `/org/gentoo/gest/Software`:

| Member | Kind | Auth | Purpose |
|---|---|---|---|
| `InstallPreview(atom) → report` | method | none | `emerge --pretend` output |
| `Install(atom) → started`       | method | `org.gentoo.gest.software.install` | start a merge |
| `Progress(line)`                | signal | — | one line of live merge output |
| `Finished(exit_code)`           | signal | — | the merge has ended |

`InstallPreview` needs no authorization because `--pretend` changes nothing.
`Install` calls polkit's `CheckAuthorization` for the caller's bus name before
doing anything.

## Installing the system data files

**Quick install (development):** from the repo root, as root:

```bash
sudo ./install-backend.sh        # install (uninstall: sudo ./install-backend.sh -u)
```

This writes the launcher + all three data files and reloads D-Bus. It is a
*dev* install: the root service loads `gest` from the working tree, so keep
the tree trusted. The manual equivalent is below.

These live in [`../../data/`](../../data) and must be placed by root:

```bash
# D-Bus: who may own/call the name
install -m 0644 data/org.gentoo.gest.conf \
    /usr/share/dbus-1/system.d/org.gentoo.gest.conf

# D-Bus: start the service on demand (bus-activation), as root
install -m 0644 data/org.gentoo.gest.service \
    /usr/share/dbus-1/system-services/org.gentoo.gest.service

# polkit: the actions and their default auth rules
install -m 0644 data/org.gentoo.gest.policy \
    /usr/share/polkit-1/actions/org.gentoo.gest.policy

# the executable the activation file points at
install -m 0755 backend-launcher /usr/libexec/gest-backend
```

`/usr/libexec/gest-backend` should exec the backend with an interpreter that can
import both `gest` and PyGObject, e.g.:

```sh
#!/bin/sh
exec /usr/bin/python3 -m gest.backend.service "$@"
```

Then reload D-Bus (`rc-service dbus reload` on OpenRC) so the new policy and
activation file are picked up. The service auto-starts on the first call and
exits when D-Bus tells it the name was lost.

## Why GLib/Gio and not dbus-next here

The backend needs the **caller's** bus name to ask polkit about it. GLib's
method-invocation object exposes it via `invocation.get_sender()`; dbus-next's
high-level API does not surface the sender. The frontend client
(`core/software/backend_client.py`) uses dbus-next because it integrates with
the frontend's asyncio loop — the two sides only share the wire protocol.
