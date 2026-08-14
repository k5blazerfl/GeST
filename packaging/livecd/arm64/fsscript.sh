#!/bin/bash
# catalyst livecd/fsscript for the arm64 (Apple Silicon / Asahi) image — runs in
# the livecd-stage2 chroot. Same installer autolaunch as amd64; the Asahi boot
# object is a machine-install concern (update-m1n1 runs on the *installed* target,
# not the live medium), so this only sets up the live environment.
set -e

# Autologin root on the primary console.
if [ -f /etc/inittab ]; then
    sed -i \
        's|^c1:.*:respawn:.*agetty.*|c1:12345:respawn:/sbin/agetty --autologin root --noclear 38400 tty1 linux|' \
        /etc/inittab
fi

# On tty1, drop straight into the GeST installer; exiting it gives a root shell.
cat > /root/.bash_profile <<'PROFILE'
# GeST installer live image (Apple Silicon): launch the installer on the console.
if [ -z "${GEST_STARTED:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    export GEST_STARTED=1
    clear
    gest --install || true
fi
PROFILE

# Services the live env needs.
rc-update add dbus default || true
rc-update add dhcpcd default || true

# NOTE: on Apple Silicon the *installed* system's boot object (m1n1 + U-Boot +
# devicetree, packed onto the ESP) is produced by `update-m1n1` from
# sys-apps/asahi-scripts, run in the target after the Asahi kernel is installed —
# GeST's bootloader step is x86-oriented today and does not do this. See the
# README "installer gap on Apple Silicon".
