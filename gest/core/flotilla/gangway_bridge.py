"""The Gangway bridge — a Windows vessel → a seamless RDP session.

Two pure pieces: parse a guest's IPv4 out of ``virsh domifaddr`` output, and
synthesize a Gangway :class:`RdpProfile` from a vessel + that address. The CLI
wires them (discover → provision the profile → launch Gangway). No libvirt here.
See ``docs/design/flotilla.md`` §5.
"""

from __future__ import annotations

import re

from gest.core.flotilla.model import Vessel
from gest.core.rdp.model import RdpProfile

# Gangway stores a profile by name as a filename; keep to its safe charset.
_UNSAFE = re.compile(r"[^A-Za-z0-9 _.-]")


def parse_agent_ipv4(domifaddr_output: str) -> str:
    """The guest's first non-loopback IPv4 from ``virsh domifaddr`` output
    (columns: Name / MAC / Protocol / Address, address as ``ip/prefix``)."""
    for line in domifaddr_output.splitlines():
        parts = line.split()
        if "ipv4" not in parts:
            continue
        idx = parts.index("ipv4")
        if idx + 1 >= len(parts):
            continue
        addr = parts[idx + 1].split("/")[0]
        if addr and not addr.startswith("127."):
            return addr
    return ""


def profile_for(vessel: Vessel, ip: str) -> RdpProfile:
    """A Gangway profile targeting a Windows vessel at ``ip`` — sensible defaults
    (clipboard/drive/audio redirect, NLA). The name is stable (so re-connecting
    updates the same profile) and safe for Gangway's filename-based store. The
    username is the local account the guest was provisioned with (§5/phase-5), so
    NLA/CredSSP matches and the Keychain lookup keys off the right user."""
    name = vessel.gangway_profile or (_UNSAFE.sub("", f"{vessel.name} VM").strip() or vessel.id)
    return RdpProfile(name=name, host=ip, username=vessel.unattend_username)
