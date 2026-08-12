"""Kernel-build module core.

Build a kernel the two ways the Handbook offers: ``genkernel all`` (automated —
config, compile, initramfs, install in one command), or a manual ``make`` on an
already-configured source tree (build → modules_install → install), optionally
followed by a dracut initramfs. Both are ordered command pipelines run as root,
so they build on the shared `gest.core.exec` step/executor machinery and stream —
in-process on a live CD, or via the polkit-gated streaming `Kernel` backend on an
installed system. Reading kernel-source state is unprivileged (`reader`).
"""
