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
