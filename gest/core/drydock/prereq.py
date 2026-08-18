"""The Gentoo prerequisites for a barrel — Drydock's distinguishing edge.

Given a barrel's config, report exactly which packages / USE flags it needs. This
is pure data (the atom + USE table). *Applying* it — installing packages, setting
``ABI_X86``/multilib, enabling the GURU overlay for umu — routes through GeST's
existing polkit'd software/USE core, the same path every GeST module uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gest.core.drydock.model import ARCH_WIN32, RUNNER_PROTON, Barrel


@dataclass(slots=True)
class Requirement:
    atom: str
    use: list[str] = field(default_factory=list)
    note: str = ""
    from_guru: bool = False  # in the GURU overlay, not the main tree


def needs_guru(barrel: Barrel) -> bool:
    """Proton barrels need umu-launcher, which is GURU-only — the checker offers
    to enable the overlay."""
    return barrel.runner == RUNNER_PROTON


def requirements(barrel: Barrel) -> list[Requirement]:
    reqs: list[Requirement] = []

    if barrel.runner == RUNNER_PROTON:
        reqs.append(Requirement("games-util/umu-launcher", note="Proton runner (umu)",
                                from_guru=True))
        reqs.append(Requirement("media-libs/vulkan-loader", note="Vulkan"))
    else:
        multilib = barrel.arch == ARCH_WIN32
        use = ["abi_x86_32"] if multilib else []
        note = "win32 prefix → needs multilib / ABI_X86=32" if multilib else ""
        reqs.append(Requirement("app-emulation/wine-vanilla", use=use, note=note))
        if barrel.dxvk:
            reqs.append(Requirement("app-emulation/dxvk", use=list(use),
                                    note="D3D9/10/11 → Vulkan"))
        if barrel.vkd3d:
            reqs.append(Requirement("app-emulation/vkd3d-proton", note="D3D12 → Vulkan"))

    # game-mode tooling if any program uses it
    if any(p.graphics.gamescope for p in barrel.programs):
        reqs.append(Requirement("gui-wm/gamescope", note="nested compositor / FSR / HDR"))
    if any(p.graphics.gamemode for p in barrel.programs):
        reqs.append(Requirement("games-util/gamemode", note="gamemoderun"))
    if any(p.graphics.mangohud for p in barrel.programs):
        reqs.append(Requirement("games-util/mangohud", use=["mangoapp"],
                                note="mangoapp for the gamescope overlay"))
    return reqs
