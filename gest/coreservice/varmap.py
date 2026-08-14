"""Shared D-Bus variant packing for gestd property bags.

Every module's adapter returns plain dicts (str/bool/int/list values); the D-Bus
object wraps them into ``a{sv}`` with these. One place so the type→signature
mapping (esp. bool-before-int) is consistent across modules.
"""

from __future__ import annotations

from typing import Any

from dbus_next import Variant


def to_variant(value: Any) -> Variant:
    if isinstance(value, bool):             # bool is an int subclass — check first
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("x", value)          # int64 (sizes can be large)
    if isinstance(value, list):
        return Variant("as", [str(x) for x in value])
    return Variant("s", str(value))


def variant_map(d: dict[str, Any]) -> dict[str, Variant]:
    return {k: to_variant(v) for k, v in d.items()}
