#!/usr/bin/env bash
# Publish a built GeSI live ISO as a GitHub Release.
#
#   packaging/livecd/release-iso.sh <iso> [tag]
#
# Defaults: <iso> = newest gest-installer-amd64-*.iso in the catalyst storedir;
#           tag   = gesi-<YYYYMMDD from the ISO name>.
#
# Why a helper: ISOs are large binaries that must NOT be committed (100 MB repo
# limit) and can't ride the `v*` release tags (those trigger the Overlay-sync
# ebuild Action). This uses a separate `gesi-*` tag, publishes a sha256 (and a
# GPG signature if you have a key), and refuses assets over GitHub's 2 GiB
# per-file limit — pointing you at external hosting if the ISO is too big.
set -euo pipefail

GITHUB_ASSET_LIMIT=$((2 * 1024 * 1024 * 1024))   # 2 GiB per release asset

storedir_default="/var/tmp/catalyst/builds/default"
iso="${1:-$(ls -t "${storedir_default}"/gest-installer-amd64-*.iso 2>/dev/null | head -1)}"
[ -n "${iso}" ] && [ -f "${iso}" ] || { echo "usage: $0 <iso> [tag]   (no ISO found in ${storedir_default})" >&2; exit 1; }

# Derive tag from the ISO's date stamp unless one was given.
stamp="$(basename "${iso}" | sed -nE 's/.*-([0-9]{8}).*\.iso/\1/p')"
tag="${2:-gesi-${stamp:-manual}}"
case "${tag}" in
    v*) echo "!! refusing tag '${tag}': v* tags trigger the ebuild Overlay-sync Action. Use gesi-* / iso-*." >&2; exit 2 ;;
esac

command -v gh >/dev/null || { echo "gh (GitHub CLI) not installed" >&2; exit 3; }

echo ">> ISO:  ${iso}  ($(du -h "${iso}" | cut -f1))"
echo ">> tag:  ${tag}"

# Checksum + optional detached GPG signature, written next to the ISO.
sha="${iso}.sha256"
( cd "$(dirname "${iso}")" && sha256sum "$(basename "${iso}")" > "${sha}" )
echo ">> wrote ${sha}"
assets=("${iso}" "${sha}")
if gpg --list-secret-keys >/dev/null 2>&1 && [ -n "$(gpg --list-secret-keys 2>/dev/null)" ]; then
    gpg --armor --detach-sign --yes "${iso}"
    assets+=("${iso}.asc")
    echo ">> wrote ${iso}.asc (GPG signature)"
else
    echo ">> (no GPG secret key — skipping signature)"
fi

# GitHub's per-file asset limit.
size=$(stat -c %s "${iso}")
if [ "${size}" -gt "${GITHUB_ASSET_LIMIT}" ]; then
    cat >&2 <<MSG
!! ISO is $(awk "BEGIN{printf \"%.2f\", ${size}/1024/1024/1024}") GiB — over GitHub's 2 GiB asset limit.
!! Options: shrink it (livecd/fsops in the stage2 spec), split it
!!   (split -b 1900M "${iso}" "${iso}.part-"), or host it externally and attach
!!   only ${sha}(.asc) to the release. Aborting the upload.
MSG
    exit 4
fi

# Create (or update) the release and upload.
if gh release view "${tag}" >/dev/null 2>&1; then
    echo ">> release ${tag} exists — uploading/clobbering assets"
    gh release upload "${tag}" "${assets[@]}" --clobber
else
    gh release create "${tag}" "${assets[@]}" \
        --title "GeSI installer — ${stamp:-manual}" \
        --notes "amd64 hybrid ISO (BIOS+UEFI); boots into HeDE. Disable Secure Boot to boot. Verify with the .sha256."
fi
echo ">> done: $(gh release view "${tag}" --json url -q .url)"
