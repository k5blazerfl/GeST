"""The GeSI install wizard (urwid) — the YaST-gated front end.

``gest --install`` launches straight into this wizard rather than the admin menu.
The first gate is System Role (:mod:`gest.tui.screens.install.role`), which
proposes a coherent selection (``assemble.propose``) so later steps edit real
defaults instead of blank fields. The engine/run path is unchanged — the wizard
just assembles the same :class:`~gest.core.install.assemble.InstallSelections`.
"""
