"""GeST — Gentoo System Tool.

A modular system-administration tool for Gentoo, in the spirit of openSUSE's
YaST2. The design is layered so frontends stay thin and swappable:

    tui/       full-screen urwid frontend (this release)  ── renders ──┐
    core/      frontend-agnostic modules (the real logic)   <────────────┘
    ipc/       shared D-Bus interface contract
    backend/   root D-Bus system service, polkit-gated

Golden rule: frontends never touch Portage or D-Bus directly. They call
``core``; ``core`` is the only thing that speaks to ``backend``.
"""

__version__ = "0.48.2"
