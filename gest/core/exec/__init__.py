"""Execution layer: run a mutating tool the right way for the current runtime.

GeST mutates the system in one of two ways depending on how it's running
(see docs/design/runtime-privilege-path.md):

* **Installed system**, launched unprivileged → marshal over the system D-Bus to
  the root ``gest-backend``, which polkit-authorizes the caller. (``DBusExecutor``)
* **Live CD / already root** → run the tool in-process; the polkit gate is
  vacuous when the caller is already uid 0. (``DirectExecutor``)

Both present the same `Executor` interface — an async ``run(argv)`` that streams
output — so callers (and the partitioner) never branch on which is active. The
subprocess/stream logic lives once in `runner`, shared by both paths.

Security invariant: ``DirectExecutor`` is selected *only* when already root; an
unprivileged frontend always goes through D-Bus + polkit, unchanged.
"""
