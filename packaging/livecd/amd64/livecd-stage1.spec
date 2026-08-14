# catalyst livecd-stage1 for the GeST amd64 installer image.
#
# Stage 1 of two: builds app-admin/gest and the install-path tools into a build
# root seeded from a stage3. Stage 2 (livecd-stage2.spec) then adds the kernel and
# bootloader and packs the ISO.
#
# Fill the @PLACEHOLDER@s for your build host:
#   @SNAPSHOT@   a portage snapshot id, e.g. 2026-08-13 (catalyst snapshot)
#   @STAGE3@     the stage3 seed subpath under builds/, e.g.
#                stage3-amd64-openrc-20260810T170331Z
#   @TIMESTAMP@  a stamp for this build, e.g. 20260813 (must match stage2's
#                source_subpath)
#   @GEST_OVERLAY@  path to the GeST overlay on the build host (clone this repo's
#                   packaging/overlay/ there, or point at /var/db/repos/gest)

subarch: amd64
version_stamp: gest-@TIMESTAMP@
target: livecd-stage1
rel_type: default
profile: default/linux/amd64/23.0
snapshot: @SNAPSHOT@
source_subpath: default/@STAGE3@

# Make app-admin/gest resolvable during the build.
portage_overlay: @GEST_OVERLAY@

# ~amd64 keyword the GeST ebuild is published under.
portage_confdir: @THIS_DIR@/../portage-conf

# The image's package set — keep in sync with amd64/gest.packages.
livecd/packages:
	app-admin/gest
	sys-fs/gptfdisk
	sys-block/parted
	sys-apps/util-linux
	sys-fs/e2fsprogs
	sys-fs/xfsprogs
	sys-fs/btrfs-progs
	sys-fs/f2fs-tools
	sys-fs/dosfstools
	net-misc/wget
	app-arch/tar
	app-arch/xz-utils
	app-crypt/gnupg
	sys-kernel/genkernel
	sys-boot/grub
	sys-boot/efibootmgr
	net-misc/dhcpcd
	net-wireless/wpa_supplicant
	net-wireless/iw
	net-firewall/nftables
	net-firewall/firewalld
	sys-auth/polkit
	sys-apps/dbus
	gui-apps/hede
	sys-auth/elogind
	sys-auth/seatd
	gui-libs/greetd
