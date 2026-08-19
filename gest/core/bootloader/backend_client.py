"""Async client for the Bootloader backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BOOTLOADER_IFACE, BOOTLOADER_PATH, BUS_NAME


class BootloaderBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> BootloaderBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, BOOTLOADER_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, BOOTLOADER_PATH, introspection)
        self._iface = obj.get_interface(BOOTLOADER_IFACE)
        return self

    async def regenerate_grub(self):
        return await self._iface.call_regenerate_grub()

    async def install_grub(self, firmware, efi_directory, bootloader_id,
                           removable, disk, boot_directory):
        """Install GRUB (UEFI or BIOS); returns (ok, output). Implements the
        ``install.GrubInstaller`` protocol with :meth:`regenerate_grub`."""
        return await self._iface.call_install_grub(
            firmware, efi_directory, bootloader_id, bool(removable), disk, boot_directory)

    async def configure_seamless_boot(self, root=""):
        """Write the seamless-boot config under ``root`` ("" = live host, or a
        target root like /mnt/gentoo): /etc/default/grub + the GRUB theme + the
        Plymouth splash. Returns (ok, output); regenerate grub.cfg afterward."""
        return await self._iface.call_configure_seamless_boot(root)

    async def sync_boot_theme(self, accent, root=""):
        """Re-tint the installed boot theme (Plymouth + GRUB) to ``accent``
        ("#RRGGBB") and rebuild the initramfs. Returns (ok, output). Requires a
        prior :meth:`configure_seamless_boot`; the desktop background is
        unaffected — only the boot palette tracks the biome."""
        return await self._iface.call_sync_boot_theme(accent, root)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
