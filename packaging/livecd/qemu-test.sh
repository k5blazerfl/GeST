#!/usr/bin/env bash
# Boot a built GeST installer ISO in QEMU to smoke-test it before real hardware.
#
#   packaging/livecd/qemu-test.sh /path/to/gest-installer-amd64-<stamp>.iso [bios|uefi]
#
# bios (default) boots the isohybrid ISO via SeaBIOS; uefi boots it via OVMF
# (emerge sys-firmware/edk2-ovmf). A scratch qcow2 target disk is created so you
# can exercise the installer end to end without touching a real disk.
set -euo pipefail

iso="${1:?usage: qemu-test.sh <iso> [bios|uefi]}"
mode="${2:-bios}"
[ -f "${iso}" ] || { echo "no such ISO: ${iso}" >&2; exit 1; }
command -v qemu-system-x86_64 >/dev/null || { echo "emerge app-emulation/qemu" >&2; exit 1; }

disk="$(mktemp -u --suffix=.qcow2)"
qemu-img create -f qcow2 "${disk}" 20G >/dev/null
trap 'rm -f "${disk}"' EXIT

common=(-m 4G -smp 2 -cdrom "${iso}" -drive "file=${disk},format=qcow2,if=virtio"
        -boot d -net nic -net user)

case "${mode}" in
    bios)
        qemu-system-x86_64 "${common[@]}"
        ;;
    uefi)
        ovmf=""
        for c in /usr/share/edk2-ovmf/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE.fd; do
            [ -f "$c" ] && ovmf="$c" && break
        done
        [ -n "${ovmf}" ] || { echo "no OVMF firmware (emerge sys-firmware/edk2-ovmf)" >&2; exit 1; }
        qemu-system-x86_64 -drive "if=pflash,format=raw,readonly=on,file=${ovmf}" "${common[@]}"
        ;;
    *)
        echo "mode must be 'bios' or 'uefi'" >&2; exit 1 ;;
esac
