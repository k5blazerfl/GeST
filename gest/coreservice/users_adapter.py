"""Pure adapter for the Users & Groups core module — models <-> property bags.

The converters and the group-membership helper are pure (unit-testable with
hand-built models); the live functions read /etc/passwd and /etc/group via the
reader. Group membership per user (primary group + supplementary) is computed
here from the two lists so a client gets it in one call.
"""

from __future__ import annotations

from typing import Any

from gest.core.users import reader


def user_to_dict(u: Any) -> dict[str, Any]:
    """A User -> property bag (without ``groups`` — that needs the group list)."""
    return {
        "name": u.name,
        "uid": u.uid,
        "gid": u.gid,
        "gecos": u.gecos,
        "home": u.home,
        "shell": u.shell,
        "full_name": u.full_name,
        "system": u.system,
    }


def group_to_dict(g: Any) -> dict[str, Any]:
    return {
        "name": g.name,
        "gid": g.gid,
        "members": list(g.members),
        "system": g.system,
    }


def user_group_names(u: Any, groups: list) -> list[str]:
    """The group names ``u`` belongs to: its primary group (by gid) + every group
    that lists it as a supplementary member, sorted and de-duplicated."""
    primary = next((g.name for g in groups if g.gid == u.gid), "")
    supplementary = [g.name for g in groups if u.name in g.members]
    return sorted({name for name in (primary, *supplementary) if name})


def list_users() -> list[dict[str, Any]]:
    groups = reader.list_groups()
    out = []
    for u in reader.list_users():
        d = user_to_dict(u)
        d["groups"] = user_group_names(u, groups)
        out.append(d)
    return out


def list_groups() -> list[dict[str, Any]]:
    return [group_to_dict(g) for g in reader.list_groups()]
