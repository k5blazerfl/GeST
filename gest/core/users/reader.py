"""Read local accounts from /etc/passwd and /etc/group (unprivileged)."""

from __future__ import annotations

from gest.core.users.model import Group, User


def parse_passwd(text: str) -> list[User]:
    """Parse passwd content: name:x:uid:gid:gecos:home:shell per line."""
    users: list[User] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 7:
            continue
        name, _pw, uid, gid, gecos, home, shell = parts[:7]
        try:
            users.append(User(name, int(uid), int(gid), gecos, home, shell))
        except ValueError:
            continue
    return users


def parse_group(text: str) -> list[Group]:
    """Parse group content: name:x:gid:member,member per line."""
    groups: list[Group] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        name, _pw, gid, members = parts[:4]
        try:
            gid_int = int(gid)
        except ValueError:
            continue
        member_list = [m for m in members.split(",") if m]
        groups.append(Group(name, gid_int, member_list))
    return groups


def list_users(path: str = "/etc/passwd") -> list[User]:
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_passwd(fh.read())
    except OSError:
        return []


def list_groups(path: str = "/etc/group") -> list[Group]:
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_group(fh.read())
    except OSError:
        return []


def member_groups(username: str, groups: list[Group]) -> list[str]:
    """Supplementary group names that list ``username`` as a member."""
    return sorted(g.name for g in groups if username in g.members)


def groups_for(username: str, path: str = "/etc/group") -> list[str]:
    return member_groups(username, list_groups(path))
