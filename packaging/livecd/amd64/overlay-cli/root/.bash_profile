# GeSI CLI installer — root's login profile on the live medium.
#
# On the autologin console (tty1) this launches GeST's guided "Install Gentoo"
# TUI as soon as the boot completes: the whole point of this image is a
# YaST-style, boot-straight-into-the-installer experience. Other ttys (tty2-6),
# and tty1 after the installer exits, drop to a normal root shell so the medium
# stays usable for inspection, networking fixups, or a manual re-run of `gest`.

# Only auto-launch on the primary console, only for an interactive login, and
# only once per session (GESI_LAUNCHED guards against a re-run if the shell is
# re-sourced). Everything else gets a plain shell.
if [ "$(tty)" = "/dev/tty1" ] && [ -z "${GESI_LAUNCHED:-}" ]; then
    export GESI_LAUNCHED=1
    echo
    echo "  Starting the GeSI Gentoo installer…  (exit it for a root shell)"
    echo
    # gest --install opens straight on the "Install Gentoo" flow. If it exits
    # (finished, or the user quit), fall through to the shell below rather than
    # respawning, so the user stays in control of the live environment.
    gest --install || true
    echo
    echo "  The installer exited. You are at a root shell on the live medium."
    echo "  Re-run the installer any time with:  gest --install"
    echo "  Reboot into the freshly installed system with:  reboot"
    echo
fi
