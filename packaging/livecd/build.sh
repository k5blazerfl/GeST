#!/usr/bin/env bash
# Render the catalyst specs from config.env + the templates, then build the GeST
# installer live image.
#
#   packaging/livecd/build.sh [arch] [desktop|cli] [--out-dir DIR]
#
# --out-dir DIR (optional): after the build, copy the finished ISO + a .sha256
# into DIR (a local staging area, e.g. GeST/iso). Off by default; the path is
# caller-supplied so no machine-specific location is baked into the build.
#
# Two amd64 flavors:
#   * desktop (default) — the full HeDE live image: boots into the Helm Desktop
#     Environment, install GeST from there. Big; slow to rebuild.
#   * cli — the barebones GeSI CLI installer: a small console-only ISO that boots
#     straight into GeST's guided "Install Gentoo" TUI (YaST-style). No desktop,
#     no display server, no Plymouth — fast to build, for iterating a real-metal
#     install without rebuilding the whole desktop stack every change.
#
# Prerequisites on the build host (a Gentoo box):
#   * dev-util/catalyst installed and configured (/etc/catalyst/catalyst.conf)
#   * a portage snapshot and a stage3 seed staged under catalyst's builds/
#   * config.env filled in (SNAPSHOT / STAGE3 / GEST_OVERLAY), and the GeST
#     overlay cloned to GEST_OVERLAY (this repo's packaging/overlay/)
#
# The rendered specs land in packaging/livecd/build/ and are what catalyst runs.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
outdir="${here}/build"

# Positional args: [arch] [flavor]. Optional flag: --out-dir DIR.
arch="amd64"
flavor="desktop"
out_dir=""
positional=()
while [ $# -gt 0 ]; do
    case "$1" in
        --out-dir)   out_dir="${2:?--out-dir needs a directory}"; shift 2 ;;
        --out-dir=*) out_dir="${1#*=}"; shift ;;
        -h|--help)   echo "usage: build.sh [arch] [desktop|cli] [--out-dir DIR]"; exit 0 ;;
        -*)          echo "unknown option: $1" >&2; exit 1 ;;
        *)           positional+=("$1"); shift ;;
    esac
done
[ "${#positional[@]}" -ge 1 ] && arch="${positional[0]}"
[ "${#positional[@]}" -ge 2 ] && flavor="${positional[1]}"
specdir="${here}/${arch}"

[ -d "${specdir}" ] || { echo "no specs for arch '${arch}'" >&2; exit 1; }

case "${flavor}" in
    desktop)
        stage1_in="livecd-stage1.spec.in"
        stage2_in="livecd-stage2.spec.in"
        packages_file="gest.packages"
        fsscript_file="fsscript.sh"
        overlay_dir="overlay"
        motd_file="motd"
        iso_stem="gest-installer-${arch}"
        ;;
    cli)
        stage1_in="livecd-stage1-cli.spec.in"
        stage2_in="livecd-stage2-cli.spec.in"
        packages_file="gest-cli.packages"
        fsscript_file="fsscript-cli.sh"
        overlay_dir="overlay-cli"
        motd_file="motd-cli"
        iso_stem="gesi-cli-${arch}"
        ;;
    *)
        echo "unknown flavor '${flavor}' (want: desktop | cli)" >&2; exit 1 ;;
esac
[ -f "${specdir}/${stage1_in}" ] || { echo "no ${stage1_in} for arch '${arch}'" >&2; exit 1; }
[ -f "${here}/config.env" ] || { echo "missing ${here}/config.env" >&2; exit 1; }

# shellcheck source=/dev/null
source "${here}/config.env"

# One timestamp for both stages (stage2 sources stage1 by it).
if [ -z "${TIMESTAMP:-}" ]; then
    TIMESTAMP="$(date -u +%Y%m%d)"
fi

# Sanity: refuse to build with the placeholder values still in place.
case "${SNAPSHOT}${STAGE3}" in
    *CHANGE-ME*) echo "!! fill SNAPSHOT and STAGE3 in ${here}/config.env first." >&2; exit 2 ;;
esac

# The cli flavor builds the LIVE IMAGE against the *base* systemd profile, not the
# desktop one in config.env: a console installer needs no X/Wayland/mesa USE, and
# the desktop profile drags mesa/opengl/libX* into the closure (bigger + slower to
# build) for nothing. Derive it by dropping the `desktop/` segment, so it tracks
# whatever release the desktop profile targets. This is the profile the LIVE MEDIUM
# is built with only — the profile GeST sets on the INSTALLED target is chosen
# separately by the installer (assemble.profile_name), so this doesn't change what
# a user ends up installing.
if [ "${flavor}" = cli ]; then
    PROFILE="${PROFILE/desktop\//}"
    echo "cli flavor: building the live image against base profile '${PROFILE}'"
