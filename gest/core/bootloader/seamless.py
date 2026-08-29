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
from gest.core.kernel.commands import genkernel_argv

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


# --- hibernate resume ---------------------------------------------------------
# The installer formats swap and writes it into fstab, but without a ``resume=``
# on the kernel cmdline the kernel has no idea where the hibernation image lives,
# so a hibernated system cold-boots and loses the session. resume= belongs on
# GRUB_CMDLINE_LINUX (every entry, incl. recovery — you want to resume from any
# of them), NOT GRUB_CMDLINE_LINUX_DEFAULT (which is quiet-splash-only). This is
# the same GRUB_CMDLINE_LINUX rail the GPU step's cmdline uses, so the two compose.
RESUME_CMDLINE_KEY = "GRUB_CMDLINE_LINUX"


def resume_cmdline(swap_uuid: str) -> str:
    """The ``resume=UUID=<swap>`` kernel arg pointing hibernate at the swap it
    restores from — empty when there is no swap (nothing to resume)."""
    return f"resume=UUID={swap_uuid}" if swap_uuid else ""


def apply_resume_cmdline(existing: str, swap_uuid: str) -> str:
    """Merge ``resume=UUID=<swap_uuid>`` into ``GRUB_CMDLINE_LINUX`` in an
    ``/etc/default/grub`` body, appending (deduped) to any existing value and
    rewriting the line in place; appends the key if absent. Idempotent, and a
    no-op when ``swap_uuid`` is empty — so a swapless install adds nothing and a
    re-run never doubles the arg."""
    args = resume_cmdline(swap_uuid)
    if not args:
        return existing
    want = args.split()
    key_re = re.compile(rf'^\s*#?\s*{RESUME_CMDLINE_KEY}=(?:"(.*)"|(.*))\s*$')
    lines = existing.split("\n")
    for i, line in enumerate(lines):
        m = key_re.match(line)
        if m:
            cur = (m.group(1) if m.group(1) is not None else m.group(2)).split()
            merged = cur + [a for a in want if a not in cur]
            lines[i] = f'{RESUME_CMDLINE_KEY}="{" ".join(merged)}"'
            return "\n".join(lines)
    if lines and lines[-1].strip():
        lines.append("")
    lines.append("# Hibernate resume — managed by GeST")
    lines.append(f'{RESUME_CMDLINE_KEY}="{" ".join(want)}"')
    return "\n".join(lines)


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


# --- biome re-tint (slice 1b) --------------------------------------------------
# Re-tinting overwrites the two boot-theme files a prior ConfigureSeamlessBoot
# already installed, from files helm-theme emits (--emit-boot-theme) for the
# active world's accent. GRUB reads theme.txt straight from /boot, so its re-tint
# lands on the next boot with no rebuild; Plymouth's script is baked into the
# initramfs, so it only takes effect after an initramfs rebuild.
PLYMOUTH_SCRIPT_DST = "/usr/share/plymouth/themes/hede/hede.script"
GRUB_THEME_TXT_DST = THEME_TXT  # /boot/grub/themes/hede/theme.txt
# The per-biome splash scene (slice 2). helm-theme copies the active world's
# boot.png here; overwriting it is what makes the splash *art* track the biome
# (the chrome above tracks the accent). Baked into the initramfs like the script.
PLYMOUTH_BG_DST = "/usr/share/plymouth/themes/hede/background.png"


def boot_theme_installs(*, staging: str, root: str = "") -> list[tuple[str, str]]:
    """``(src, dst)`` pairs to atomic-copy when re-tinting the installed boot
    theme from files emitted into ``staging`` (as ``plymouth/hede/hede.script``
    and ``grub/hede/theme.txt``). ``root`` prefixes the on-disk destinations for
    an install-root seam. The backend atomic-writes each dst (temp + rename)."""
    return [
        (f"{staging}/plymouth/hede/hede.script", f"{root}{PLYMOUTH_SCRIPT_DST}"),
        (f"{staging}/grub/hede/theme.txt", f"{root}{GRUB_THEME_TXT_DST}"),
    ]


def boot_scene_install(*, staging: str, root: str = "") -> tuple[str, str]:
    """The ``(src, dst)`` for the per-biome splash scene. Best-effort: the src is
    present only when the active world ships a boot.png, so the backend installs
    it only if emitted — a world without one keeps the default Harbor scene."""
    return (f"{staging}/plymouth/hede/background.png", f"{root}{PLYMOUTH_BG_DST}")


def initramfs_regen_step() -> Step:
    """Rebuild the initramfs so Plymouth picks up the re-tinted ``hede.script``.
    ``genkernel --plymouth initramfs`` re-bakes only the initramfs (no kernel
    recompile) with the current default HeDE splash — the fast twin of the
    install-time ``genkernel --plymouth all``. genkernel writes the image itself,
    keeping the prior kernel's entry available if a boot regresses."""
    return Step("rebuild the initramfs (Plymouth splash)",
                genkernel_argv(plymouth=True, action="initramfs"))


def seamless_steps(*, root: str = "") -> list[Step]:
    """The direct (in-process root) install path's seamless pipeline: write the
    merged ``/etc/default/grub`` (a ``tee`` step, content on stdin) then stage the
    theme + select Plymouth. Reads the target's existing grub default to merge
    idempotently — empty if absent (a fresh install root), so it stays
    deterministic. Insert before the ``grub-mkconfig`` step; the backend path uses
    ConfigureSeamlessBoot instead."""
    grub_default_path = f"{root}/etc/default/grub"
    existing = ""
    try:
        with open(grub_default_path, encoding="utf-8") as f:
            existing = f.read()
    except OSError:
        pass  # no file on a fresh target → merge into an empty base
    return [
        Step(f"write {grub_default_path}", ["tee", grub_default_path],
             stdin=grub_default(existing)),
        *stage_theme_steps(root=root),
    ]
