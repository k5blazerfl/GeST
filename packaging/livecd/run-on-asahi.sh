#!/usr/bin/env bash
# run-on-asahi.sh — install and run the latest GeST inside an already-installed
# Asahi Gentoo (Apple Silicon). This is the fastest way to exercise GeST on real
# M1/M2 hardware: no live-image build, just register this checkout's overlay and
# emerge app-admin/gest.
#
#   sudo packaging/livecd/run-on-asahi.sh [--run]
#
# --run also launches `gest` afterwards. Run this from an up-to-date GeST checkout
# on the Mac itself (or copy the repo over).
#
# NOTE: this runs GeST *on* Apple Silicon to test its modules; installing Gentoo
# *onto* another Apple-Silicon target with GeST is not yet complete (GeST's
# kernel/bootloader steps are x86-oriented — see the README "installer gap on
# Apple Silicon").
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"
overlay_dst="/var/db/repos/gest"
do_run=0
[ "${1:-}" = "--run" ] && do_run=1

[ "$(id -u)" -eq 0 ] || { echo "run as root (emerge + repos.conf)" >&2; exit 1; }

# Best-effort sanity: warn (don't block) if this doesn't look like Apple Silicon.
if [ -r /proc/cpuinfo ] && ! grep -qiE 'apple|m1|m2' /proc/cpuinfo 2>/dev/null; then
    echo "warning: this doesn't look like Apple Silicon — continuing anyway."
fi

echo "== registering the GeST overlay → ${overlay_dst}"
mkdir -p "${overlay_dst}"
rsync -a --delete "${repo_root}/packaging/overlay/" "${overlay_dst}/"
if ! grep -Rqs "location *= *${overlay_dst}" /etc/portage/repos.conf 2>/dev/null; then
    mkdir -p /etc/portage/repos.conf
    cat > /etc/portage/repos.conf/gest.conf <<REPO
[gest]
location = ${overlay_dst}
masters = gentoo
auto-sync = no
REPO
fi

echo "== accepting the ~arm64 keyword for app-admin/gest"
mkdir -p /etc/portage/package.accept_keywords
echo "app-admin/gest ~arm64" > /etc/portage/package.accept_keywords/gest

echo "== emerging app-admin/gest"
emerge --verbose --noreplace app-admin/gest

echo
echo "GeST installed. Run it with:  gest"
echo "(reload D-Bus if the polkit backend isn't seen yet:  rc-service dbus reload)"

if [ "${do_run}" = 1 ]; then
    exec gest
fi
