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


def preview_sync() -> PreviewResult:
    """Informational 'preview' for a tree sync (emerge --sync has no --pretend)."""
    return PreviewResult(
        atom="@tree",
        returncode=0,
        output=(
            "Synchronize the Portage ebuild tree from the configured mirrors.\n"
            "This refreshes available package versions; it does not change\n"
            "installed packages. Press Sync to proceed."
        ),
    )


def preview_depclean(atom: str = "", *, runner: Runner | None = None) -> PreviewResult:
    """Preview a removal: emerge --pretend --depclean [atom] (safe; keeps deps)."""
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n", "--depclean"]
    if atom:
        argv.append(atom)
    returncode, output = run(argv)
    return PreviewResult(atom=atom or "@world", returncode=returncode, output=output.strip())


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


def preview_install_many(atoms, *, runner: Runner | None = None) -> PreviewResult:
    """Preview merging several atoms at once: emerge --pretend <atoms>.

    This is what the transactional Accept resolves before committing.
    """
    atoms = list(atoms)
    if not atoms:
        return PreviewResult(atom="", returncode=0, output="nothing selected")
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n", *atoms]
    returncode, output = run(argv)
    return PreviewResult(atom=" ".join(atoms), returncode=returncode, output=output.strip())


def preview_install_binary_many(
    atoms, *, only: bool, runner: Runner | None = None
) -> PreviewResult:
    """Preview a binary merge: emerge --pretend --getbinpkg [--usepkgonly] <atoms>.

    ``only`` forces binary packages (``--usepkgonly``): the pretend run fails
    cleanly if no binary is available. Without it, emerge prefers a binary and
    falls back to building from source.
    """
    atoms = list(atoms)
    if not atoms:
        return PreviewResult(atom="", returncode=0, output="nothing selected")
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n", "--getbinpkg"]
    if only:
        argv.append("--usepkgonly")
    argv += atoms
    returncode, output = run(argv)
    return PreviewResult(atom=" ".join(atoms), returncode=returncode, output=output.strip())


def preview_depclean_many(atoms, *, runner: Runner | None = None) -> PreviewResult:
    """Preview removing several atoms at once: emerge --pretend --depclean <atoms>."""
    atoms = list(atoms)
    if not atoms:
        return PreviewResult(atom="", returncode=0, output="nothing selected")
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--verbose", "--color", "n", "--depclean", *atoms]
    returncode, output = run(argv)
    return PreviewResult(atom=" ".join(atoms), returncode=returncode, output=output.strip())


def preview_unmerge_many(atoms, *, runner: Runner | None = None) -> PreviewResult:
    """Preview a forced removal: emerge --pretend --unmerge <atoms>.

    Unlike ``--depclean``, ``--unmerge`` removes exactly the named packages with
    no dependency safety net — the preview is what confirms *which* packages
    (and only those) would go, so the UI can warn before committing.
    """
    atoms = list(atoms)
    if not atoms:
        return PreviewResult(atom="", returncode=0, output="nothing selected")
    run = runner or _default_runner
    argv = [_EMERGE, "--pretend", "--color", "n", "--unmerge", *atoms]
    returncode, output = run(argv)
    return PreviewResult(atom=" ".join(atoms), returncode=returncode, output=output.strip())
