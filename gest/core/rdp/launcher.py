"""Tie a Gangway profile to the desktop via Customs.

Synthesize the ``.desktop`` launcher entry (and its stable desktop-id) for a
profile, so "Connect to <host>" appears in ``helm-menu`` and can be pinned, with
the ``.rdp``/``rdp://`` MIME types associated. The ``Exec`` points at the
``gangway-open <profile>`` stub that fetches creds and launches FreeRDP.
"""

from __future__ import annotations

import re

from gest.core.customs import mime
from gest.core.customs.desktop import DesktopEntry, build_exec
from gest.core.rdp.model import RdpProfile

GANGWAY_OPEN = "gangway-open"
# The stub that opens an arbitrary .rdp file / rdp:// URI ad-hoc (the MIME/URI
# handler's Exec points here, with a %u field code).
GANGWAY_RDP_OPEN = "gangway-rdp-open"
HANDLER_DESKTOP_ID = "gangway-rdp-handler"
# FreeRDP's SDL client presents this window class; identity-matching (Customs)
# folds in variants like "FreeRDP".
FREERDP_WM_CLASS = "sdl-freerdp"


def open_argv(profile_name: str) -> list[str]:
    return [GANGWAY_OPEN, profile_name]


def desktop_id(profile_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", profile_name.lower()).strip("-")
    return f"gangway-{slug}"


def desktop_entry(profile: RdpProfile) -> DesktopEntry:
    return DesktopEntry(
        name=f"{profile.name} (RDP)",
        exec=build_exec(open_argv(profile.name)),
        icon="gangway",
        comment=f"Remote Desktop to {profile.host}",
        categories=["Network", "RemoteAccess"],
        startup_wm_class=FREERDP_WM_CLASS,
        extra={"X-GeST-Origin": "gangway", "X-Gangway-Profile": profile.name},
    )


def handler_open_argv(target: str) -> list[str]:
    return [GANGWAY_RDP_OPEN, target]


def handler_desktop_entry() -> DesktopEntry:
    """A single, profile-independent launcher that *handles* a ``.rdp`` file or
    ``rdp://`` URI (``%u``). ``NoDisplay`` — it is a handler, not a menu entry —
    and it carries the ``.rdp``/``rdp://`` MIME types so it can be the default."""
    return DesktopEntry(
        name="Remote Desktop (.rdp)",
        exec=f"{build_exec([GANGWAY_RDP_OPEN])} %u",
        icon="gangway",
        comment="Open a .rdp file or rdp:// link",
        categories=["Network", "RemoteAccess"],
        mime_types=list(mime.GANGWAY_TYPES),
        no_display=True,
        extra={"X-GeST-Origin": "gangway"},
    )
