"""Launch orchestration for a Gangway profile.

Ties the pieces together: fetch the password from the Keychain, build the
FreeRDP argv, and spawn the client with the password on stdin (``/from-stdin``).
Both the credential fetch and the spawn are injectable, so the orchestration is
unit-testable without a keychain, FreeRDP, or an RDP host.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.rdp import commands, creds
from gest.core.rdp.model import RdpProfile

# (argv, stdin_bytes|None) -> exit code
Spawn = Callable[[list[str], bytes | None], int]
# attributes -> password|None
FetchPassword = Callable[[dict], str | None]


def _default_fetch(attributes: dict) -> str | None:
    return creds.lookup(attributes)


def _default_spawn(argv: list[str], stdin: bytes | None) -> int:
    return subprocess.run(argv, input=stdin).returncode


def launch(profile: RdpProfile, *, share_path: str | None = None,
           fetch_password: FetchPassword = _default_fetch,
           spawn: Spawn = _default_spawn) -> int:
    """Launch ``profile``. Returns the client's exit code.

    The password (if any) is written to FreeRDP's stdin; ``/from-stdin`` is only
    added when we actually have one, so a passwordless profile prompts normally.
    """
    password = fetch_password(profile.credential_attributes())
    argv = commands.build_argv(profile, share_path=share_path, from_stdin=bool(password))
    stdin = (password + "\n").encode() if password else None
    return spawn(argv, stdin)
