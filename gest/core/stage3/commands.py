"""Pure, validated argv builders for the stage3 module.

Two commands run as root while unpacking a stage3: ``tar`` to extract the tarball
into the target root (preserving permissions, extended attributes and numeric
owners, exactly as the Handbook prescribes), and ``gpg --verify`` for the
best-effort authenticity check of the detached signature. Both are pure and
CI-testable; the target-root safety confinement lives in the backend
(``core.disk.mount.guard_target_root``), not here.
"""

from __future__ import annotations


def tar_unpack_argv(tarball: str, root: str, *, tar: str = "tar") -> list[str]:
    """`tar xpf <tarball> -C <root> --xattrs-include=*.* --numeric-owner`.

    The Handbook's stage3 extraction flags: ``x`` extract, ``p`` preserve
    permissions, ``f`` from file, into ``root`` (``-C``), keeping every extended
    attribute (``--xattrs-include=*.*``, needed for capabilities/SELinux labels)
    and the tarball's numeric uid/gid rather than remapping to the host's.
    """
    return [tar, "xpf", tarball, "-C", root, "--xattrs-include=*.*", "--numeric-owner"]


def gpg_verify_argv(sig: str, target: str, *, gpg: str = "gpg") -> list[str]:
    """`gpg --verify <sig> <target>` — check the detached signature over the
    downloaded tarball against the keyring (best-effort; see the backend)."""
    return [gpg, "--verify", sig, target]


def download_argv(url: str, dest: str, *, wget: str = "wget", curl: str = "curl") -> list[str]:
    """Argv to fetch ``url`` to ``dest``, preferring wget, else curl.

    Mirrors the backend's downloader (``backend/stage3.py``) as a pure, testable
    builder for the installer's direct-path stage3 unpack: wget gives clean,
    periodic ``dot:giga`` progress; a falsy ``wget`` (e.g. ``wget=""`` when the
    caller detected it is absent) falls back to a ``curl -L --fail`` download.
    Both write to ``-O``/``-o dest`` so the URL is the final positional argument
    and never mistaken for a flag.
    """
    if wget:
        return [wget, "--progress=dot:giga", "-O", dest, url]
    return [curl, "-L", "--fail", "-o", dest, url]
