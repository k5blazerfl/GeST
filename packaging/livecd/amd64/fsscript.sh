#!/bin/bash
# catalyst livecd/fsscript — runs inside the livecd-stage2 chroot after packages
# are installed. Turns the image into a boot-to-desktop installer: it comes up in
# HeDE (the Helm Desktop Environment), and the user runs GeST — the TUI or its Qt
# Control Center (gest-settings), both present — to install Gentoo.
#
# The live image is systemd (matching HeDE's init commitment): seats/login come
# from systemd-logind and greetd runs as its packaged systemd unit. All the
# systemctl calls below are offline symlink operations — safe inside the chroot.
set -e

# greetd owns vt1 (it autologins into the HeDE session — see the root-overlay
# /etc/greetd/config.toml). Mask the tty1 getty so logind's autovt can't race it;
# tty2-6 stay as rescue shells with `gest` on PATH (root has no password on the
# live medium). greetd.service also Conflicts=getty@tty1 upstream, but masking is
# belt-and-suspenders.
systemctl mask getty@tty1.service

# Session bus + wired networking for the stage3 download. systemd-logind (built
# in) provides the logind seat labwc/wlroots use via libseat — greetd opens a PAM
# session that registers it — so no elogind/seatd *service* is needed.
systemctl enable dbus.service    || true   # system bus (GeST backend activation)
systemctl enable dhcpcd.service  || true   # wired networking for stage3 / emerges

# The greeter: autologin straight into the HeDE session at boot. gui-libs/greetd
# ships a systemd unit upstream; enable it and boot into graphical.target.
systemctl enable greetd.service
systemctl set-default graphical.target

# Headless boot-smoke beacon (root overlay: /etc/systemd/system/gest-boot-beacon
# .service). Fires once graphical.target is reached and prints a token to the
# serial port so packaging/livecd/boot-smoke.sh can assert the image boots
# unattended. Serial-only → harmless (silent no-op) on real hardware.
systemctl enable gest-boot-beacon.service || true

# Seamless boot: make the HeDE ship's-helm splash the default for the post-pivot
# systemd phase (genkernel already baked it into the initramfs via gk_mainargs).
# The greetd drop-in (root overlay, greetd.service.d/plymouth.conf) retains the
# splash on the framebuffer until labwc draws the HeDE session over it — navy over
# navy, no flash.
plymouth-set-default-theme hede || true
