"""The @world set: read explicitly-installed packages and deselect them.

The world file (``/var/lib/portage/world``) is Portage's record of the packages
you asked for explicitly — everything else is a dependency. Removing an entry
does **not** unmerge it; it just drops it from @world so a later ``depclean``
may reclaim it once nothing needs it. Portage owns the file, so the canonical
mutation is ``emerge --deselect`` rather than editing the file behind its back.

This module is deliberately Portage-free and pure: the argv builder and its atom
validation are shared verbatim by the root backend and the tests, so a bus
caller can never smuggle an option-looking or malformed atom into the root
subprocess. Listing world members is left to the reader (it already computes
``world_member`` while walking the vardb).
"""

from __future__ import annotations

import re

# A cat/pkg atom, optionally version-operator-prefixed or slotted, as Portage
# writes them into the world file. Never starts with '-' (which emerge would
# read as an option) and contains no shell/whitespace metacharacters.
_ATOM_RE = re.compile(r"^[A-Za-z0-9=<>~*][A-Za-z0-9+._/:=<>~*!-]*$")


def valid_atom(atom: str) -> bool:
    """True if ``atom`` is safe to pass to ``emerge --deselect``."""
    return bool(_ATOM_RE.match(atom))


def deselect_argv(atoms, emerge: str = "emerge") -> list[str]:
    """Build the ``emerge --deselect`` argv, validating every atom.

    Raises :class:`ValueError` on an empty list or any atom that isn't a plain
    package atom — the backend calls this before spawning root, so a bad atom
    fails loudly instead of reaching the subprocess.
    """
    atoms = list(atoms)
    if not atoms or any(not valid_atom(a) for a in atoms):
        raise ValueError("invalid or empty atom list")
    return [emerge, "--deselect", "--color", "n", *atoms]


def unmerge_argv(atoms, emerge: str = "emerge") -> list[str]:
    """Build the ``emerge --unmerge`` argv, validating every atom.

    Unlike ``--depclean``, ``--unmerge`` removes exactly the named packages
    *without* a dependency safety check — it is how a repo-orphan (which
    depclean protects) is actually removed. Callers must therefore guard it
    (confirm + a reverse-dependency warning) before use. Atom validation is the
    same as :func:`deselect_argv`, so a bus caller cannot smuggle an
    option-looking or malformed atom into the root subprocess; raises
    :class:`ValueError` on an empty list or any bad atom.
    """
    atoms = list(atoms)
    if not atoms or any(not valid_atom(a) for a in atoms):
        raise ValueError("invalid or empty atom list")
    return [emerge, "--unmerge", "--color", "n", *atoms]
