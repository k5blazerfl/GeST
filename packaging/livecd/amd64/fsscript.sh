#!/bin/bash
# catalyst livecd/fsscript — runs inside the livecd-stage2 chroot after packages
# are installed. Turns the image into a boot-to-desktop installer: it comes up in
# HeDE (the Helm Desktop Environment), and the user runs GeST — the TUI or its Qt
# Control Center (gest-settings), both present — to install Gentoo.
set -e

# greetd owns vt1 (it autologins into the HeDE session — see the root-overlay
# /etc/greetd/config.toml), so free tty1 from the default getty. tty2-6 stay as
# rescue shells with `gest` on PATH (root has no password on the live medium).
if [ -f /etc/inittab ]; then
    sed -i \
        's|^c1:.*:respawn:.*agetty.*|# c1 disabled — greetd owns vt1 (HeDE autologin)|' \
        /etc/inittab
fi

# Seat/login + session bus so the Wayland compositor, polkit and GeST's
# bus-activated backend all work, plus wired networking for the stage3 download.
# elogind provides the logind seat labwc/wlroots use via libseat (greetd opens a
# PAM session that registers it) — no separate seatd needed.
rc-update add elogind boot   || true   # logind API: seats, brightness, active session
rc-update add dbus default   || true   # system/session bus (GeST backend activation)
rc-update add dhcpcd default || true   # wired networking for stage3 / emerges

# The greeter: autologin straight into the HeDE session at boot. greetd ships
# only a systemd unit upstream, so the image supplies an OpenRC init script (see
# overlay/etc/init.d/greetd); rc-update it into the default runlevel.
rc-update add greetd default
