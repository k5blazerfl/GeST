"""Seamless graphical boot for the installed system — the desktop-side twin of
the live CD's seamless boot. It sets a quiet kernel cmdline, points GRUB at the
HeDE "Harbor" theme, and selects the Plymouth splash, so an installed HeDE boots
the same way the installer image does: GRUB → Plymouth → desktop, one look.

The config transforms here are pure + unit-tested. The bootloader backend reads
``/etc/default/grub``, applies :func:`grub_default`, atomic-writes it, then the
argv steps from :func:`stage_theme_steps` stage the theme + select Plymouth and
``grub-mkconfig`` regenerates — the same core-transform / backend-write split as
fstab (``core/disk``).
"""

from __future__ import annotations

import re

from gest.core.exec.steps import Step

# Quiet-splash args appended to the default kernel cmdline (mirrors the live CD's
# livecd/bootargs).
SEAMLESS_CMDLINE = (
    "quiet splash loglevel=3 rd.udev.log_level=3 "
    "vt.global_cursor_default=0 systemd.show_status=false"
)

# The HeDE GRUB theme ships with gui-apps/hede; the installer stages it into /boot.
THEME_SRC = "/usr/share/hede/grub/hede"
THEME_DST = "/boot/grub/themes/hede"
THEME_TXT = THEME_DST + "/theme.txt"
PLYMOUTH_THEME = "hede"


def grub_settings(*, theme: str = THEME_TXT) -> dict[str, str]:
    """The ``/etc/default/grub`` keys a seamless boot sets."""
    return {
        "GRUB_TIMEOUT": "5",
        "GRUB_CMDLINE_LINUX_DEFAULT": SEAMLESS_CMDLINE,
        "GRUB_TERMINAL_OUTPUT": "gfxterm",
        "GRUB_GFXMODE": "auto",
        "GRUB_THEME": theme,
    }


_KEY_RE = re.compile(r"^\s*#?\s*([A-Z0-9_]+)=")


def apply_grub_default(existing: str, settings: dict[str, str]) -> str:
    """Merge ``settings`` into an ``/etc/default/grub`` body, idempotently.

    An existing (possibly commented-out) ``KEY=...`` line is rewritten in place;
    keys not present are appended under a marked block. Values are double-quoted.
    Re-running with the same settings is a no-op.
    """
    pending = dict(settings)
    out: list[str] = []
    for line in existing.splitlines():
        m = _KEY_RE.match(line)
        key = m.group(1) if m else None
        if key is not None and key in pending:
            out.append(f'{key}="{pending.pop(key)}"')
        else:
            out.append(line)
    if pending:
        if out and out[-1].strip():
            out.append("")
        out.append("# Seamless boot (HeDE) — managed by GeST")
        for key, value in settings.items():
            if key in pending:
                out.append(f'{key}="{value}"')
    return "\n".join(out).rstrip("\n") + "\n"


def grub_default(existing: str) -> str:
    """The seamless ``/etc/default/grub`` for ``existing`` content — the single
    transform the bootloader backend writes (like fstab's upsert)."""
    return apply_grub_default(existing, grub_settings())


def stage_theme_steps(*, root: str = "") -> list[Step]:
    """Argv steps that stage the theme + select Plymouth (run after the
    ``/etc/default/grub`` write, before ``grub-mkconfig``). ``root`` prefixes the
    on-disk paths for an install-root seam."""
    dst = f"{root}{THEME_DST}"
    return [
        Step("prepare the GRUB theme dir", ["mkdir", "-p", dst]),
        Step("stage the HeDE GRUB theme", ["cp", "-rT", f"{root}{THEME_SRC}", dst]),
        Step("select the Plymouth splash", ["plymouth-set-default-theme", PLYMOUTH_THEME]),
    ]
