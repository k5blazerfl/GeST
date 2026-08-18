"""The Drydock ``helm.recipe`` model — pure data for an install recipe.

A **recipe** is the install-time complement to the bottle model (:mod:`.model`):
a declarative description of how to set a Windows app up in a bottle — the files
it needs, an ordered list of install ``steps``, and the ``programs`` it ends up
exposing. Drydock's own interpreter (roadmap phase 6) executes a recipe; the
Lutris importer (:mod:`.lutris_import`, phase 7) produces one. See
``docs/design/drydock-lutris-interop.md``.

Pure dataclasses + dict (de)serialization only — YAML lives at the edges
(the importer / CLI), so the model itself pulls no parser dependency (matching
:mod:`gest.core.drydock.model`, which is dict-pure with JSON at the store edge).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from gest.core.drydock.model import ARCH_WIN64, RUNNER_WINE

RECIPE_VERSION = 1

# The step vocabulary the interpreter (phase 6) will dispatch on. The importer
# maps Lutris directives onto these names.
ACTION_EXTRACT = "extract"
ACTION_MOVE = "move"
ACTION_COPY = "copy"
ACTION_CHMODX = "chmodx"
ACTION_EXECUTE = "execute"
ACTION_WRITE_FILE = "write_file"
ACTION_WRITE_CONFIG = "write_config"
ACTION_WRITE_JSON = "write_json"
ACTION_CREATE_PREFIX = "create_prefix"
ACTION_WINEEXEC = "wineexec"
ACTION_WINETRICKS = "winetricks"
ACTION_REGEDIT = "regedit"
ACTION_REGEDIT_FILE = "regedit_file"
ACTION_REGDELETE = "regdelete"
ACTION_WINEKILL = "winekill"
ACTION_EJECT_DISC = "eject_disc"
# A directive we recognised but do NOT execute — carried into the recipe as a
# visible TODO so a human finishes it, never silently faked (see the ADR).
ACTION_MANUAL = "manual"


@dataclass(slots=True)
class RecipeFile:
    """An install input. Either a download (``url`` [+ ``filename``]) or a file
    the user must supply themselves (``user_provided`` holds the prompt)."""

    id: str
    url: str = ""
    filename: str = ""
    user_provided: str = ""

    def to_dict(self) -> dict:
        d: dict = {"id": self.id}
        if self.user_provided:
            d["user_provided"] = self.user_provided
        else:
            d["url"] = self.url
            if self.filename:
                d["filename"] = self.filename
        return d

    @classmethod
    def from_dict(cls, d: Mapping) -> RecipeFile:
        return cls(id=str(d["id"]), url=str(d.get("url", "")),
                   filename=str(d.get("filename", "")),
                   user_provided=str(d.get("user_provided", "")))


@dataclass(slots=True)
class RecipeStep:
    """One ordered install action: an ``action`` name + its ``params``."""

    action: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"action": self.action, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d: Mapping) -> RecipeStep:
        return cls(action=str(d["action"]), params=dict(d.get("params", {})))


@dataclass(slots=True)
class RecipeProgram:
    """A program the recipe ends up exposing (Customs exports these later)."""

    name: str
    exe: str
    args: list[str] = field(default_factory=list)
    category: str = "Application"  # "Application" | "Game"

    def to_dict(self) -> dict:
        return {"name": self.name, "exe": self.exe,
                "args": list(self.args), "category": self.category}

    @classmethod
    def from_dict(cls, d: Mapping) -> RecipeProgram:
        return cls(name=str(d.get("name", "")), exe=str(d.get("exe", "")),
                   args=[str(a) for a in d.get("args", [])],
                   category=str(d.get("category", "Application")))


@dataclass(slots=True)
class RecipeBottle:
    """The bottle this recipe seeds — a subset of :class:`.model.Bottle`."""

    runner: str = RUNNER_WINE
    arch: str = ARCH_WIN64
    verbs: list[str] = field(default_factory=list)
    dxvk: bool = False
    vkd3d: bool = False
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"runner": self.runner, "arch": self.arch, "verbs": list(self.verbs),
                "dxvk": self.dxvk, "vkd3d": self.vkd3d, "env": dict(self.env)}

    @classmethod
    def from_dict(cls, d: Mapping) -> RecipeBottle:
        return cls(runner=str(d.get("runner", RUNNER_WINE)),
                   arch=str(d.get("arch", ARCH_WIN64)),
                   verbs=[str(v) for v in d.get("verbs", [])],
                   dxvk=bool(d.get("dxvk", False)), vkd3d=bool(d.get("vkd3d", False)),
                   env={str(k): str(v) for k, v in dict(d.get("env", {})).items()})


@dataclass(slots=True)
class Recipe:
    app_name: str
    app_id: str = ""
    categories: list[str] = field(default_factory=lambda: ["Application"])
    bottle: RecipeBottle = field(default_factory=RecipeBottle)
    files: list[RecipeFile] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    programs: list[RecipeProgram] = field(default_factory=list)
    prereqs: str = "auto"  # "auto" → defer to prereq.py's atom+USE table

    def to_dict(self) -> dict:
        return {
            "recipe": RECIPE_VERSION,
            "app": {"name": self.app_name, "id": self.app_id,
                    "categories": list(self.categories)},
            "bottle": self.bottle.to_dict(),
            "files": [f.to_dict() for f in self.files],
            "steps": [s.to_dict() for s in self.steps],
            "programs": [p.to_dict() for p in self.programs],
            "prereqs": self.prereqs,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Recipe:
        app = dict(d.get("app", {}))
        return cls(
            app_name=str(app.get("name", "")), app_id=str(app.get("id", "")),
            categories=[str(c) for c in app.get("categories", ["Application"])],
            bottle=RecipeBottle.from_dict(d.get("bottle", {})),
            files=[RecipeFile.from_dict(f) for f in d.get("files", [])],
            steps=[RecipeStep.from_dict(s) for s in d.get("steps", [])],
            programs=[RecipeProgram.from_dict(p) for p in d.get("programs", [])],
            prereqs=str(d.get("prereqs", "auto")),
        )
