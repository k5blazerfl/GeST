"""The installer flow engine (installer step 4).

Thin orchestration over the existing modules, per docs/design/installer-flow-engine.md:
an ordered, resumable, progress-streaming pipeline that points the modules at a
target root under /mnt/gentoo and sequences them in Handbook order. This package
is the engine mechanics only — the step registry that wires the real module calls
(provision/mount/stage3/kernel/bootloader/…) lands on top of it.

- ``plan``: the ``InstallPlan`` value type (reviewed and approved before any step
  runs) plus ``Phase`` and the small ``UserSpec``/``NetworkSpec`` records.
- ``step``: the ``InstallStep`` protocol and the ``ArgvStep``/``FuncStep`` bases.
- ``context``: ``InstallContext`` (the runtime handle) and ``StateStore``.
- ``engine``: ``run_install`` — the loop that runs the steps, picks the host or
  chroot executor per step, streams progress, stops at the first failure, and
  always tears the pseudo-filesystems down in a ``finally``.
"""
