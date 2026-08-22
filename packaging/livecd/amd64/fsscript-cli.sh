#!/bin/bash
# catalyst livecd/fsscript for the BAREBONES GeSI CLI installer image — runs
# inside the livecd-stage2 chroot after packages are installed. Turns the image
# into a boot-to-installer console: it autologins root on tty1, and root's shell
# profile launches GeST's guided "Install Gentoo" TUI (a YaST-style CLI install).
#
# The live image is systemd (matching GeST/HeDE's init commitment), but there is
# NO desktop here — no greetd, no display server, no graphical.target. The system
# boots to multi-user.target and the console is the whole UI. All the systemctl
# calls below are offline symlink operations — safe inside the chroot.
set -e

# Session bus + wired networking for the stage3 download. The installer shells out
# over D-Bus (the GeST backend) and needs a network to fetch a stage3 and emerge.
systemctl enable dbus.service    || true   # system bus (GeST backend activation)
systemctl enable dhcpcd.service  || true   # wired networking for stage3 / emerges

# Boot to the console, not graphical — this image has no display server.
systemctl set-default multi-user.target

# tty1 autologins root (drop-in shipped in the CLI root overlay:
# /etc/systemd/system/getty@tty1.service.d/autologin.conf). tty2-6 stay as plain
# getty login shells with `gest` on PATH (root has no password on the live medium)
# so a second console is available if the installer is exited. Make sure getty@tty1
# is wanted by multi-user.target (it is, via getty.target — this is belt-and-suspenders).
systemctl enable getty@tty1.service || true

# Headless boot-smoke beacon (CLI root overlay: /etc/systemd/system/
# gesi-boot-beacon.service). Fires once multi-user.target is reached and prints a
# token to the serial port so packaging/livecd/boot-smoke.sh can assert the image
# boots unattended. Serial-only → harmless (silent no-op) on real hardware.
systemctl enable gesi-boot-beacon.service || true

# --- firmware trim (barebones console installer) ---------------------------
# linux-firmware is ~1.9 GB and by far the largest thing on the image, but the
# live CONSOLE only needs firmware for networking (to fetch the stage3): a text
# console renders on the EFI framebuffer (efifb/simpledrm) with no GPU firmware,
# and the INSTALLED target gets full linux-firmware during the install anyway
# (InstallGpuDrivers always emerges it). So drop what the live console can't use:
#   * GPU firmware — i915 (Intel), amdgpu/radeon (AMD), nvidia. (NOT sys-fs/amd,
#     which is CPU microcode — left in place.)
#   * qcom — Qualcomm ARM-SoC (Snapdragon/Adreno) blobs, irrelevant on amd64.
# ALL Wi-Fi/Ethernet firmware (iwlwifi, ath*, rtw*, rtl*, brcm, mediatek/mt76, …)
# is kept, so install-time networking is unaffected. Saves ~800 MB uncompressed.
# The package DB still lists these files, which is fine for an immutable live image.
for _fw in i915 amdgpu radeon nvidia qcom; do
    rm -rf "/lib/firmware/${_fw}"
done
