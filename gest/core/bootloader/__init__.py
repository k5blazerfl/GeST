"""Bootloader & kernel module core.

Read-only kernel/bootloader facts are unprivileged; regenerating the bootloader
config goes through the polkit-gated backend. Pure parsing is CI-testable.
"""