fi

# Paths the templates reference (ASAHI_OVERLAY is arm64-only; harmless on amd64).
export PROFILE SNAPSHOT STAGE3 GEST_OVERLAY TIMESTAMP
export ASAHI_OVERLAY="${ASAHI_OVERLAY:-}"
# The Amphitheater overlay, where gui-apps/hede (the amd64 desktop) lives. Only
# the amd64 DESKTOP specs reference it; the cli flavor has no desktop, so force it
# empty there — that also makes assert-iso-versions.sh skip its hede check.
if [ "${flavor}" = cli ]; then
    export HEDE_OVERLAY=""
else
    export HEDE_OVERLAY="${HEDE_OVERLAY:-}"
fi
if [ "${flavor}" = cli ]; then
    export PORTAGE_CONFDIR="${here}/portage-conf-cli"   # no qt/desktop USE + base-profile fixups
else
    export PORTAGE_CONFDIR="${here}/portage-conf"
fi
export MOTD="${specdir}/${motd_file}"
export FSSCRIPT="${specdir}/${fsscript_file}"
# Files copied verbatim into the image root (e.g. /etc/greetd/config.toml, which
# autologins into HeDE). Optional — only wired if the arch ships an overlay/ dir.
# For amd64 we point catalyst at a build-time STAGING copy of the overlay so the
# build can add the quickpkg-fixup binpkgs (real, source-built binpkgs for
# image-mutating packages — see stage_binpkg_fixups + gest/core/install/desktop.py)
# after stage1 fills catalyst's pkgcache, without dirtying the tracked overlay/.
staging_overlay="${outdir}/root-overlay"
if [ "${arch}" = "amd64" ] && [ -d "${specdir}/${overlay_dir}" ]; then
    # amd64 (both flavors): build against a STAGING copy of the tracked overlay so the
    # build can inject the gentoo license texts (so the installer's License gate can
    # [View] the real firmware/NVIDIA/EULA agreements — catalyst strips the tree) and,
    # desktop only, the quickpkg binpkg fixups — without dirtying the tracked overlay/.
    export ROOT_OVERLAY="${staging_overlay}"
else
    # non-amd64: the tracked overlay is used verbatim.
    export ROOT_OVERLAY="${specdir}/${overlay_dir}"
fi
# Kernel .config genkernel builds from (CD-boot filesystems compiled in). Only
# referenced by the amd64 stage2 spec.
export KERNEL_CONFIG="${specdir}/kernel-config"

mkdir -p "${outdir}"

# Stage the tree's license TEXTS into the image at /var/db/repos/gentoo/licenses so
# the installer's License gate can [View] the ACTUAL agreement (firmware, NVIDIA-r2,
# any @EULA) — catalyst strips the portage tree from the image, so that dir is gone
# otherwise and gest's read_license_text falls back to one-line summaries. Copied
# fresh from the build host's synced tree (NOT committed to the repo). A minimal repo
# identity (layout.conf + repo_name) rides along so portage sees a well-formed, if
# licenses-only, gentoo repo in the live env — no "missing masters" nags.
stage_license_texts() {
    local reposrc="/var/db/repos/gentoo"
    local repodest="${staging_overlay}/var/db/repos/gentoo"
    if [ ! -d "${reposrc}/licenses" ]; then
        echo "!! ${reposrc}/licenses not found on build host — the License gate [View]" >&2
        echo "!! will fall back to one-line summaries. (Sync the gentoo tree to fix.)" >&2
        return 0
    fi
    mkdir -p "${repodest}/licenses" "${repodest}/metadata" "${repodest}/profiles"
    cp -a "${reposrc}/licenses/." "${repodest}/licenses/"
    [ -f "${reposrc}/metadata/layout.conf" ] && cp -a "${reposrc}/metadata/layout.conf" "${repodest}/metadata/"
    [ -f "${reposrc}/profiles/repo_name" ]   && cp -a "${reposrc}/profiles/repo_name"   "${repodest}/profiles/"
    echo "== staged $(find "${reposrc}/licenses" -maxdepth 1 -type f | wc -l) license texts → /var/db/repos/gentoo/licenses (License gate [View] shows the real agreements) =="
}

