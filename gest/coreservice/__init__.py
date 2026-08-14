"""``gestd`` — the unprivileged GeST core service (Phase-0 scaffold).

A session-bus D-Bus service that exposes GeST ``core``'s read/validate/render
surface so a non-Python frontend (HeDE's C++/Qt shell) can consume it without
touching the Portage API or reimplementing GeST's logic. It is the read side of
the HeDE "path B" integration; writes stay on the polkit-gated root backend.

Layers, mirroring the rest of GeST:

* ``*_adapter`` modules — pure functions marshalling ``core`` <-> plain
  dicts/tuples. No D-Bus import, so the contract logic is unit-testable without a
  bus.
* the D-Bus object modules (e.g. ``hostname``) — thin ``dbus_next`` service
  interfaces that wrap the adapters and do the variant packing.
* ``service`` — claims the well-known name on the session bus and runs the loop
  (the ``gest-core`` console script).

See README.md and ``gest/ipc/core_contract.py`` for the contract.
"""
