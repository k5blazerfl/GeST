#!/usr/bin/env bash
# Build the GeST installer live image with catalyst.
#
#   packaging/livecd/build.sh amd64
#
# Prerequisites on the build host (a Gentoo box):
#   * dev-util/catalyst installed and configured (/etc/catalyst/catalyst.conf)
#   * a portage snapshot and a stage3 seed staged under catalyst's builds/
#   * the GeST overlay available where the stage1 spec's portage_overlay points
#
# The specs carry @PLACEHOLDER@s (snapshot id, stage3 seed, timestamp, overlay
# path) — fill them (or export them and let this script sed a working copy) before
# a real run. This wrapper just runs the two catalyst stages in order.
set -euo pipefail

arch="${1:-amd64}"
here="$(cd "$(dirname "$0")" && pwd)"
specdir="${here}/${arch}"

if [ ! -d "${specdir}" ]; then
    echo "no specs for arch '${arch}' (have: $(ls -d "${here}"/*/ 2>/dev/null))" >&2
    exit 1
fi

for f in livecd-stage1.spec livecd-stage2.spec; do
    if grep -q '@[A-Z0-9_]\+@' "${specdir}/${f}"; then
        echo "!! ${specdir}/${f} still has @PLACEHOLDER@s — fill them before building." >&2
        exit 2
    fi
done

echo "== livecd-stage1 =="
catalyst -f "${specdir}/livecd-stage1.spec"
echo "== livecd-stage2 =="
catalyst -f "${specdir}/livecd-stage2.spec"
echo "done — the ISO is under catalyst's builds/ (livecd/iso in the stage2 spec)."
