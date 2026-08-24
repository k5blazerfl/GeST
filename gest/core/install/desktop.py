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
    "media-libs/vulkan-loader", "gui-wm/labwc", "gui-libs/wlroots",
    "gui-apps/foot", "gui-apps/swaylock", "kde-frameworks/layer-shell-qt",
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


def has_desktop_binpkg(root: str = "") -> bool:
    """True if the target PKGDIR already carries a ``gui-apps/hede`` binpkg.

    The desktop ISO quickpkg's the running HeDE system, so this is True and the
    install goes binary-only + offline. The barebones CLI ISO ships no HeDE, so
    it's False — and the desktop is fetched from the overlay/binhost instead."""
    import os
    d = f"{root}{PKGDIR}/gui-apps"
    try:
        return any(name.startswith("hede") for name in os.listdir(d))
    except OSError:
        return False


def overlay_seeded(root: str = "") -> bool:
    """True if the Amphitheater overlay content is already in the target (seeded
    from the ISO) — then gui-apps/hede is reachable with no git sync."""
    import os
    return os.path.isdir(f"{root}{OVERLAY_LOCATION}")


def sync_overlay_argv() -> list[str]:
    """Force-sync just the Amphitheater overlay (git) — how the CLI ISO gets the
    ``gui-apps/hede`` ebuilds when the ISO didn't seed them. ``emaint`` syncs the
    named repo on demand regardless of its ``auto-sync`` setting."""
    return ["emaint", "sync", "-r", OVERLAY_NAME]


def emerge_tool_argv(atom: str) -> list[str]:
    """Emerge a single build-time tool into the target (binhost, source fallback) —
    e.g. dev-vcs/git, which the base stage3 lacks but the git overlay sync needs."""
    return ["emerge", "--getbinpkg", "--color", "n", atom]


def emerge_desktop_argv(*, atoms: tuple[str, ...] = DESKTOP_ATOMS,
                        binary_only: bool = True) -> list[str]:
    """Emerge the desktop atoms into the target, recorded in @world (no --oneshot).

    ``binary_only`` (desktop ISO) uses ``--usepkgonly``: install from the quickpkg'd
    binpkgs — offline, no ebuild tree, never recompiles. Otherwise (CLI ISO) use
    ``--getbinpkg``: pull from the binhost when one is configured, else build from
    the synced overlay + tree."""
    mode = "--usepkgonly" if binary_only else "--getbinpkg"
    return ["emerge", mode, "--color", "n", *atoms]


def cleanup_pkgdir_argv(*, root: str = "") -> list[str]:
    """Remove the transient ``@installed`` binpkgs from the target after the emerge."""
    return ["rm", "-rf", f"{root}{PKGDIR}"]


# --- quickpkg fixups: real binpkgs for image-mutating packages ---------------
#
# quickpkg @installed captures each package's POST-pkg_preinst state, so any ebuild
# whose src_install/pkg_preinst juggle their own image break on re-merge — e.g.
# x11-misc/xkeyboard-config renames xkb→xkb.workaround in src_install then
# xkb.workaround→xkb in pkg_preinst (collision-check dodge, upstream bug #957712);
# the installed files are `xkb`, so the quickpkg'd binpkg's preinst can't find
# `xkb.workaround` → dies. A REAL --buildpkg binpkg's image is pre-preinst
# (`xkb.workaround`) and merges cleanly. The catalyst build stages such packages'
# real, source-built binpkgs here (auto-detected from its pkgcache — see
# packaging/livecd/build.sh); ProvisionDesktop overlays them onto the quickpkg'd
# PKGDIR, replacing the broken copies. See docs/design/desktop-provisioning.md.
BINPKG_FIXUP_DIR = "/var/cache/gest-binpkgs"


def binpkg_fixup_pairs(*, fixup_dir: str = BINPKG_FIXUP_DIR,
                       target_pkgdir: str) -> list[tuple[str, str]]:
    """For each ``<category>/<pn>`` dir shipped under ``fixup_dir`` (the real,
    source-built binpkgs), the ``(source, target)`` pair whose target copy in
    ``target_pkgdir`` must be replaced. Pure listing — the caller does the rm+copy,
    so it stays unit-testable. Empty list if the image ships no fixups (older ISO /
    base-Gentoo install)."""
    import os
    if not os.path.isdir(fixup_dir):
        return []
    pairs: list[tuple[str, str]] = []
    for category in sorted(os.listdir(fixup_dir)):
        cat_src = os.path.join(fixup_dir, category)
        if not os.path.isdir(cat_src):
            continue
        for pn in sorted(os.listdir(cat_src)):
            if os.path.isdir(os.path.join(cat_src, pn)):
                pairs.append((os.path.join(cat_src, pn),
                              os.path.join(target_pkgdir, category, pn)))
    return pairs


def regen_binhost_argv() -> list[str]:
    """Rebuild the target PKGDIR's ``Packages`` index (chroot). Run after the fixup
    binpkgs replaced quickpkg's copies — else ``--usepkgonly`` reads a stale index
    (wrong filename/hash for the swapped packages) and refuses them."""
    return ["emaint", "binhost", "--fix"]
