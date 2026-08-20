#!/usr/bin/env bash
# Render the catalyst specs from config.env + the templates, then build the GeST
# installer live image.
#
#   packaging/livecd/build.sh amd64
#
# Prerequisites on the build host (a Gentoo box):
#   * dev-util/catalyst installed and configured (/etc/catalyst/catalyst.conf)
#   * a portage snapshot and a stage3 seed staged under catalyst's builds/
#   * config.env filled in (SNAPSHOT / STAGE3 / GEST_OVERLAY), and the GeST
#     overlay cloned to GEST_OVERLAY (this repo's packaging/overlay/)
#
# The rendered specs land in packaging/livecd/build/ and are what catalyst runs.
set -euo pipefail

arch="${1:-amd64}"
here="$(cd "$(dirname "$0")" && pwd)"
specdir="${here}/${arch}"
outdir="${here}/build"

[ -d "${specdir}" ] || { echo "no specs for arch '${arch}'" >&2; exit 1; }
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

# Paths the templates reference (ASAHI_OVERLAY is arm64-only; harmless on amd64).
export PROFILE SNAPSHOT STAGE3 GEST_OVERLAY TIMESTAMP
export ASAHI_OVERLAY="${ASAHI_OVERLAY:-}"
# The Amphitheater overlay, where gui-apps/hede (the amd64 desktop) lives. Only
# the amd64 specs reference it; harmless (empty) on arm64.
export HEDE_OVERLAY="${HEDE_OVERLAY:-}"
export PORTAGE_CONFDIR="${here}/portage-conf"
export MOTD="${specdir}/motd"
export FSSCRIPT="${specdir}/fsscript.sh"
# Files copied verbatim into the image root (e.g. /etc/greetd/config.toml, which
# autologins into HeDE). Optional — only wired if the arch ships an overlay/ dir.
# For amd64 we point catalyst at a build-time STAGING copy of the overlay so the
# build can add the quickpkg-fixup binpkgs (real, source-built binpkgs for
# image-mutating packages — see stage_binpkg_fixups + gest/core/install/desktop.py)
# after stage1 fills catalyst's pkgcache, without dirtying the tracked overlay/.
staging_overlay="${outdir}/root-overlay"
if [ "${arch}" = "amd64" ] && [ -d "${specdir}/overlay" ]; then
    export ROOT_OVERLAY="${staging_overlay}"
else
    export ROOT_OVERLAY="${specdir}/overlay"
fi
# Kernel .config genkernel builds from (CD-boot filesystems compiled in). Only
# referenced by the amd64 stage2 spec.
export KERNEL_CONFIG="${specdir}/kernel-config"

mkdir -p "${outdir}"

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
envsubst < "${specdir}/livecd-stage1.spec.in" > "${outdir}/livecd-stage1.spec"
grep -vE '^\s*(#|$)' "${specdir}/gest.packages" | sed 's/^/\t/' \
    >> "${outdir}/livecd-stage1.spec"

# stage2: just the substitution.
envsubst < "${specdir}/livecd-stage2.spec.in" > "${outdir}/livecd-stage2.spec"

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
# Stage the real binpkg fixups into the root overlay now that stage1 has filled the
# pkgcache, so stage2 lays them into the image. amd64 desktop image only.
if [ "${arch}" = "amd64" ] && [ -d "${specdir}/overlay" ]; then
    echo "== staging quickpkg-fixup binpkgs =="
    stage_binpkg_fixups
fi
echo "== livecd-stage2 =="
catalyst -f "${outdir}/livecd-stage2.spec" 2>&1 | tee -a "${build_log}"

# Gate: the image must have installed app-admin/gest (and gui-apps/hede on amd64)
# at the version the overlay offers, built from source. Fails the build on drift
# or a silent binpkg fallback. SKIP_VERSION_ASSERT=1 bypasses (not recommended).
if [ "${SKIP_VERSION_ASSERT:-0}" != 1 ]; then
    echo "== asserting installed versions =="
    "${here}/assert-iso-versions.sh" "${build_log}"
fi

# Theme the ISO's GRUB menu (the Harbor look — pairs with the Plymouth splash).
# catalyst writes a plain grub.cfg onto the ISO filesystem, which the build can't
# reach otherwise, so this is a post-build inject. Best-effort: a plain menu still
# boots. STOREDIR defaults to catalyst's default; override if catalyst.conf moved it.
iso="${STOREDIR:-/var/tmp/catalyst}/builds/default/gest-installer-amd64-${TIMESTAMP}.iso"
if [ -f "${iso}" ]; then
    "${here}/grub-theme-inject.sh" "${iso}" \
        || echo "!! GRUB theme inject failed — the ISO still boots with a plain menu."
fi

echo "done — the ISO is under catalyst's builds/ (livecd/iso: gest-installer-amd64-${TIMESTAMP}.iso)."
