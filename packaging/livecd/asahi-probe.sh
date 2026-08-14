#!/usr/bin/env bash
# asahi-probe.sh — READ-ONLY ground-truth probe for GeST's Apple Silicon (Asahi)
# install support. Run this on an installed Asahi Gentoo box (e.g. an M2); it
# gathers the real values GeST's arm64 path was scaffolded against, so those
# scaffolds (the update-m1n1 argv, the GRUB target, the Asahi kernel atoms, the
# ESP/boot.bin layout) can be confirmed or corrected.
#
# It ONLY reads: no emerge, no writes, no mounts, nothing destructive. Paste the
# output back into the GeST session and it becomes code corrections.
#
#   bash packaging/livecd/asahi-probe.sh 2>&1 | tee asahi-probe.out
set -u

hr() { printf '\n===== %s =====\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

hr "host / arch / page size"
uname -mrs
echo "PAGE_SIZE=$(getconf PAGE_SIZE 2>/dev/null)"   # Asahi kernels are 16384 (16K)
[ -r /proc/device-tree/compatible ] && { printf 'device-tree: '; tr '\0' ' ' </proc/device-tree/compatible; echo; }

hr "m1n1 boot stub tool (update-m1n1)"
if have update-m1n1; then
    echo "path: $(command -v update-m1n1)"
    echo "--- update-m1n1 --help (or first lines of the script) ---"
    update-m1n1 --help 2>&1 | head -40 || head -40 "$(command -v update-m1n1)"
else
    echo "update-m1n1 NOT on PATH (is sys-apps/asahi-scripts installed?)"
fi
echo "--- /etc/default/m1n1 ---"; cat /etc/default/m1n1 2>/dev/null || echo "(none)"

hr "ESP / boot payload layout"
findmnt -no SOURCE,TARGET,FSTYPE /boot /boot/efi /efi 2>/dev/null
echo "--- boot.bin candidates ---"
ls -l /boot/efi/m1n1/ /efi/m1n1/ 2>/dev/null || echo "(no m1n1/ dir under the usual ESP mounts)"
echo "--- block layout ---"
lsblk -o NAME,SIZE,FSTYPE,PARTTYPENAME,MOUNTPOINT 2>/dev/null

hr "GRUB"
have grub-install && grub-install --version
echo "--- how GRUB is configured here ---"
grep -rHE 'GRUB_PLATFORM|target|arm64-efi' /etc/default/grub 2>/dev/null || echo "(no target hints in /etc/default/grub)"
have efibootmgr && { echo "--- efibootmgr ---"; efibootmgr -v 2>/dev/null | head; }

hr "Asahi packages (kernel / meta / scripts / firmware)"
for atom in \
    sys-apps/asahi-scripts sys-apps/asahi-meta sys-apps/asahi-fwextract \
    "virtual/dist-kernel" "sys-kernel/*asahi*" "sys-firmware/*asahi*"; do
    printf -- '-- %s\n' "$atom"
    if have equery; then equery -q list "$atom" 2>/dev/null
    elif have qlist; then qlist -ICv "$atom" 2>/dev/null
    else echo "(no equery/qlist — is app-portage/gentoolkit / portage-utils installed?)"; fi
done

hr "kernel install style"
echo "--- installed kernels in /boot ---"; ls -1 /boot/ 2>/dev/null | grep -iE 'vmlinu|kernel|dtb|Image' || echo "(none obvious)"
echo "--- dist-kernel? ---"; have eselect && eselect kernel list 2>/dev/null

hr "portage repos / overlay"
have portageq && portageq get_repos / 2>/dev/null
ls /etc/portage/repos.conf/ 2>/dev/null

hr "done"
echo "Paste everything above back into the GeST session."
