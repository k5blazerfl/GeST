"""Prepare a stage3 target for chroot, and tear the preparation down cleanly.

Between unpacking a stage3 and running anything inside the target (sync, profile,
the ``@world`` merge, kernel build, bootloader) the Handbook has one setup step:
bind the kernel pseudo-filesystems into the target and copy the live CD's DNS in
so ``emerge`` can resolve mirrors from within the chroot. This module owns that
setup and — critically — its teardown, which must run on failure too, or the
pseudo-mounts left behind keep the target from unmounting cleanly.

Split like the rest of core:

* ``commands`` — pure, validated argv builders (``mkdir -p``, the individual
  ``mount`` incantations, the propagation ``--make-*`` calls, ``umount -l``, and
  the ``cp --dereference`` of ``resolv.conf``);
* ``prepare``  — the ordered Handbook mount sequence, its reverse teardown, and
  the ``prepare_chroot`` / ``teardown_chroot`` apply functions that run them
  through an `Executor`.

Safety: every entry point guards the root with
:func:`gest.core.disk.mount.guard_target_root`, so preparation is confined to the
``/mnt`` / ``/media`` / ``/run/media`` prefixes and can never touch ``/``.
"""
