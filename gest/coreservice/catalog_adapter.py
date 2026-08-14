"""Pure adapter for the Catalog — module descriptors -> property bags."""

from __future__ import annotations

from typing import Any

from gest.coreservice.descriptors import MODULES, ModuleDescriptor


def descriptor_to_dict(m: ModuleDescriptor) -> dict[str, Any]:
    return {
        "id": m.id,
        "title": m.title,
        "category": m.category,
        "icon": m.icon,
        "path": m.path,
        "interface": m.iface,
    }


def list_modules() -> list[dict[str, Any]]:
    return [descriptor_to_dict(m) for m in MODULES]
