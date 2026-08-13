"""The host-side atomic writer the config registry steps use.

Every config ``FuncStep`` in the registry renders its file with the existing core
render/validate function and writes it here — never over D-Bus. This is the
install-time counterpart of the backend's ``_atomic_write``: it resolves the
managed absolute path under the target ``root`` via
:func:`gest.core.rootpath.resolve`, creates parent directories, and does a
temp-file + ``chmod`` + ``os.replace`` so a reader never sees a half-written file.

Confinement is deliberately *not* enforced here — a step's own guard
(``mount.guard_target_root`` on the chroot/stage3 seams, the ``rootpath`` config
guard, or the reviewed plan) decides what a safe root is; this helper only writes
where it is told, exactly like the backend's private ``_atomic_write``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile

from gest.core import rootpath


def write_under_root(root: str, abs_path: str, text: str, *, mode: int = 0o644) -> str:
    """Atomically write ``text`` to ``abs_path`` resolved under ``root``.

    ``resolve("/mnt/gentoo", "/etc/hosts")`` writes ``/mnt/gentoo/etc/hosts``;
    ``root == "/"`` writes the absolute path unchanged. Parent directories are
    created. Returns the path written.
    """
    path = rootpath.resolve(root, abs_path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return path
