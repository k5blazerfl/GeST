#!/usr/bin/env bash
# assert-iso-versions.sh — post-build gate on a catalyst build log.
#
#   assert-iso-versions.sh <catalyst-build-log>
#
# After an ISO build, confirm the image installed the packages that MUTATE the
# image (app-admin/gest, and gui-apps/hede on amd64):
#   * from SOURCE, not a reused binary package — the silent-fallback bug that
#     once shipped an ISO with hede stranded at 0.3.0 while the overlay had moved
#     on (bug #10); a binpkg merge of an image-mutating package fails the build.
#   * at the version the OVERLAY offers — i.e. the newest ebuild in GEST_OVERLAY /
#     HEDE_OVERLAY. (Deliberately the overlay, not pyproject/source: a dev ISO
#     ships the last *released* ebuild, which may be behind an unreleased bump —
#     see stack-status.py, which checks source-vs-overlay separately.)
#
# Reads GEST_OVERLAY (required) and HEDE_OVERLAY (amd64) from the environment;
# build.sh exports both. Exit 0 = the image is coherent, 1 = drift / binpkg
# fallback / package never built.
set -euo pipefail

log="${1:?usage: assert-iso-versions.sh <catalyst-build-log>}"
[ -f "${log}" ] || { echo "assert-iso-versions: no such log: ${log}" >&2; exit 2; }

fail=0
note() { printf '  \033[1;31m✗\033[0m %s\n' "$*" >&2; fail=1; }
okay() { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }

# Newest X.Y.Z among <pkgdir>/<pkg>-*.ebuild (empty if the dir/pkg is absent).
# The `|| true` keeps a no-match `ls` from aborting the script under pipefail.
newest_ebuild_ver() {  # pkgdir pkg
    { ls "$1/$2"-*.ebuild 2>/dev/null || true; } \
        | sed -nE "s#.*/$2-([0-9]+\.[0-9]+\.[0-9]+)\.ebuild\$#\1#p" \
        | sort -V | tail -1
}

# The last "Emerging" line for a package atom in the build log (stage1 installs
# the livecd package set, so app-admin/gest is emerged there).
emerge_line() {  # cat/pkg
    grep -E "^>>> Emerging (binary )?\([0-9]+ of [0-9]+\) ${1}-[0-9]" "${log}" \
        | tail -1
}

# Assert one image-mutating package: built from source, at the overlay's version.
assert_pkg() {  # cat/pkg  overlay_dir  required(1|0)
    local atom="$1" odir="$2" required="$3"
    local pkg="${atom#*/}"
    local expected line ver
    expected="$(newest_ebuild_ver "${odir}" "${pkg}")"
    if [ -z "${expected}" ]; then
        [ "${required}" = 1 ] \
            && note "${atom}: no ebuild found under ${odir} — cannot verify" \
            || echo "  – ${atom}: no overlay ebuild, skipping"
        return
    fi
    line="$(emerge_line "${atom}" || true)"
    if [ -z "${line}" ]; then
        note "${atom}: never emerged in the build (expected ${expected}) — pulled from the seed/binpkg?"
        return
    fi
    if printf '%s' "${line}" | grep -q '^>>> Emerging binary '; then
        note "${atom}: merged from a BINARY package — image-mutating packages must build from source (the hede-0.3.0 fallback bug)"
        return
    fi
    ver="$(printf '%s' "${line}" | sed -nE "s#.* ${atom}-([0-9]+\.[0-9]+\.[0-9]+).*#\1#p")"
    if [ "${ver}" != "${expected}" ]; then
        note "${atom}: image merged ${ver} but the overlay offers ${expected}"
        return
    fi
    okay "${atom}: built ${ver} from source (matches overlay)"
}

echo "== verifying image-mutating package versions in ${log##*/}"
assert_pkg "app-admin/gest" "${GEST_OVERLAY:?GEST_OVERLAY not set}/app-admin/gest" 1
if [ -n "${HEDE_OVERLAY:-}" ]; then
    assert_pkg "gui-apps/hede" "${HEDE_OVERLAY}/gui-apps/hede" 1
fi

if [ "${fail}" = 1 ]; then
    echo "assert-iso-versions: FAILED — the ISO does not match the overlay." >&2
    exit 1
fi
echo "assert-iso-versions: OK"
