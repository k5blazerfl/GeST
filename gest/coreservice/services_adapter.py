"""Pure adapter for the Services (systemd) core module — models <-> property bags.

Converters take a model instance and return a plain dict (unit-testable with
hand-built models, no subprocess). The live functions call ``reader`` (which shells
out to ``systemctl`` — no Portage, no asyncio loop of its own, but blocking
subprocess, so the D-Bus layer runs them off the loop).
"""

from __future__ import annotations

from typing import Any

from gest.core.services import reader


def service_to_dict(s: Any) -> dict[str, Any]:
    return {
        "name": s.name,
        "status": s.status,
        "sub_state": s.sub_state,
        "enabled_state": s.enabled_state,
        "enabled": s.enabled,
        "running": s.running,
        "masked": s.masked,
        "description": s.description,
    }


def detail_to_dict(d: Any) -> dict[str, Any]:
    return {
        "name": d.name,
        "description": d.description,
        "requires": list(d.requires),
        "wants": list(d.wants),
        "after": list(d.after),
        "required_by": list(d.required_by),
        "status": d.status,
        "sub_state": d.sub_state,
        "enabled_state": d.enabled_state,
        "load_state": d.load_state,
        "running": d.running,
        "enabled": d.enabled,
        "masked": d.masked,
    }


def list_services() -> list[dict[str, Any]]:
    return [service_to_dict(s) for s in reader.list_services()]


def describe(name: str) -> dict[str, Any]:
    # Pass the current runtime/install state through so the detail is accurate
    # without re-deriving it inside describe_service.
    svc = next((s for s in reader.list_services() if s.name == name), None)
    kw = (
        {"status": svc.status, "sub_state": svc.sub_state, "enabled_state": svc.enabled_state}
        if svc else {}
    )
    return detail_to_dict(reader.describe_service(name, **kw))
