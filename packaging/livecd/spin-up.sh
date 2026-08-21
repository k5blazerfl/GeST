#!/usr/bin/env bash
# spin-up.sh — one command to build a GeST installer live ISO with the latest
# GeST and boot it in QEMU for testing.
#
#   sudo packaging/livecd/spin-up.sh [--uefi] [--no-boot] [--snapshot ID]
#                                    [--flavor systemd] [--storedir DIR]
#                                    [--hede-overlay DIR]
#
# It automates the catalyst inputs that build.sh otherwise assumes:
#   1. syncs this checkout's GeST overlay into /var/db/repos/gest (→ latest GeST)
#   1b. locates + refreshes the HeDE (Amphitheater) overlay (→ latest hede)
#   2. ensures a portage snapshot (or use --snapshot / an existing config.env)
#   3. downloads the latest stage3-amd64-<flavor> seed into catalyst's builds/
#   4. writes config.env (incl. HEDE_OVERLAY), runs build.sh, and boots the ISO
#
# Must run as root on a Gentoo host with catalyst + qemu installed:
#   sudo emerge -av dev-util/catalyst app-emulation/qemu sys-firmware/edk2-ovmf
#
# NOTE: catalyst's snapshot handling differs across major versions (dated
# squashfs vs. git treeish). If the auto snapshot value fails, re-run with an
# explicit --snapshot <id> — every other phase is version-stable.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"
arch="amd64"
flavor="systemd"   # HeDE is systemd-only; the live image seeds + boots systemd
mirror="https://distfiles.gentoo.org"
overlay_dst="/var/db/repos/gest"
hede_overlay="/var/db/repos/amphitheater"   # where gui-apps/hede lives (external repo)
boot=1
firmware="bios"
snapshot=""
storedir=""

while [ $# -gt 0 ]; do
    case "$1" in
        --uefi) firmware="uefi"; shift ;;
        --no-boot) boot=0; shift ;;
        --snapshot) snapshot="$2"; shift 2 ;;
        --flavor) flavor="$2"; shift 2 ;;
        --storedir) storedir="$2"; shift 2 ;;
        --hede-overlay) hede_overlay="$2"; shift 2 ;;
        -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

say() { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }
die() { echo "spin-up: $*" >&2; exit 1; }

# --- preflight --------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "run as root (catalyst writes to storedir and /var/db/repos)."
command -v catalyst >/dev/null || die "catalyst not installed — emerge dev-util/catalyst"
if [ "${boot}" = 1 ]; then
    command -v qemu-system-x86_64 >/dev/null || die "qemu not installed — emerge app-emulation/qemu (or pass --no-boot)"
fi