# Build a STAGING root overlay = the tracked overlay/ + the "quickpkg fixup"
# binpkgs. quickpkg @installed (the installer's desktop provisioning) captures each
# package's POST-pkg_preinst state, so any ebuild whose src_install/pkg_preinst
# juggle their own image (e.g. x11-misc/xkeyboard-config's xkb.workaround rename,
# bug #957712) yields a binpkg that dies on re-merge. The fix: ship those packages'
# REAL, source-built binpkgs (from catalyst's stage1 pkgcache, whose images are
# pre-preinst) under /var/cache/gest-binpkgs; ProvisionDesktop overlays them onto
# the quickpkg'd PKGDIR. We AUTO-DETECT the affected packages (any whose
# preinst/postinst/setup mv/rm/ln/cp within $ED/$D) so the set stays correct as the
# closure changes — no hand-maintained list. See docs/design/desktop-provisioning.md.
stage_binpkg_fixups() {
    local storedir="${STOREDIR:-/var/tmp/catalyst}"
    local stage1root="${storedir}/tmp/default/livecd-stage1-${arch}-gest-${TIMESTAMP}"
    local pkgcache="${storedir}/packages/default/livecd-stage1-${arch}"

    rm -rf "${staging_overlay}"
    mkdir -p "${staging_overlay}"
    cp -a "${specdir}/overlay/." "${staging_overlay}/"

    if [ ! -d "${stage1root}/var/db/pkg" ]; then
        echo "!! stage1 root not found (${stage1root}) — no binpkg fixups staged" >&2
        return 0
    fi
    local dest="${staging_overlay}/var/cache/gest-binpkgs"
    local n=0 pdir eb cat pf pn src
    for pdir in "${stage1root}"/var/db/pkg/*/*; do
        [ -d "${pdir}" ] || continue
        eb="$(ls "${pdir}"/*.ebuild 2>/dev/null | head -1)"; [ -n "${eb}" ] || continue
        # quickpkg-hostile signature: a phase that `mv`s an image path ($ED/$D) —
        # i.e. renames a build-only file (xkeyboard-config's xkb.workaround dodge).
        # quickpkg captures the post-rename state, so that source is gone → die. The
        # defensive cp/ln cache-restores from $EROOT are guarded and quickpkg-safe,
        # so we deliberately do NOT match them (they'd bloat the ISO for no reason).
        awk '
            /^(pkg_preinst|pkg_postinst|pkg_setup)[[:space:]]*\(\)/ {inph=1}
            inph { body=body $0 "\n"
                   if ($0 ~ /^\}/) {
                       if (body ~ /mv[^\n]*\$\{?(ED|D)\}?/) found=1
                       inph=0; body="" } }
            END { exit !found }
        ' "${eb}" || continue
        cat="$(basename "$(dirname "${pdir}")")"; pf="$(basename "${pdir}")"
        pn="$(echo "${pf}" | sed -E 's/-[0-9][^-]*(-r[0-9]+)?$//')"
        src="${pkgcache}/${cat}/${pn}"
        [ -d "${src}" ] || continue
        mkdir -p "${dest}/${cat}"
        cp -a "${src}" "${dest}/${cat}/"
        n=$((n + 1))
        echo "   fixup binpkg: ${cat}/${pn}"
    done
    echo "== staged ${n} real binpkg fixup(s) under ${dest#"${staging_overlay}"} =="
}

# stage1: render the template, then append the package list (tab-indented atoms,
# comments/blank lines stripped) under the `livecd/packages:` line.
envsubst < "${specdir}/${stage1_in}" > "${outdir}/livecd-stage1.spec"
grep -vE '^\s*(#|$)' "${specdir}/${packages_file}" | sed 's/^/\t/' \
    >> "${outdir}/livecd-stage1.spec"

# stage2: just the substitution.
envsubst < "${specdir}/${stage2_in}" > "${outdir}/livecd-stage2.spec"

echo "rendered:"
echo "  ${outdir}/livecd-stage1.spec"
echo "  ${outdir}/livecd-stage2.spec"

if [ "${RENDER_ONLY:-}" = "1" ]; then
    echo "(RENDER_ONLY=1 — stopping before catalyst)"; exit 0
fi

command -v catalyst >/dev/null || { echo "catalyst not installed (emerge dev-util/catalyst)" >&2; exit 3; }

# catalyst runs grub-mkrescue on the BUILD HOST (not in the chroot) to pack the
# ISO, so the host's sys-boot/grub decides which El Torito boot images the ISO
# gets. A UEFI-only host grub yields a UEFI-only ISO that BIOS machines can't
# boot. Warn loudly if the BIOS (i386-pc) platform is missing on x86 arches.
case "${arch}" in
    amd64|x86|i?86)
        if [ ! -d /usr/lib/grub/i386-pc ]; then
            echo "!! WARNING: host sys-boot/grub has no i386-pc platform — the ISO" >&2
            echo "!! will be UEFI-ONLY (BIOS machines won't boot it). Rebuild grub with" >&2
            echo "!!   GRUB_PLATFORMS=\"pc efi-64\" emerge -1 sys-boot/grub" >&2
            echo "!! then re-run this build for a BIOS+UEFI hybrid ISO." >&2
        fi
        ;;
esac

# Capture catalyst's output so the post-build assertion can confirm the image
# installed the versions the overlay offers — from source, not a stale binpkg
# (the silent-fallback bug that once stranded hede at 0.3.0). `set -o pipefail`
# (set at the top) keeps catalyst's exit status through the tee.
build_log="${outdir}/catalyst-${arch}-${TIMESTAMP}.log"
: > "${build_log}"

echo "== livecd-stage1 =="
catalyst -f "${outdir}/livecd-stage1.spec" 2>&1 | tee -a "${build_log}"
# Populate the STAGING root overlay now that stage1 has filled the pkgcache, so stage2
# lays it into the image (amd64). Desktop seeds it via stage_binpkg_fixups (a copy of
# overlay/ + the real binpkg fixups); cli seeds a plain copy of its tracked overlay.
# Both flavors then get the gentoo license texts injected for the installer's License
# gate ([View] the real firmware/NVIDIA/EULA agreements).
if [ "${arch}" = "amd64" ] && [ -d "${specdir}/${overlay_dir}" ]; then
    if [ "${flavor}" = desktop ]; then
        echo "== staging quickpkg-fixup binpkgs =="
        stage_binpkg_fixups
    else
        rm -rf "${staging_overlay}"; mkdir -p "${staging_overlay}"
        cp -a "${specdir}/${overlay_dir}/." "${staging_overlay}/"
    fi
    stage_license_texts
fi
echo "== livecd-stage2 =="
catalyst -f "${outdir}/livecd-stage2.spec" 2>&1 | tee -a "${build_log}"

# Gate: the image must have installed app-admin/gest (and gui-apps/hede on amd64)
# at the version the overlay offers, built from source. Fails the build on drift
# or a silent binpkg fallback. SKIP_VERSION_ASSERT=1 bypasses (not recommended).
#
# The cli flavor skips this: it is a local DEV-iteration image, not a release
# artifact, and a warm rebuild legitimately re-uses the cached gest binpkg of the
# CORRECT overlay version — which this source-only gate would reject. The gate
# stays ON for the desktop/release ISO, where a source build matters. To land NEW
# gest source in a cli ISO, bump the gest ebuild version (the normal release flow)
# so the cached binpkg no longer matches and portage rebuilds it.
if [ "${flavor}" != cli ] && [ "${SKIP_VERSION_ASSERT:-0}" != 1 ]; then
    echo "== asserting installed versions =="
    "${here}/assert-iso-versions.sh" "${build_log}"
fi

# Theme the ISO's GRUB menu (the Harbor look — pairs with the Plymouth splash).
# catalyst writes a plain grub.cfg onto the ISO filesystem, which the build can't
# reach otherwise, so this is a post-build inject. Desktop flavor only: the
# barebones CLI installer keeps a plain, fast GRUB menu (no splash to pair with).
# Best-effort: a plain menu still boots. STOREDIR defaults to catalyst's default;
# override if catalyst.conf moved it.
iso="${STOREDIR:-/var/tmp/catalyst}/builds/default/${iso_stem}-${TIMESTAMP}.iso"
if [ "${flavor}" = desktop ] && [ -f "${iso}" ]; then
    "${here}/grub-theme-inject.sh" "${iso}" \
        || echo "!! GRUB theme inject failed — the ISO still boots with a plain menu."
fi

# Optional publish: drop the finished ISO + a .sha256 sibling into --out-dir (a
# local staging area like GeST/iso). No-op unless --out-dir was given.
if [ -n "${out_dir}" ]; then
    if [ -f "${iso}" ]; then
        mkdir -p "${out_dir}"
        cp -f "${iso}" "${out_dir}/"
        ( cd "${out_dir}" && sha256sum "$(basename "${iso}")" > "$(basename "${iso}").sha256" )
        # Built via sudo (catalyst needs root)? Hand the published files back to the
        # invoking user so the staging dir isn't full of root-owned ISOs.
        if [ -n "${SUDO_USER:-}" ]; then
            chown "${SUDO_USER}" \
                "${out_dir}/$(basename "${iso}")" \
                "${out_dir}/$(basename "${iso}").sha256" 2>/dev/null || true
        fi
        echo "published: ${out_dir}/$(basename "${iso}")  (+ .sha256)"
    else
        echo "!! --out-dir set but no ISO at ${iso} — nothing to publish" >&2
    fi
fi

echo "done — the ISO is under catalyst's builds/ (livecd/iso: ${iso_stem}-${TIMESTAMP}.iso)."
