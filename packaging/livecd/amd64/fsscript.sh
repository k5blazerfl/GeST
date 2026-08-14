#!/bin/bash
# catalyst livecd/fsscript — runs inside the livecd-stage2 chroot after packages
# are installed. Turns the image from "a console with gest on PATH" into a real
# installer CD: autologin root on tty1 and launch GeST on login.
set -e

# Autologin root on the primary console (no password on the live medium).
if [ -f /etc/inittab ]; then
    sed -i \
        's|^c1:.*:respawn:.*agetty.*|c1:12345:respawn:/sbin/agetty --autologin root --noclear 38400 tty1 linux|' \
        /etc/inittab
fi

# On tty1, drop straight into the GeST installer; exiting it gives a root shell.
cat > /root/.bash_profile <<'PROFILE'
# GeST installer live image: launch the installer on the primary console.
if [ -z "${GEST_STARTED:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    export GEST_STARTED=1
    clear
    gest --install || true          # exit GeST → a normal root shell
fi
PROFILE

# Services the live environment needs: D-Bus (so GeST's polkit-gated backend can
# bus-activate) and dhcpcd (wired networking for the stage3 download / emerges).
rc-update add dbus default || true
rc-update add dhcpcd default || true
