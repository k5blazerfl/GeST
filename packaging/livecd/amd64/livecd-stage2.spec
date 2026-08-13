# catalyst livecd-stage2 for the GeST amd64 installer image.
#
# Stage 2 of two: takes livecd-stage1's build root, adds a kernel + bootloader,
# and packs a hybrid ISO (BIOS + UEFI) that boots into a root console.
#
# @TIMESTAMP@ MUST match the stage1 version_stamp so source_subpath resolves.
# gentoo-kernel-bin keeps the build fast (a prebuilt kernel); swap to
# sys-kernel/gentoo-sources + genkernel if you want a from-source kernel.

subarch: amd64
version_stamp: gest-@TIMESTAMP@
target: livecd-stage2
rel_type: default
profile: default/linux/amd64/23.0
snapshot: @SNAPSHOT@
source_subpath: default/livecd-stage1-amd64-gest-@TIMESTAMP@

# kernel
boot/kernel: gentoo
boot/kernel/gentoo/sources: sys-kernel/gentoo-kernel-bin

# image: a squashfs root packed into a hybrid, UEFI-capable ISO
livecd/type: generic-livecd
livecd/fstype: squashfs
livecd/iso: gest-installer-amd64-@TIMESTAMP@.iso
livecd/volid: GEST_INSTALLER

# what the user sees at the console; the installer is the gated "Install Gentoo"
# menu category, shown because the live env runs as root.
livecd/motd: @THIS_DIR@/motd

# To auto-launch GeST on tty1 instead of a bare login, drop a start script into
# the image's /etc/local.d/ (via a bind/overlay) that runs `gest` for root — an
# iteration once the plain "boots to a console with gest on PATH" image works.
