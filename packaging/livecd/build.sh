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

# Paths the templates reference.
export PROFILE SNAPSHOT STAGE3 GEST_OVERLAY TIMESTAMP
export PORTAGE_CONFDIR="${here}/portage-conf"
export MOTD="${specdir}/motd"
export FSSCRIPT="${specdir}/fsscript.sh"

mkdir -p "${outdir}"

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

echo "== livecd-stage1 =="
catalyst -f "${outdir}/livecd-stage1.spec"
echo "== livecd-stage2 =="
catalyst -f "${outdir}/livecd-stage2.spec"
echo "done — the ISO is under catalyst's builds/ (livecd/iso: gest-installer-amd64-${TIMESTAMP}.iso)."
