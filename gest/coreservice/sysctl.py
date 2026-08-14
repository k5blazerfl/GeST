"""The sysctl gestd D-Bus object — the GeST sysctl.d drop-in.

``GetSettings`` returns the managed key/values as ``a{ss}``; ``Validate``/``Render``
keep the checks and the rendered form in Python ``core``. Applying (write + load)
stays on the polkit root backend.
"""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import sysctl_adapter as adapter
from gest.ipc.core_contract import SYSCTL_CORE_IFACE


class SysctlInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(SYSCTL_CORE_IFACE)

    @method()
    async def GetSettings(self) -> "a{ss}":
        return await asyncio.to_thread(adapter.get_settings)

    @method()
    async def Validate(self, settings: "a{ss}") -> "bs":   # -> (ok, message)
        ok, message = await asyncio.to_thread(adapter.validate, settings)
        return [ok, message]

    @method()
    async def Render(self, settings: "a{ss}") -> "s":
        return await asyncio.to_thread(adapter.render, settings)
