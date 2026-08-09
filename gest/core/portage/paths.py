"""The single source of truth for ``/etc/portage/`` file locations.

Every path honours Portage's ``PORTAGE_CONFIGROOT`` (normally ``/``, but an
alternate root when configuring a chroot or in tests). ``portage`` is imported
lazily so the pure codecs and their tests never require it.
"""

from __future__ import annotations

import os


def config_root() -> str:
    """Portage's ``PORTAGE_CONFIGROOT`` (``/`` if portage is unavailable)."""
    try:
        import portage

        return portage.settings["PORTAGE_CONFIGROOT"] or "/"
    except Exception:
        return "/"


def etc_portage(root: str | None = None) -> str:
    return os.path.join(root or config_root(), "etc", "portage")


def make_conf(root: str | None = None) -> str:
    return os.path.join(etc_portage(root), "make.conf")


def repos_conf_dir(root: str | None = None) -> str:
    return os.path.join(etc_portage(root), "repos.conf")


def binrepos_conf_dir(root: str | None = None) -> str:
    return os.path.join(etc_portage(root), "binrepos.conf")


def binhost_fragment(root: str | None = None) -> str:
    """The GeST-owned binary-host file, ``binrepos.conf/gest.conf``."""
    return os.path.join(binrepos_conf_dir(root), "gest.conf")


def package_dir(kind: str, root: str | None = None) -> str:
    """The ``package.<kind>`` directory (e.g. ``kind="use"`` → ``package.use``)."""
    return os.path.join(etc_portage(root), f"package.{kind}")


def gest_fragment(kind: str, root: str | None = None) -> str:
    """The GeST-owned drop-in ``package.<kind>/gest``."""
    return os.path.join(package_dir(kind, root), "gest")
