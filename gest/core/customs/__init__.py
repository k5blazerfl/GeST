"""Customs — the foreign-app integration layer (docs/design/hede-windows-interop.md §2).

The shared spine that turns a *foreign* Windows program — a remote app over RDP
(Gangway) or a local ``.exe`` in a Wine/Proton prefix (Drydock) — into a
first-class HeDE citizen. Four jobs, all here on the GeST/core (Python) side:

* :mod:`gest.core.customs.desktop` — synthesize/refresh ``.desktop`` launcher
  entries (with jump-list Actions) so a foreign app shows up in ``helm-menu`` and
  can be pinned.
* :mod:`gest.core.customs.mime` — the MIME/URI associations Customs owns
  (``.rdp``/``rdp://`` for Gangway, ``.exe``/``.msi``/``.lnk`` for Drydock).
* :mod:`gest.core.customs.icons` — extract an icon from a Windows ``.exe``
  (icoutils ``wrestool``) and install it into the XDG icon theme.
* :mod:`gest.core.customs.identity` — map a running window's Wayland ``app_id`` /
  Xwayland ``WM_CLASS`` back to its synthesized ``.desktop`` so the foreign-toplevel
  taskbar shows the right icon/title.

Everything here is pure Python + file/argv building — unit-testable without a
compositor or the external tools. The runtime pieces (invoking ``wrestool`` /
``update-desktop-database``, and the C++ taskbar wiring in ``hede/``) are thin
shells over these helpers.
"""
