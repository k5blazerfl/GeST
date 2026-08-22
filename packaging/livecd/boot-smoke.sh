#!/usr/bin/env bash
# boot-smoke.sh — unattended headless boot gate for a built GeST installer ISO.
#
#   packaging/livecd/boot-smoke.sh <iso> [bios|uefi] [--timeout SECONDS]
#                                        [--marker REGEX] [--keep-log]
#
# Boots the ISO in QEMU with NO display, captures the serial console, and passes
# only if the image reaches a completed graphical boot within the timeout — i.e.
# the gest-boot-beacon.service prints its token to the serial port once
# greetd/graphical.target is up (see amd64/overlay + fsscript.sh). This is the
# automated form of the manual "boot it in QEMU and eyeball the greeter" check,
# so it can run in CI / nightly on the build host.
#
# Exit 0 = booted to the greeter; 1 = timed out / QEMU died before signalling;
# 2 = bad usage / missing tools.  Interactive testing still lives in qemu-test.sh.
set -euo pipefail

iso=""
mode="bios"
timeout=300
marker="GEST_BOOT_OK"
keep_log=0

while [ $# -gt 0 ]; do
    case "$1" in
        bios|uefi)   mode="$1"; shift ;;
        --timeout)   timeout="$2"; shift 2 ;;
        --marker)    marker="$2"; shift 2 ;;
        --keep-log)  keep_log=1; shift ;;
        -h|--help)   grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)          echo "unknown option: $1" >&2; exit 2 ;;
        *)           iso="$1"; shift ;;
    esac
done

[ -n "${iso}" ] || { echo "usage: boot-smoke.sh <iso> [bios|uefi] [--timeout N]" >&2; exit 2; }
[ -f "${iso}" ] || { echo "no such ISO: ${iso}" >&2; exit 2; }
command -v qemu-system-x86_64 >/dev/null || { echo "emerge app-emulation/qemu" >&2; exit 2; }

disk="$(mktemp -u --suffix=.qcow2)"
serial="$(mktemp --suffix=.serial.log)"
qemu_pid=""
cleanup() {
    [ -n "${qemu_pid}" ] && kill "${qemu_pid}" 2>/dev/null || true
    rm -f "${disk}"
    [ "${keep_log}" = 1 ] || rm -f "${serial}"
}
trap cleanup EXIT

qemu-img create -f qcow2 "${disk}" 20G >/dev/null

# accel fallback is a colon list on -machine (kvm, else tcg); `-accel kvm:tcg`
# is invalid syntax and makes QEMU exit immediately on hosts that parse it strictly.
args=(-m 4G -smp 2 -machine accel=kvm:tcg -no-reboot -display none
      -serial "file:${serial}" -cdrom "${iso}"
      -drive "file=${disk},format=qcow2,if=virtio" -boot d -net nic -net user)
if [ "${mode}" = "uefi" ]; then
    ovmf=""
    for c in /usr/share/edk2-ovmf/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE.fd \
             /usr/share/edk2/OvmfX64/OVMF_CODE.fd /usr/share/edk2/ovmf/OVMF_CODE.fd; do
        [ -f "$c" ] && ovmf="$c" && break
    done
    [ -n "${ovmf}" ] || { echo "no OVMF firmware (emerge sys-firmware/edk2-ovmf)" >&2; exit 2; }
    args=(-drive "if=pflash,format=raw,readonly=on,file=${ovmf}" "${args[@]}")
fi

echo "== boot-smoke: ${iso##*/} (${mode}), waiting up to ${timeout}s for /${marker}/"
qemu-system-x86_64 "${args[@]}" & qemu_pid=$!

waited=0
while [ "${waited}" -lt "${timeout}" ]; do
    if grep -qE "${marker}" "${serial}" 2>/dev/null; then
        echo "== boot-smoke: PASS — image reached the greeter in ${waited}s"
        exit 0
    fi
    if ! kill -0 "${qemu_pid}" 2>/dev/null; then
        echo "== boot-smoke: FAIL — QEMU exited before signalling (after ${waited}s)" >&2
        break
    fi
    sleep 3
    waited=$((waited + 3))
done

[ "${waited}" -lt "${timeout}" ] || echo "== boot-smoke: FAIL — timed out after ${timeout}s" >&2
echo "---- last 25 lines of serial console ----" >&2
tail -n 25 "${serial}" >&2 || true
exit 1
