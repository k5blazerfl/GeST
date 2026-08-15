"""The Drydock bottle model — pure data + JSON (de)serialization.

A **bottle** is a managed Wine/Proton prefix + config; it holds **programs**
(installed Windows apps), each with a **graphics profile** (gamescope/gamemode/
MangoHud/DXVK tuning). The runner is chosen per bottle — ``proton`` (via umu) or
``wine`` — with no default (resolved design decision).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

RUNNER_PROTON = "proton"  # Proton via umu-run
RUNNER_WINE = "wine"  # plain Wine
RUNNERS = (RUNNER_PROTON, RUNNER_WINE)

ARCH_WIN64 = "win64"
ARCH_WIN32 = "win32"
ARCHES = (ARCH_WIN64, ARCH_WIN32)

CONFIG_VERSION = 1


@dataclass(slots=True)
class GraphicsProfile:
    gamescope: bool = False
    gamescope_width: int = 0  # 0 → follow the output size
    gamescope_height: int = 0
    fsr: bool = False
    hdr: bool = False
    gamemode: bool = False
    mangohud: bool = False
    dxvk_hud: str = ""  # e.g. "fps" or "full"
    fps_cap: int = 0  # 0 → uncapped
    esync: bool = True
    fsync: bool = True

    def to_dict(self) -> dict:
        return {
            "gamescope": self.gamescope, "gamescope_width": self.gamescope_width,
            "gamescope_height": self.gamescope_height, "fsr": self.fsr, "hdr": self.hdr,
            "gamemode": self.gamemode, "mangohud": self.mangohud, "dxvk_hud": self.dxvk_hud,
            "fps_cap": self.fps_cap, "esync": self.esync, "fsync": self.fsync,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> GraphicsProfile:
        return cls(**{k: d[k] for k in d if k in cls.__slots__})


@dataclass(slots=True)
class Program:
    id: str
    name: str
    exe: str  # path to the executable inside the prefix
    args: list[str] = field(default_factory=list)
    category: str = "Application"  # "Application" | "Game"
    wm_class: str = ""  # for taskbar identity matching (Customs)
    graphics: GraphicsProfile = field(default_factory=GraphicsProfile)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "exe": self.exe, "args": list(self.args),
            "category": self.category, "wm_class": self.wm_class,
            "graphics": self.graphics.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Program:
        return cls(
            id=str(d["id"]), name=str(d.get("name", "")), exe=str(d.get("exe", "")),
            args=[str(a) for a in d.get("args", [])],
            category=str(d.get("category", "Application")),
            wm_class=str(d.get("wm_class", "")),
            graphics=GraphicsProfile.from_dict(d.get("graphics", {})),
        )


@dataclass(slots=True)
class Bottle:
    id: str
    name: str
    runner: str  # RUNNER_PROTON | RUNNER_WINE
    runner_version: str = ""  # Proton codename/path (umu) or eselect wine target
    arch: str = ARCH_WIN64
    prefix: str = ""  # WINEPREFIX; defaults under the bottle dir if empty
    verbs: list[str] = field(default_factory=list)  # winetricks verbs (wine)
    dxvk: bool = False  # wine-only — Proton bundles DXVK/VKD3D
    vkd3d: bool = False
    env: dict[str, str] = field(default_factory=dict)
    programs: list[Program] = field(default_factory=list)

    def is_valid(self) -> bool:
        return bool(self.id) and self.runner in RUNNERS and self.arch in ARCHES

    def program(self, program_id: str) -> Program | None:
        return next((p for p in self.programs if p.id == program_id), None)

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION, "id": self.id, "name": self.name,
            "runner": self.runner, "runner_version": self.runner_version,
            "arch": self.arch, "prefix": self.prefix, "verbs": list(self.verbs),
            "dxvk": self.dxvk, "vkd3d": self.vkd3d, "env": dict(self.env),
            "programs": [p.to_dict() for p in self.programs],
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Bottle:
        return cls(
            id=str(d["id"]), name=str(d.get("name", "")), runner=str(d["runner"]),
            runner_version=str(d.get("runner_version", "")),
            arch=str(d.get("arch", ARCH_WIN64)), prefix=str(d.get("prefix", "")),
            verbs=[str(v) for v in d.get("verbs", [])],
            dxvk=bool(d.get("dxvk", False)), vkd3d=bool(d.get("vkd3d", False)),
            env={str(k): str(v) for k, v in dict(d.get("env", {})).items()},
            programs=[Program.from_dict(p) for p in d.get("programs", [])],
        )
