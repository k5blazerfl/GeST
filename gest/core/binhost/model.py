"""Data types for the binhost module."""

from __future__ import annotations

from dataclasses import dataclass

# The two FEATURES tokens that turn binary packages on and require signatures.
GETBINPKG = "getbinpkg"
REQUIRE_SIGNATURE = "binpkg-request-signature"


@dataclass(slots=True)
class Binhost:
    """One binary-package host — a section in ``binrepos.conf``."""

    name: str
    sync_uri: str = ""
    priority: str = ""
    verify_signature: bool = True
    location: str = ""
    managed: bool = False  # True if it lives in GeST's gest.conf (editable here)


@dataclass(slots=True)
class FeaturesState:
    """Whether the two binhost-related FEATURES tokens are set in make.conf."""

    getbinpkg: bool = False
    require_signature: bool = False
