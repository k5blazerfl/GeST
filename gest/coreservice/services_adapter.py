"""Pure adapter for the Services (OpenRC) core module — models <-> property bags.

Converters take a model instance and return a plain dict (unit-testable with
hand-built models, no subprocess). The live functions call ``reader`` (which shells
out to ``rc-status``/``rc-update``/``rc-service`` — no Portage, no asyncio loop of
its own, but blocking subprocess, so the D-Bus layer runs them off the loop).
"""

from __future__ import annotations

from typing import Any

from gest.core.services import reader


def service_to_dict(s: Any) -> dict[str, Any]:
    return {
        "name": s.name,
        "status": s.status,
        "runlevels": list(s.runlevels),
        "enabled": s.enabled,
        "running": s.running,
    }


def detail_to_dict(d: Any) -> dict[str, Any]:
    return {
        "name": d.name,
        "description": d.description,
        "needs": list(d.needs),
        "uses": list(d.uses),
        "wants": list(d.wants),
        "needed_by": list(d.needed_by),
        "status": d.status,
        "runlevels": list(d.runlevels),
        "running": d.running,
    }


def list_services() -> list[dict[str, Any]]:
    return [service_to_dict(s) for s in reader.list_services()]


def describe(name: str) -> dict[str, Any]:
    # Pass the current status/runlevels through so the detail is accurate without
    # re-deriving them inside describe_service.
    svc = next((s for s in reader.list_services() if s.name == name), None)
    kw = {"status": svc.status, "runlevels": svc.runlevels} if svc else {}
    return detail_to_dict(reader.describe_service(name, **kw))
