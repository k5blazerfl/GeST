#!/usr/bin/env bash
# Inject the HeDE "Harbor" GRUB theme into a built GeSI ISO.
#
#   packaging/livecd/grub-theme-inject.sh <iso> [theme-dir]
#
# catalyst's generic-livecd writes a plain text grub.cfg onto the ISO (it already
# sets `gfxpayload=keep` + `insmod all_video`), and that file lives on the ISO
# filesystem — not the squashfs the root overlay reaches — so it can't be themed
# from inside the build. This post-build step rewrites that grub.cfg to switch to
# gfxterm + the Helm theme and drops the theme files onto the ISO, preserving the
# hybrid (BIOS+UEFI) boot via `xorriso -boot_image any replay`.
#
# The theme (background.png, theme.txt, hede.pf2) is the same one gui-apps/hede
# installs to /usr/share/hede/grub/hede; here we take it from this checkout so
# the build host doesn't need HeDE installed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
iso="${1:?usage: grub-theme-inject.sh <iso> [theme-dir]}"
theme_src="${2:-${here}/../../hede/data/grub/hede}"

[ -f "${iso}" ] || { echo "no such ISO: ${iso}" >&2; exit 1; }
[ -f "${theme_src}/theme.txt" ] || { echo "no GRUB theme at ${theme_src}" >&2; exit 1; }
command -v xorriso >/dev/null || { echo "xorriso not installed (dev-libs/libisoburn)" >&2; exit 3; }

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

# 1. Pull the generated grub.cfg out of the ISO.
xorriso -osirrox on -indev "${iso}" \
    -extract /boot/grub/grub.cfg "${tmp}/grub.cfg" >/dev/null 2>&1

# 2. Switch to a graphical menu + the Helm theme, and shorten the timeout. The
#    theme lines slot in right after catalyst's `insmod all_video`.
sed -i \
    -e 's/^set timeout=.*/set timeout=5/' \
    -e '/^insmod all_video/a\
insmod gfxterm\
terminal_output gfxterm\
loadfont /boot/grub/themes/hede/hede.pf2\
set theme=/boot/grub/themes/hede/theme.txt' \
    "${tmp}/grub.cfg"

# 3. Write the patched grub.cfg + the theme back onto the ISO, keeping it bootable.
xorriso -boot_image any replay -dev "${iso}" \
    -map "${tmp}/grub.cfg" /boot/grub/grub.cfg \
    -map "${theme_src}" /boot/grub/themes/hede >/dev/null 2>&1

echo "grub-theme-inject: themed ${iso} with the Harbor GRUB menu."
