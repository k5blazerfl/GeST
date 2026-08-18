"""Desktop provisioning — the pure command/config builders for installing HeDE
onto the target (see ``docs/design/desktop-provisioning.md``).

The GeSI live image *is* a HeDE system, so "install the desktop" is: repackage
the running system's packages into binpkgs (``quickpkg @installed``), seed the
Amphitheater overlay + a git-backed ``repos.conf`` for day-2 updates, then
``emerge --usepkgonly`` the desktop into the target — offline, no recompile. The
registry wires these; every path/atom is built here so it is validated in one
place and unit-tested without a real system.
"""

from __future__ import annotations

# The desktop meta-package (its RDEPEND pulls labwc/foot/gest/wireplumber/…), the
# boot-splash engine, and the login manager. gui-apps/hede also ships the GRUB +
# Plymouth "hede" themes the seamless steps stage. On systemd, logind handles seat
# management, so no seatd. Together these satisfy the desktop + seamless deps.
DESKTOP_ATOMS = ("gui-apps/hede", "sys-boot/plymouth", "gui-libs/greetd")

# greetd's config on the installed system. HeDE's session is `helm-session`
# (labwc + the Helm shell); `default.target` is switched to graphical so systemd
# boots into it.
GREETD_CONFIG = "/etc/greetd/config.toml"


def greetd_autologin_config(user: str) -> str:
    """A greetd config that autologins ``user`` into the HeDE session. Mirrors the
    live CD's overlay config, but for the installed user (root if none was created)."""
    session = 'env QT_WAYLAND_DISABLE_WINDOWDECORATION=1 dbus-run-session helm-session'
    return (
        "# Managed by GeST — autologin into HeDE (the Helm Desktop Environment).\n"
        "[terminal]\n"
        "vt = 1\n\n"
        "[initial_session]\n"
        f'command = "{session}"\n'
        f'user = "{user}"\n\n'
        "[default_session]\n"
        f'command = "{session}"\n'
        f'user = "{user}"\n'
    )

# The published overlay carrying gest + hede (+ hiedi/pyrrha); present in the live
# image and git-syncable, so the installed system can update on its own terms.
OVERLAY_NAME = "amphitheater"
OVERLAY_LOCATION = "/var/db/repos/amphitheater"
OVERLAY_SYNC_URI = "https://github.com/k5blazerfl/Amphitheater"

# Portage's default binary-package dir. quickpkg writes here (via PKGDIR); the
# target's copy is transient — populated for the install, removed afterward.
PKGDIR = "/var/cache/binpkgs"


ACCEPT_KEYWORDS = "/etc/portage/package.accept_keywords/gest-hede"


# The HeDE desktop closure is ~arch (testing). This mirrors the live CD's build
# keyword list (packaging/livecd/portage-conf/package.accept_keywords) — a
# DELIBERATELY targeted set, NOT a blanket `*/* ~arch` (a global unstable keyword
# drags the toolchain, notably perl, ahead of the stable stage3 and slot-conflicts).
# Keep in sync with that file.
_DESKTOP_KEYWORDED = (
    "app-admin/gest", "gui-apps/hede", "gui-libs/greetd",
    "dev-libs/wayland", "dev-util/glslang", "dev-util/spirv-tools",
    "media-libs/vulkan-loader", "gui-wm/labwc",
    "dev-util/wayland-scanner", "dev-util/vulkan-headers", "dev-util/spirv-headers",
)


def accept_keywords(arch: str) -> str:
    """The target's ``package.accept_keywords`` for the HeDE desktop: accept
    ``~<arch>`` for the (curated) desktop closure so ``--usepkgonly`` can install
    the quickpkg'd binpkgs (else it masks them: "masked by: ~amd64 keyword")."""
    return "".join(f"{atom} ~{arch}\n" for atom in _DESKTOP_KEYWORDED)


def repos_conf() -> str:
    """The target's ``repos.conf/amphitheater.conf`` — a git-backed overlay entry.

    ``auto-sync = no``: the install seeds the overlay from the live image, and the
    installed system re-syncs from GitHub only when the user runs ``emerge --sync``.
    """
    return (
        f"[{OVERLAY_NAME}]\n"
        f"location = {OVERLAY_LOCATION}\n"
        "sync-type = git\n"
        f"sync-uri = {OVERLAY_SYNC_URI}\n"
        "auto-sync = no\n"
    )


def quickpkg_argv(*, pkgdir: str) -> list[str]:
    """Repackage every installed package on the *live* env into ``pkgdir``.

    ``@installed`` covers the full ``hede`` dependency closure, so the later
    ``--usepkgonly`` emerge never falls back to compiling. ``--include-config=y``
    bundles config files (no CONFIG_PROTECT surprises). ``pkgdir`` is normally the
    target's ``/var/cache/binpkgs`` (prefixed with the install root), so the
    binpkgs land where the chroot emerge reads them.
    """
    return ["env", f"PKGDIR={pkgdir}", "quickpkg", "--include-config=y", "@installed"]


def seed_overlay_argv(*, root: str = "") -> list[str]:
    """Copy the live image's Amphitheater overlay into the target (``root`` prefix)."""
    return ["cp", "-a", OVERLAY_LOCATION, f"{root}{OVERLAY_LOCATION}"]


def overlay_parent_argv(*, root: str = "") -> list[str]:
    """Ensure the target's ``/var/db/repos`` exists before seeding the overlay."""
    return ["mkdir", "-p", f"{root}/var/db/repos"]


def emerge_desktop_argv(*, atoms: tuple[str, ...] = DESKTOP_ATOMS) -> list[str]:
    """``emerge --usepkgonly`` the desktop: binary-only, so the install is offline,
    needs no ebuild tree, and never recompiles. Recorded in @world (no --oneshot)."""
    return ["emerge", "--usepkgonly", "--color", "n", *atoms]


def cleanup_pkgdir_argv(*, root: str = "") -> list[str]:
    """Remove the transient ``@installed`` binpkgs from the target after the emerge."""
    return ["rm", "-rf", f"{root}{PKGDIR}"]
