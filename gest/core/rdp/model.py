"""The RDP connection profile — pure data + the Keychain lookup attributes.

A profile is what the user configures per host; it maps to/from a ``.rdp`` file
(:mod:`gest.core.rdp.rdpfile`) and drives the FreeRDP argv
(:mod:`gest.core.rdp.commands`). The password is never stored here — only the
attributes Gangway looks it up by in the Secret Service.
"""

from __future__ import annotations

from dataclasses import dataclass

# Quality profiles → a FreeRDP network hint + GFX pipeline (see commands.py).
QUALITY_LAN = "lan"
QUALITY_BALANCED = "balanced"
QUALITY_WAN = "wan"
QUALITIES = (QUALITY_LAN, QUALITY_BALANCED, QUALITY_WAN)

# The Secret Service "service" attribute Gangway files its passwords under.
CRED_SERVICE = "gangway"


@dataclass(slots=True)
class RdpProfile:
    name: str  # the label / filename stem (not an RDP wire field)
    host: str
    port: int = 3389
    username: str = ""
    domain: str = ""

    fullscreen: bool = True
    width: int = 1920
    height: int = 1080
    multimon: bool = False
    dynamic_resolution: bool = True

    gateway_host: str = ""
    quality: str = QUALITY_BALANCED

    clipboard: bool = True
    drive_redirect: bool = True  # share a local folder as a drive
    audio_output: bool = True
    microphone: bool = False
    printers: bool = False

    nla: bool = True  # Network Level Authentication (CredSSP)

    def credential_attributes(self) -> dict[str, str]:
        """The Secret Service attributes this profile's password is stored under.
        Stable across edits to non-identity fields so a re-lookup still finds it."""
        attrs = {"service": CRED_SERVICE, "host": self.host, "port": str(self.port)}
        if self.username:
            attrs["user"] = self.username
        if self.domain:
            attrs["domain"] = self.domain
        return attrs

    def is_valid(self) -> bool:
        return bool(self.host) and self.quality in QUALITIES and 0 < self.port < 65536
