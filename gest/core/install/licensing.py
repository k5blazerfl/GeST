"""License-agreement review for the installer's license gate — the ``describe and
gate`` layer over the 3-rung ACCEPT_LICENSE policy.

The wizard's license step maps a rung (Libre / Redistributable / Full) to one
``ACCEPT_LICENSE`` string (:data:`plan.LICENSE_POLICIES`) — an abstract label you
pick blind. This module turns that rung, plus the concrete install, into the
**agreements it entails**, marks the ones *this* machine will actually exercise
(firmware always; ``NVIDIA-r2`` iff the proprietary driver; any ``@EULA`` a
selected package pulls), and flags **blockers** when the chosen rung can't cover a
required agreement — so the Libre-on-NVIDIA trap surfaces at the gate, pre-flight,
instead of as a masked-package wall at genkernel hours later.

It **describes and gates only**: the rung → ``ACCEPT_LICENSE`` value
(:func:`plan.license_accept_value`) is the single lever and is unchanged here.

See ``docs/design/gesi-license-gate.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gest.core.install.plan import license_accept_value

#: Where the Gentoo tree ships license texts on the live medium — the source for
#: the gate's ``[View]`` action.
LICENSE_DIR = "/var/db/repos/gentoo/licenses"

# ACCEPT_LICENSE group tokens. @BINARY-REDISTRIBUTABLE already contains @FREE, and
# Full = "@BINARY-REDISTRIBUTABLE @EULA", so a rung "covers" a group iff the token
# is present in its ACCEPT_LICENSE value (see _covers).
FREE = "@FREE"
BINARY_REDISTRIBUTABLE = "@BINARY-REDISTRIBUTABLE"
EULA = "@EULA"


@dataclass(frozen=True, slots=True)
class Agreement:
    """One license agreement the install may need to accept.

    ``name`` is the license file name in the tree (``LICENSE_DIR/<name>``, the
    ``[View]`` target); ``label`` is a short human tag; ``group`` is the
    ACCEPT_LICENSE token that covers it; ``required_by_this_install`` marks the
    ones the concrete plan will actually exercise (vs. merely covered by the rung).
    """

    name: str
    label: str
    group: str
    one_line: str
    required_by_this_install: bool = False

    @property
    def text_path(self) -> str:
        """Path to the license's full text on the live medium (the ``[View]`` file)."""
        return f"{LICENSE_DIR}/{self.name}"


@dataclass(frozen=True, slots=True)
class LicenseReview:
    """What a rung entails for a concrete install: the agreements to show, the
    blockers that must be resolved before Continue, and softer warnings."""

    rung: str
    accept_value: str
    #: Agreements the rung covers, worth showing (firmware + NVIDIA driver, plus any
    #: required EULA). Ordered required-first for display.
    entails: tuple[Agreement, ...]
    #: Hard problems — the rung can't cover something this install requires. Non-empty
    #: means the gate must refuse Continue.
    blockers: tuple[str, ...]
    #: Softer notices (e.g. a genuinely-libre install building firmware-free).
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when nothing blocks Continue (there may still be warnings)."""
        return not self.blockers

    @property
    def required(self) -> tuple[Agreement, ...]:
        """The entailed agreements this install will actually exercise."""
        return tuple(a for a in self.entails if a.required_by_this_install)

    def required_labels(self) -> tuple[str, ...]:
        """Short labels of the required agreements, for a compact chip/summary."""
        return tuple(a.label for a in self.required)


# --- the catalog ------------------------------------------------------------
# GeSI itself only ever exercises two non-free licenses: the Linux firmware blob
# license and the proprietary NVIDIA driver license. Both live in the redistributable
# bucket. We list them for every rung that covers them (marking which THIS install
# uses), rather than dumping the whole group.

def _firmware(required: bool) -> Agreement:
    return Agreement(
        "linux-fw-redistributable", "Firmware", BINARY_REDISTRIBUTABLE,
        "Linux firmware — Wi-Fi, GPU microcode and other device blobs. Redistributable "
        "binary blobs (sys-kernel/linux-firmware); most real hardware needs them.",
        required_by_this_install=required)


def _nvidia(required: bool) -> Agreement:
    return Agreement(
        "NVIDIA-r2", "NVIDIA driver", BINARY_REDISTRIBUTABLE,
        "Proprietary NVIDIA driver license (x11-drivers/nvidia-drivers) — the "
        "closed-source GeForce driver a modern NVIDIA card needs under Wayland/HeDE.",
        required_by_this_install=required)


#: Curated one-liners for click-through EULA licenses a selected package can pull.
#: Starts small and grows as packages that carry these land in the feature/role sets
#: (design phase 4). Anything not here still works — it falls back to a generic line.
_EULA_ONE_LINERS: dict[str, str] = {
    "NVIDIA-CUDA": "NVIDIA CUDA toolkit end-user license agreement.",
    "google-chrome": "Google Chrome browser terms of service.",
    "Steam": "Valve Steam subscriber agreement.",
    "RAR": "RARLAB unrar/WinRAR license.",
}


def _eula_agreement(name: str) -> Agreement:
    return Agreement(
        name, name, EULA,
        _EULA_ONE_LINERS.get(name, f"{name} — click-through end-user license agreement."),
        required_by_this_install=True)


def _covers(accept_value: str, group: str) -> bool:
    """Whether a rung's ACCEPT_LICENSE value covers a license group token."""
    return group in accept_value.split()


