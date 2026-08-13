"""Pure, validated argv builders for the chroot preparation step.

Every builder here produces an argv that runs as root inside the live CD to set
up (or tear down) an install target for chroot. As in ``core/disk/commands``, a
path that doesn't match a strict, absolute, ``..``-free pattern is refused before
it can reach a privileged ``mount``/``umount``/``cp`` — the builders are pure (no
I/O), so the whole surface is CI-testable.

The mount incantations follow the current Gentoo Handbook:

* ``proc`` is a fresh ``proc`` mount;
* ``/sys`` and ``/dev`` are recursive bind mounts (``--rbind``) — so ``/dev/pts``
  and ``/dev/shm`` come along — then made ``rslave`` so unmount events propagate
  out of, but mount events don't leak into, the host;
* ``/run`` is a plain bind made ``slave``.

Teardown is a *lazy* unmount (``umount -l``), recursively (``-R``) for the
recursive binds, so a busy or already-detached mount doesn't wedge cleanup.
"""

from __future__ import annotations

from gest.core.disk.commands import valid_target_path


def _require_target_path(path: str) -> None:
    if not valid_target_path(path):
        raise ValueError(f"invalid target path: {path!r}")


def mkdir_p_argv(path: str, *, mkdir: str = "mkdir") -> list[str]:
    """Create ``path`` and any missing parents: ``mkdir -p <path>``."""
    _require_target_path(path)
    return [mkdir, "-p", path]


def mount_proc_argv(target: str, *, mount: str = "mount") -> list[str]:
    """Mount a fresh proc at ``target``: ``mount -t proc proc <target>``."""
    _require_target_path(target)
    return [mount, "-t", "proc", "proc", target]


def mount_pseudo_argv(
    source: str, target: str, *, rbind: bool = False, mount: str = "mount"
) -> list[str]:
    """Bind ``source`` onto ``target``: ``mount --bind`` (or ``--rbind``).

    ``rbind=True`` builds the recursive bind used for ``/sys`` and ``/dev`` so
    their submounts (``/dev/pts``, ``/dev/shm``, …) are carried into the target.
    """
    _require_target_path(source)
    _require_target_path(target)
    return [mount, "--rbind" if rbind else "--bind", source, target]


def make_propagation_argv(target: str, mode: str, *, mount: str = "mount") -> list[str]:
    """Set mount-propagation on ``target``: ``mount --make-<mode> <target>``.

    ``mode`` is ``"rslave"`` (for the recursive ``/sys`` and ``/dev`` binds) or
    ``"slave"`` (for the ``/run`` bind); anything else is refused.
    """
    if mode not in ("rslave", "slave"):
        raise ValueError(f"invalid propagation mode: {mode!r}")
    _require_target_path(target)
    return [mount, f"--make-{mode}", target]


def umount_lazy_argv(path: str, *, recursive: bool = False, umount: str = "umount") -> list[str]:
    """Lazily unmount ``path``: ``umount -l`` (``-R -l`` when ``recursive``).

    Lazy detaches even a busy mount; ``recursive`` also tears down everything
    below it, which is what the ``--rbind`` mounts (``/sys``, ``/dev``) need.
    """
    _require_target_path(path)
    return [umount, "-R", "-l", path] if recursive else [umount, "-l", path]


def cp_resolv_argv(root: str, *, cp: str = "cp") -> list[str]:
    """Copy the live DNS into the target with ``cp --dereference``.

    ``--dereference`` follows a symlinked ``/etc/resolv.conf`` (common under
    resolvconf/NetworkManager) so the target gets the real file, not a dangling
    link.
    """
    dest = root.rstrip("/") + "/etc/resolv.conf"
    _require_target_path(dest)
    return [cp, "--dereference", "/etc/resolv.conf", dest]
