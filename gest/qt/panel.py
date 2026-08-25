"""Qt-free helper for the Panel Layout module (unit-testable without PySide).

The module is a thin doorway onto HeDE's panel editor, ``helm-barnacle`` — the
second door onto the same engine the bar reads (docs/design/barnacle.md), so the
Control Center never reimplements the layout logic. This builds the launch argv
so it's testable without a display.
"""

from __future__ import annotations

# The panel editor binary (resolved on $PATH, like the other helm-* tools the
# Qt frontend drives). Absent when HeDE isn't installed — the module handles
# that at click time.
PANEL_EDITOR = "helm-barnacle"


def panel_editor_command() -> list[str]:
    """Argv to launch the panel editor."""
    return [PANEL_EDITOR]