def review_licenses(rung: str, *, nvidia: bool = False,
                    eulas: Sequence[str] = ()) -> LicenseReview:
    """Review what ``rung`` entails for a concrete install.

    ``nvidia`` — the proprietary NVIDIA driver is planned (from
    ``plan.gpu.nvidia_proprietary`` / the detected GPU). ``eulas`` — specific
    ``@EULA`` license names a selected package pulls (best-effort; usually empty).

    Firmware is treated as needed by every real-hardware install. On the Libre rung
    that firmware/NVIDIA can't be satisfied: if NVIDIA was requested it's a
    **blocker** (you asked for a driver Libre can't provide); otherwise it's a
    **warning** (a genuinely-libre install is allowed and builds firmware-free).
    Raises ``ValueError`` on an unknown rung (via :func:`license_accept_value`).
    """
    accept = license_accept_value(rung)

    # Candidate agreements for display: firmware + NVIDIA are shown by any rung that
    # covers them (so Redistributable/Full show "NVIDIA driver — covered" even on an
    # AMD box), required-flagged per the plan; required EULAs are shown too.
    firmware = _firmware(required=True)
    nvidia_ag = _nvidia(required=nvidia)
    eula_ags = tuple(_eula_agreement(name) for name in eulas)

    covered = [a for a in (firmware, nvidia_ag, *eula_ags) if _covers(accept, a.group)]
    # required-first, stable within each half
    entails = tuple(sorted(covered, key=lambda a: not a.required_by_this_install))

    blockers: list[str] = []
    warnings: list[str] = []

    # Firmware / NVIDIA the rung can't cover (i.e. Libre).
    if not _covers(accept, BINARY_REDISTRIBUTABLE):
        if nvidia:
            blockers.append(
                "Libre (@FREE) can't provide the NVIDIA driver (NVIDIA-r2) or the "
                "firmware this machine needs. Choose Redistributable or Full, or turn "
                "off the proprietary NVIDIA driver.")
        else:
            warnings.append(
                "Libre (@FREE) excludes binary firmware — Wi-Fi, GPU microcode and "
                "similar may not work, and the kernel is built firmware-free. Choose "
                "Redistributable if this machine needs firmware.")

    # A selected package needs a click-through EULA the rung doesn't accept.
    uncovered_eulas = [a for a in eula_ags if not _covers(accept, a.group)]
    if uncovered_eulas:
        names = ", ".join(a.name for a in uncovered_eulas)
        blockers.append(
            f"This install needs click-through EULA licenses ({names}) that only Full "
            "accepts. Choose Full, or drop the packages that need them.")

    return LicenseReview(rung=rung, accept_value=accept, entails=entails,
                         blockers=tuple(blockers), warnings=tuple(warnings))


def license_agreements(plan) -> LicenseReview:
    """Review the license agreements a fully-assembled :class:`InstallPlan` entails —
    the convenience entry pulling the rung + NVIDIA fact off the plan. The wizard
    (which has only draft selections) calls :func:`review_licenses` directly."""
    return review_licenses(plan.license, nvidia=plan.gpu.nvidia_proprietary,
                           eulas=plan_eula_licenses(plan))


def plan_eula_licenses(plan) -> tuple[str, ...]:
    """The ``@EULA`` license names the plan's selected packages pull (best-effort).

    Empty today — GeSI's roles/feature set pull no click-through EULA packages — but
    the seam the relevance map grows into (design phase 4). Kept a pure function of
    the plan so the review stays deterministic and testable."""
    return ()


def read_license_text(name: str, *, licenses_dir: str = LICENSE_DIR) -> str:
    """The full text of a license from the tree (the ``[View]`` action), or ``""`` if
    it isn't present — e.g. on a non-Gentoo dev host, where the caller falls back to
    the agreement's one-line summary."""
    try:
        return Path(licenses_dir, name).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
