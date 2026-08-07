"""Install *preview* — what `emerge` would do, without doing it.

``emerge --pretend`` changes nothing, so it is a read-only operation and runs as
the invoking user (like the rest of :mod:`gest.core.software.reader`). This is
deliberately *not* routed through the privileged backend: the preview works even
before the root service is installed, and there is nothing to authorize.

The actual merge is a different story — that goes through
:mod:`gest.core.software.backend_client` and polkit.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

_EMERGE = shutil.which("emerge") or "/usr/bin/emerge"

# A runner turns an argv into (returncode, combined_output). Injectable so tests
# don't have to spawn a real emerge.
Runner = Callable[[list[str]], "tuple[int, str]"]


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout
    if proc.stderr:
        out = f"{out}\n{proc.stderr}" if out else proc.stderr
    return proc.returncode, out


@dataclass(slots=True)
class PreviewResult:
    """The outcome of an `emerge --pretend` for a single atom."""

    atom: str
    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def summary(self) -> str:
        """A one-line headline: emerge's ``Total:`` line, or a fallback."""
        for line in self.output.splitlines():
            if line.startswith("Total:"):
                return line.strip()
        if not self.ok:
            # surface the first emerge error line if resolution failed
            for line in self.output.splitlines():
                stripped = line.strip()
                if stripped.startswith("!!!") or "error" in stripped.lower():
                    return stripped.lstrip("! ").strip()
            return "emerge could not resolve this package"
        return "nothing to do"


def preview_world(*, runner: Runner | None = None) -> PreviewResult:
    """Preview a full system update: emerge --pretend -uDN @world."""
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n", "-uDN", "@world"]
    returncode, output = run(argv)
    return PreviewResult(atom="@world", returncode=returncode, output=output.strip())


def preview_install(
    atom: str, *, changed_use: bool = False, runner: Runner | None = None
) -> PreviewResult:
    """Return what merging ``atom`` would do, per ``emerge --pretend``.

    With ``changed_use`` the preview reflects a rebuild triggered by changed
    USE flags (``--changed-use``) rather than a fresh install.
    """
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n"]
    if changed_use:
        argv.append("--changed-use")
    argv.append(atom)
    returncode, output = run(argv)
    return PreviewResult(atom=atom, returncode=returncode, output=output.strip())
