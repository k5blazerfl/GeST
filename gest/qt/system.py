"""System-identity module logic: sync bridges to the polkit-gated System backend.

Hostname, locale, console keymap and console font all mutate through the one
:class:`~gest.core.system.backend_client.SystemBackend` (a D-Bus, polkit-gated
service), so a single ``_run`` helper wraps every call in the shared
``run_backend`` bridge — a PySide slot calls these synchronously and shows the
returned ``(ok, message)`` in a status label.
"""

from __future__ import annotations

from gest.qt.backend import run_backend


def _run(method: str, *args) -> tuple[bool, str]:
    async def run():
        from gest.core.system.backend_client import SystemBackend

        backend = await SystemBackend().connect()
        try:
            return await getattr(backend, method)(*args)
        finally:
            await backend.close()

    return run_backend(run)


def set_hostname(name: str) -> tuple[bool, str]:
    return _run("set_hostname", name)


def set_locale(lang: str) -> tuple[bool, str]:
    return _run("set_locale", lang)


def set_keymap(keymap: str) -> tuple[bool, str]:
    return _run("set_keymap", keymap)


def set_console_font(font: str) -> tuple[bool, str]:
    return _run("set_console_font", font)
