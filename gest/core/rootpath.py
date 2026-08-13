"""The target-root seam for GeST's file-writing config modules.

Every module that renders a config file and writes it (system, network, sshd,
privilege, sysctl, envd, wifi, firewall) manages one or more *absolute* paths on
the system it configures — ``/etc/hosts``, ``/etc/conf.d/net`` and so on. To let
the future installer point those same writers at a target under ``/mnt/gentoo``
without forking any module's logic, each write RPC takes a ``root`` (default
``/``) and resolves its managed paths under it. This module is the one place that
knows how a ``root`` maps an absolute path to its on-disk location and what a safe
``root`` is.

It mirrors :mod:`gest.core.disk.mount`'s target-root guard, but the seam is a
*superset*: a config write is also valid against the running system (``root ==
"/"``), whereas assembling an install target never is. When ``root == "/"`` every
helper here is a no-op, so a maintenance write behaves byte-for-byte as before;
only an install directs writes elsewhere.

Safety: a non-``/`` root is confined to the ``/mnt`` / ``/media`` / ``/run/media``
prefixes (the same confinement the ``disk.mounttarget`` polkit action enforces),
so a target write can never land on the running system.
"""

from __future__ import annotations

# A confined install target lives under one of these; never the running tree.
ALLOWED_TARGET_ROOTS = ("/mnt", "/media", "/run/media")


def valid_config_root(root: str) -> bool:
    """True for the running system (``/``) or a confined install target.

    An install target must be a syntactically valid absolute path strictly under
    one of :data:`ALLOWED_TARGET_ROOTS` — so ``/``, ``/mnt/gentoo`` and
    ``/media/usb`` are accepted but ``/home``, a bare ``/mnt`` or ``/mnt/../etc``
    are refused.
    """
    if root == "/":
        return True
    if not root.startswith("/") or ".." in root.split("/"):
        return False
    return any(root.startswith(prefix + "/") for prefix in ALLOWED_TARGET_ROOTS)


def guard_config_root(root: str) -> None:
    """Raise ``ValueError`` unless ``root`` is a valid config root."""
    if not valid_config_root(root):
        raise ValueError(
            f"config root must be / or under /mnt|/media|/run/media: {root!r}")


def is_target(root: str) -> bool:
    """True when writing to an install target (not the running system).

    The signal a writer uses to skip live/runtime commands: a config written into
    a target root is not the running system's config, so ``env-update``, ``sysctl
    -p``, service reloads and the like must not run.
    """
    return root not in ("", "/")


def resolve(root: str, abs_path: str) -> str:
    """Map an absolute managed path to its location under ``root``.

    ``resolve("/", "/etc/hosts")`` is ``/etc/hosts`` unchanged; ``resolve(
    "/mnt/gentoo", "/etc/hosts")`` is ``/mnt/gentoo/etc/hosts``. A trailing slash
    on ``root`` is tolerated.
    """
    if root in ("", "/"):
        return abs_path
    return root.rstrip("/") + abs_path
