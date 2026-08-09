"""System logs module core.

A read-only viewer over the kernel ring buffer (`dmesg`), the OpenRC boot log,
and the readable files under /var/log. Everything is read as the invoking user;
sources that need root (e.g. dmesg when kernel.dmesg_restrict=1, or root-only log
files) are surfaced with a note rather than failing. Line colouring reuses the
TUI's ANSI renderer.
"""
