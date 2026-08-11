"""Staged repository changes — mark now, apply on Accept (YaST-style).

Repository mutations don't touch the system on each keypress; they accumulate
here and are applied together when the user Accepts (like Software Management's
mark→Accept flow). This is the pure, frontend-agnostic store — the TUI renders it
and applies it through the Repos + Portage backends. CI-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ENABLE = "enable"
DISABLE = "disable"
REMOVE = "remove"
ADD = "add"
_STATE_OPS = frozenset({ENABLE, DISABLE, REMOVE})


@dataclass(slots=True, frozen=True)
class AddSpec:
    sync_type: str
    uri: str


@dataclass(slots=True, frozen=True)
class EditSpec:
    """New field values for an existing repo (name unchanged)."""

    sync_type: str
    uri: str
    priority: str = ""


@dataclass(slots=True)
class Pending:
    """The set of staged changes: eselect state ops, custom adds, refresh flags."""

    state: dict[str, str] = field(default_factory=dict)     # name -> enable/disable/remove
    adds: dict[str, AddSpec] = field(default_factory=dict)  # name -> AddSpec (new repo)
    edits: dict[str, EditSpec] = field(default_factory=dict)  # name -> EditSpec
    refresh: dict[str, bool] = field(default_factory=dict)  # name -> desired refresh flag

    @property
    def is_empty(self) -> bool:
        return not (self.state or self.adds or self.edits or self.refresh)

    def count(self) -> int:
        return (len(self.state) + len(self.adds) + len(self.edits)
                + len(self.refresh))

    def clear(self) -> None:
        self.state.clear()
        self.adds.clear()
        self.edits.clear()
        self.refresh.clear()

    def mark_state(self, name: str, op: str) -> None:
        """Toggle a state op on ``name`` — marking the same op again clears it."""
        if op not in _STATE_OPS:
            raise ValueError(f"unknown op: {op}")
        if self.state.get(name) == op:
            del self.state[name]
        else:
            self.state[name] = op
            if op == REMOVE:
                self.refresh.pop(name, None)   # removing moots refresh-on-open
                self.edits.pop(name, None)     # ...and any staged edit

    def add(self, name: str, sync_type: str, uri: str) -> None:
        self.adds[name] = AddSpec(sync_type, uri)

    def edit(self, name: str, sync_type: str, uri: str, priority: str = "") -> None:
        self.edits[name] = EditSpec(sync_type, uri, priority)

    def edit_of(self, name: str) -> EditSpec | None:
        return self.edits.get(name)

    def cancel(self, name: str) -> None:
        """Drop every staged change for ``name`` (un-stage a new/marked repo)."""
        self.state.pop(name, None)
        self.adds.pop(name, None)
        self.edits.pop(name, None)
        self.refresh.pop(name, None)

    def toggle_refresh(self, name: str, current: bool) -> bool:
        """Toggle refresh relative to the on-disk ``current``; clears if back to it."""
        desired = not self.refresh.get(name, current)
        if desired == current:
            self.refresh.pop(name, None)
        else:
            self.refresh[name] = desired
        return desired

    def state_of(self, name: str) -> str | None:
        return self.state.get(name)

    def refresh_of(self, name: str) -> bool | None:
        return self.refresh.get(name)

    def ordered_ops(self) -> list[tuple[str, str, AddSpec | None]]:
        """``(kind, name, spec)`` in apply order: adds/enables before dis/removes."""
        ops: list[tuple[str, str, AddSpec | None]] = [
            (ADD, name, spec) for name, spec in self.adds.items()
        ]
        for want in (ENABLE, DISABLE, REMOVE):
            ops += [(op, name, None) for name, op in self.state.items() if op == want]
        return ops

    def touches_refresh_file(self) -> bool:
        """True when Accept must rewrite the refresh-state file."""
        return bool(self.refresh) or REMOVE in self.state.values()

    def resolved_refresh(self, current_on: set[str]) -> set[str]:
        """Final refresh name-set: current, minus removed, with staged toggles applied."""
        result = set(current_on)
        result.difference_update(
            name for name, op in self.state.items() if op == REMOVE)
        for name, on in self.refresh.items():
            result.add(name) if on else result.discard(name)
        return result