# catalyst storedir (where builds/ and snapshots live). Parse it from the config
# unless overridden; default to catalyst's own default.
if [ -z "${storedir}" ]; then
    storedir="$(sed -nE 's/^[[:space:]]*storedir[[:space:]]*=[[:space:]]*"?([^"#]+)"?.*/\1/p' \
                /etc/catalyst/catalyst.conf 2>/dev/null | tr -d '[:space:]' | head -1)"
    storedir="${storedir:-/var/tmp/catalyst}"
fi
[ -d "${storedir}" ] || die "catalyst storedir '${storedir}' not found (configure /etc/catalyst/catalyst.conf, or pass --storedir)"
say "catalyst storedir: ${storedir}"

# --- 1. GeST overlay (latest GeST) ------------------------------------------
say "Syncing the GeST overlay → ${overlay_dst}"
mkdir -p "${overlay_dst}"
rsync -a --delete "${repo_root}/packaging/overlay/" "${overlay_dst}/"
# register it if repos.conf doesn't already point somewhere at it
if ! grep -Rqs "location *= *${overlay_dst}" /etc/portage/repos.conf 2>/dev/null; then
    mkdir -p /etc/portage/repos.conf
    cat > /etc/portage/repos.conf/gest.conf <<REPO
[gest]
location = ${overlay_dst}
masters = gentoo
auto-sync = no
REPO
    echo "  registered /etc/portage/repos.conf/gest.conf"
fi

# --- 1b. HeDE (Amphitheater) overlay ----------------------------------------
# gui-apps/hede is NOT in this repo's overlay — it lives in the external
# Amphitheater overlay. It MUST reach the stage as an ebuild repo, else the
# resolver can't see hede-<current> and silently falls back to a stale hede
# binpkg from pkgcache (shipping an ancient desktop). So locate it, refresh it
# if it's a git checkout, register it, and (step 4) write HEDE_OVERLAY so the
# spec's `repos:` line includes it.
say "Locating the HeDE overlay → ${hede_overlay}"
[ -d "${hede_overlay}/gui-apps/hede" ] || die \
    "HeDE overlay not found at ${hede_overlay} (expected gui-apps/hede/). Clone \
k5blazerfl/Amphitheater there, or pass --hede-overlay DIR."
if [ -d "${hede_overlay}/.git" ]; then
    git -C "${hede_overlay}" pull --ff-only 2>/dev/null \
        && echo "  refreshed (git pull)" \
        || echo "  (could not fast-forward; using ${hede_overlay} as-is)"
fi
echo "  hede ebuilds: $(ls "${hede_overlay}/gui-apps/hede/"*.ebuild 2>/dev/null | \
    sed 's#.*/##;s/\.ebuild$//' | tr '\n' ' ')"
if ! grep -Rqs "location *= *${hede_overlay}" /etc/portage/repos.conf 2>/dev/null; then
    mkdir -p /etc/portage/repos.conf
    cat > /etc/portage/repos.conf/amphitheater.conf <<REPO
[amphitheater]
location = ${hede_overlay}
masters = gentoo
auto-sync = no
REPO
    echo "  registered /etc/portage/repos.conf/amphitheater.conf"
fi

# --- 1c. purge image-mutating binpkgs (gest, hede) --------------------------
# catalyst's pkgcache keeps binpkgs from prior builds and --usepkg prefers them.
# For the packages that DEFINE the image (built from our overlays) that is wrong
# on two counts: a stale binpkg silently substitutes an old version, and
# assert-iso-versions requires these built *from source*. Purge them so every
# build compiles gest + hede fresh from the just-synced overlays. Dep binpkgs are
# kept (they only speed the build; their versions don't gate the image).
say "Purging image-mutating binpkgs (gest, hede) from the pkgcache"
rm -rf "${storedir}"/packages/*/*/app-admin/gest \
       "${storedir}"/packages/*/*/gui-apps/hede 2>/dev/null || true
# Drop the binhost index too — it still lists the just-removed gpkgs, so --usepkg
# would try to fetch a "non-existent binary" and fail ("outdated index"). Portage
# regenerates the index by scanning on the next emerge; the remaining dep gpkgs
# are re-indexed automatically.
rm -f "${storedir}"/packages/*/*/Packages 2>/dev/null || true
echo "  gest + hede will be rebuilt from source (binhost index will regenerate)"

# --- 2. snapshot ------------------------------------------------------------
# Precedence: --snapshot > existing non-placeholder config.env > auto.
cfg="${here}/config.env"
if [ -z "${snapshot}" ] && [ -f "${cfg}" ]; then
    cur="$(sed -nE 's/^SNAPSHOT="?([^"]*)"?.*/\1/p' "${cfg}" | head -1)"
    case "${cur}" in ""|*CHANGE-ME*) ;; *) snapshot="${cur}" ;; esac
fi
if [ -z "${snapshot}" ]; then
    say "Making a portage snapshot (catalyst -s stable)"
    catalyst -s stable || die "snapshot failed — run 'catalyst -s <id>' yourself and pass --snapshot <id>"
    snapshot="stable"
    echo "  using snapshot id '${snapshot}' (pass --snapshot if your catalyst names it differently)"
else
    say "Using snapshot: ${snapshot}"
fi

# --- 3. latest stage3 seed --------------------------------------------------
say "Resolving the latest stage3-${arch}-${flavor}"
latest_url="${mirror}/releases/${arch}/autobuilds/latest-stage3-${arch}-${flavor}.txt"
# The .txt is PGP-clearsigned, so pull the stage3 path line out directly rather
# than assuming it's the first non-comment line (it isn't — the armor is).
relpath="$(curl -fsSL "${latest_url}" \
    | grep -oE "[0-9TZ]+/stage3-${arch}-${flavor}-[0-9TZ]+\.tar\.xz" | head -1)" \
    || die "could not fetch ${latest_url}"
[ -n "${relpath}" ] || die "no stage3 path in ${latest_url}"
tarname="$(basename "${relpath}")"                    # stage3-amd64-systemd-<stamp>.tar.xz
seed="${tarname%.tar.*}"                               # the source_subpath name (no ext)
seed_dir="${storedir}/builds/default"
seed_path="${seed_dir}/${tarname}"
mkdir -p "${seed_dir}"
if [ -f "${seed_path}" ]; then
    echo "  seed already present: ${seed_path}"
else
    echo "  downloading ${tarname}"
    curl -fSL --retry 3 -o "${seed_path}" "${mirror}/releases/${arch}/autobuilds/${relpath}" \
        || die "stage3 download failed"
fi
echo "  seed: default/${seed}"

# --- 4. write config.env ----------------------------------------------------
say "Writing ${cfg}"
cat > "${cfg}" <<CONFIG
# Generated by spin-up.sh $(date -u +%Y-%m-%dT%H:%M:%SZ). Re-run spin-up.sh to refresh.
PROFILE="default/linux/${arch}/23.0/desktop/systemd"
SNAPSHOT="${snapshot}"
STAGE3="${seed}"
GEST_OVERLAY="${overlay_dst}"
HEDE_OVERLAY="${hede_overlay}"
TIMESTAMP=""
CONFIG

# --- 5. build ---------------------------------------------------------------
say "Building the ISO (catalyst) — this takes a while"
"${here}/build.sh" "${arch}"

# --- 6. boot ----------------------------------------------------------------
iso="$(ls -t "${storedir}/builds"/*/gest-installer-${arch}-*.iso 2>/dev/null | head -1 || true)"
[ -n "${iso}" ] || die "build finished but no ISO found under ${storedir}/builds/"
say "Built: ${iso}"
if [ "${boot}" = 1 ]; then
    say "Booting in QEMU (${firmware})"
    "${here}/qemu-test.sh" "${iso}" "${firmware}"
else
    echo "Boot it with:  packaging/livecd/qemu-test.sh '${iso}' ${firmware}"
fi
