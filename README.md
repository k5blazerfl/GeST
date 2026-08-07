# GeST — Gentoo System Tool

A modular, YaST-style system-administration tool for Gentoo. Where openSUSE has
YaST2, Gentoo has a pile of excellent-but-disjoint CLIs (`emerge`, `equery`,
`rc-update`, …). GeST aims to unify them behind one coherent interface —
starting with a full-screen text UI, with a Qt/KDE frontend planned.

> **Status:** early. The **software (Portage) module** read path and the TUI
> shell are implemented and tested. The privileged backend is scaffolded (D-Bus
> + polkit) but not yet wired into the TUI's write actions. See the roadmap.

## Architecture

The design copies YaST's most durable idea — a hard separation between
frontends, module logic, and a privileged backend — so a second frontend is a
new renderer, not a rewrite.

```
 frontends ──► core ──► backend
  (TUI)     (modules)  (root, D-Bus + polkit)

 gest/tui/        Textual full-screen frontend (this release)
 gest/core/       frontend-agnostic modules — the real logic
   software/        Portage: model, reader (queries), backend_client (mutations)
 gest/ipc/        the shared D-Bus + polkit contract (names in one place)
 gest/backend/    root D-Bus service, one process, polkit-gated
 data/            system data files (D-Bus policy, activation, polkit actions)
```

**Golden rule:** frontends never touch Portage or D-Bus directly. They call
`core`; `core` is the only thing that speaks to `backend`.

- **Queries** (installed list, search, USE flags) use the in-process **Portage
  Python API** — structured and fast, never `emerge` output scraping.
- **Mutations** (merge, unmerge, edit `/etc/portage`, sync) are the backend's
  job: an unprivileged frontend asks the root service over the system bus, and
  **polkit** decides whether the user is allowed.

## Running (development)

The venv must see the *system* Portage, so create it with system site-packages:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install textual dbus-next
./bin/gest            # launch the TUI
```

In the TUI: **↑/↓** move, **Enter** opens a module, **/** focuses search,
**Esc** goes back, **q** quits.

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

The reader tests are integration tests against the host's live Portage DB; the
TUI tests drive the interface headlessly via Textual's pilot.

## Privileged backend

Not required for the read-only TUI. To enable install/remove later, install the
system data files (as root) — see [`gest/backend/README.md`](gest/backend/README.md).

## Roadmap

- [x] Layered skeleton: core + TUI + IPC contract
- [x] Software module — read path (list / search / info, USE flags, @world)
- [x] Backend scaffold: D-Bus service, polkit actions, system data files
- [x] Install flow: `emerge --pretend` preview → confirm → streamed merge
      (preview runs as the user; the live merge needs the root backend installed)
- [x] USE-flag editing (`package.use`) — tri-state per flag, written via the
      polkit-gated backend, then applied with a `--changed-use` rebuild
- [x] Keyword acceptance + mask editing (`package.accept_keywords`,
      `package.mask`, `package.unmask`) via a generalized backend config writer
- [x] `@world` system update (`emerge -uDN @world`) — preview + streamed merge
- [ ] Unmerge (depclean preview), tree sync, news items
- [ ] Further modules: Services (OpenRC/systemd), Users & Groups, Network
- [ ] Qt/KDE frontend over the same `core`
```
