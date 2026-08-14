"""Boot & Kernel module logic: pure summary + regenerate-grub bridge."""

from __future__ import annotations

from gest.core.bootloader.reader import BootInfo
from gest.core.kernel.reader import KernelBuildInfo
from gest.qt.backend import run_backend


def boot_summary(boot: BootInfo, kern: KernelBuildInfo) -> list[tuple[str, str]]:
    tools = [n for n, on in (("genkernel", kern.genkernel), ("dracut", kern.dracut)) if on]
    return [
        ("Running kernel", boot.running_kernel or "—"),
        ("Bootloader", boot.bootloader),
        ("Kernel source", boot.kernel_source or "—"),
        ("Installed kernels", ", ".join(boot.kernels) or "—"),
        ("Kernel .config", "present" if kern.has_config else "absent"),
        ("Build tools", ", ".join(tools) or "—"),
    ]


def regenerate_grub() -> tuple[bool, str]:
    async def run():
        from gest.core.bootloader.backend_client import BootloaderBackend

        backend = await BootloaderBackend().connect()
        try:
            return await backend.regenerate_grub()
        finally:
            await backend.close()

    return run_backend(run)
