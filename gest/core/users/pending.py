"""Staged user/group changes for the transactional Users & Groups flow.

The YaST model: edits don't touch the system as you make them — you stage
add/edit/delete/password/member operations, then commit them together with OK
(or throw them away with Cancel). This is the frontend-agnostic store of those
staged operations — pure data, no toolkit/backend imports, so it is
unit-testable on CI. The screen renders projected state from it (+/~/- markers)
and replays :meth:`ordered` through the backend on OK.
"""

from __future__ import annotations

from dataclasses import dataclass

# Operation kinds.
ADD_USER = "add_user"
MOD_USER = "mod_user"
DEL_USER = "del_user"
SET_PASSWORD = "set_password"
ADD_GROUP = "add_group"
DEL_GROUP = "del_group"
SET_MEMBER = "set_member"

# Apply order: create groups, then users, then modify, then membership, then
# passwords, then deletions (users before their groups). Keeps dependencies sane
# regardless of the order the admin staged things in.
_ORDER = [ADD_GROUP, ADD_USER, MOD_USER, SET_MEMBER, SET_PASSWORD, DEL_USER, DEL_GROUP]

_USER_KINDS = frozenset({ADD_USER, MOD_USER, DEL_USER, SET_PASSWORD})


@dataclass(slots=True)
class Op:
    kind: str
    key: str              # dedup key: username / groupname / "group\x00user"
    data: dict            # operation payload
    label: str            # human-readable one-liner


class PendingChanges:
    def __init__(self) -> None:
        self._ops: list[Op] = []

    # -- staging ------------------------------------------------------------

    def stage(self, op: Op) -> None:
        """Add an op, replacing any existing op with the same (kind, key)."""
        self._ops = [o for o in self._ops if not (o.kind == op.kind and o.key == op.key)]
        self._ops.append(op)

    def remove_for_user(self, name: str) -> None:
        """Drop every staged op that touches user ``name`` (an undo)."""
        self._ops = [o for o in self._ops if not self._touches_user(o, name)]

    def remove_for_group(self, name: str) -> None:
        self._ops = [o for o in self._ops if not self._touches_group(o, name)]

    def clear(self) -> None:
        self._ops.clear()

    # -- queries ------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self._ops

    def __len__(self) -> int:
        return len(self._ops)

    def ordered(self) -> list[Op]:
        return sorted(self._ops, key=lambda o: _ORDER.index(o.kind))

    @staticmethod
    def _touches_user(op: Op, name: str) -> bool:
        if op.kind in _USER_KINDS:
            return op.key == name
        return op.kind == SET_MEMBER and op.data.get("user") == name

    @staticmethod
    def _touches_group(op: Op, name: str) -> bool:
        if op.kind in (ADD_GROUP, DEL_GROUP):
            return op.key == name
        return op.kind == SET_MEMBER and op.data.get("group") == name

    def user_marker(self, name: str) -> str | None:
        kinds = {o.kind for o in self._ops if self._touches_user(o, name)}
        if DEL_USER in kinds:
            return "-"
        if ADD_USER in kinds:
            return "+"
        if kinds & {MOD_USER, SET_PASSWORD, SET_MEMBER}:
            return "~"
        return None

    def group_marker(self, name: str) -> str | None:
        kinds = {o.kind for o in self._ops if self._touches_group(o, name)}
        if DEL_GROUP in kinds:
            return "-"
        if ADD_GROUP in kinds:
            return "+"
        if SET_MEMBER in kinds:
            return "~"
        return None

    def added_user(self, name: str) -> Op | None:
        for o in self._ops:
            if o.kind == ADD_USER and o.key == name:
                return o
        return None

    def added_users(self) -> list[Op]:
        return [o for o in self._ops if o.kind == ADD_USER]

    def added_groups(self) -> list[Op]:
        return [o for o in self._ops if o.kind == ADD_GROUP]

    def summary(self) -> str:
        adds = sum(o.kind in (ADD_USER, ADD_GROUP) for o in self._ops)
        edits = sum(o.kind in (MOD_USER, SET_PASSWORD, SET_MEMBER) for o in self._ops)
        dels = sum(o.kind in (DEL_USER, DEL_GROUP) for o in self._ops)
        parts = []
        if adds:
            parts.append(f"+{adds}")
        if edits:
            parts.append(f"~{edits}")
        if dels:
            parts.append(f"-{dels}")
        return " ".join(parts)


# -- typed op constructors --------------------------------------------------

def add_user_op(name, comment, shell, groups, system) -> Op:
    return Op(ADD_USER, name,
              {"name": name, "comment": comment, "shell": shell,
               "groups": groups, "system": system},
              f"add user {name}")


def mod_user_op(name, comment, shell, groups) -> Op:
    return Op(MOD_USER, name,
              {"name": name, "comment": comment, "shell": shell, "groups": groups},
              f"edit user {name}")


def del_user_op(name, remove_home) -> Op:
    return Op(DEL_USER, name, {"name": name, "remove_home": remove_home},
              f"delete user {name}" + (" (+home)" if remove_home else ""))


def set_password_op(name, password) -> Op:
    return Op(SET_PASSWORD, name, {"name": name, "password": password},
              f"set password for {name}")


def add_group_op(name, system) -> Op:
    return Op(ADD_GROUP, name, {"name": name, "system": system}, f"add group {name}")


def del_group_op(name) -> Op:
    return Op(DEL_GROUP, name, {"name": name}, f"delete group {name}")


def set_member_op(group, user, add) -> Op:
    return Op(SET_MEMBER, f"{group}\x00{user}",
              {"group": group, "user": user, "add": add},
              f"{'add' if add else 'remove'} {user} {'to' if add else 'from'} {group}")
