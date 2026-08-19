"""GeST root D-Bus interface for the bootloader & kernel module.

Registered at /org/gentoo/gest/Bootloader. Regenerates the bootloader config
(`grub-mkconfig -o …`, gated by org.gentoo.gest.bootloader.manage) and installs
GRUB (`grub-install`, UEFI or BIOS, gated by the more-impactful
org.gentoo.gest.bootloader.install). Every action is audit-logged; the install
argv is re-validated server-side via the shared command builder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.bootloader import commands
from gest.ipc.interface import (
    BOOTLOADER_IFACE,
    BOOTLOADER_INSTALL_POLKIT,
    BOOTLOADER_PATH,
    BOOTLOADER_POLKIT,
)

_INTROSPECTION = f"""
<node>
  <interface name="{BOOTLOADER_IFACE}">
    <method name="RegenerateGrub">
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="InstallGrub">
      <arg type="s" name="firmware" direction="in"/>
      <arg type="s" name="efi_directory" direction="in"/>
      <arg type="s" name="bootloader_id" direction="in"/>
      <arg type="b" name="removable" direction="in"/>
      <arg type="s" name="disk" direction="in"/>
      <arg type="s" name="boot_directory" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="ConfigureSeamlessBoot">
      <arg type="s" name="root" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SyncBootTheme">
      <arg type="s" name="accent" direction="in"/>
      <arg type="s" name="world" direction="in"/>
      <arg type="s" name="root" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_GRUB_MKCONFIG = shutil.which("grub-mkconfig") or "/usr/sbin/grub-mkconfig"
_GRUB_INSTALL = shutil.which("grub-install") or "/usr/sbin/grub-install"
_HELM_THEME = shutil.which("helm-theme") or "/usr/bin/helm-theme"

# Accent crossing the trust boundary must be exactly "#RRGGBB": it becomes an
# argv element to helm-theme, which bakes the boot theme (a Plymouth *script* run
# as root in the initramfs). We regenerate from this single validated primitive
# rather than accept caller-supplied theme text.
_ACCENT_RE = re.compile(r"\A#[0-9a-fA-F]{6}\Z")
# The world id (scene selector) is likewise a validated slug — helm-theme copies
# the *packaged* /usr/share/hede/worlds/<id>/boot.png (root-trusted), so the id,
# not caller-supplied image bytes, is what crosses the boundary. Empty = chrome
# only (keep the current scene).
_WORLD_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

_POLKIT = {
    "RegenerateGrub": BOOTLOADER_POLKIT,
    "InstallGrub": BOOTLOADER_INSTALL_POLKIT,
    "ConfigureSeamlessBoot": BOOTLOADER_POLKIT,  # edits grub config, like RegenerateGrub
    "SyncBootTheme": BOOTLOADER_POLKIT,  # re-tints the installed boot theme + initramfs
}
_METHODS = tuple(_POLKIT)


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def _atomic_write(path: str, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + rename), creating the
    parent dir. Mirrors the pattern in backend/disk.py and backend/firewall.py."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _atomic_copy(src: str, dst: str) -> None:
    """Copy the (binary) file ``src`` to ``dst`` atomically (temp + rename),
    creating the parent dir. Used for the per-biome splash scene image."""
    directory = os.path.dirname(dst) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
            shutil.copyfileobj(f, out)
        os.replace(tmp, dst)
    except BaseException:
        os.unlink(tmp)
        raise


def _configure_seamless(root: str) -> tuple[bool, str]:
    """Apply the seamless-boot config under ``root`` ("" = the live host, or a
    target root like /mnt/gentoo): rewrite ``/etc/default/grub`` via the pure
    transform, then stage the GRUB theme + select the Plymouth splash. The caller
    regenerates grub.cfg (RegenerateGrub) afterward."""
    from gest.core.bootloader import seamless

    grub_default = f"{root}/etc/default/grub"
    try:
        existing = ""
        if os.path.exists(grub_default):
            with open(grub_default, encoding="utf-8") as f:
                existing = f.read()
        _atomic_write(grub_default, seamless.grub_default(existing))
    except OSError as exc:
        return False, f"/etc/default/grub: {exc}"

    lines = [f"wrote {grub_default}"]
    for step in seamless.stage_theme_steps(root=root):
        ok, out = _run(step.argv)
        lines.append(f"{step.label}: {'ok' if ok else out}")
        if not ok:
            return False, "\n".join(lines)
    return True, "\n".join(lines)


def _sync_boot_theme(accent: str, world: str, root: str) -> tuple[bool, str]:
    """Re-tint the installed boot theme to ``accent`` (a validated ``#RRGGBB``)
    and, when ``world`` (a validated slug) is given, swap the splash scene to that
    biome's boot.png so the splash *art* tracks it too — the desktop background is
    untouched.

    helm-theme regenerates the tinted Plymouth script + GRUB theme.txt and copies
    the world's packaged boot.png into a root-owned temp dir (``--emit-boot-theme``,
    no session side-effects); we atomic-write/copy each into place, then rebuild
    the initramfs so Plymouth picks up the new script + scene. GRUB reads its
    theme.txt from /boot, so it needs no rebuild. Requires a prior
    ConfigureSeamlessBoot (this overwrites files it installed). On a target root
    (``root`` set) the initramfs rebuild is left to the target's own kernel build
    — we only place the files."""
    from gest.core.bootloader import seamless

    if not _ACCENT_RE.match(accent):
        raise ValueError(f"invalid accent (expected #RRGGBB): {accent!r}")
    if world and not _WORLD_RE.match(world):
        raise ValueError(f"invalid world id: {world!r}")

    lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gest-boot-theme-") as staging:
        argv = [_HELM_THEME, f"--emit-boot-theme={staging}", f"--accent={accent}"]
        if world:
            argv.append(f"--world={world}")
        ok, out = _run(argv)
        lines.append(f"emit boot theme ({accent}, world={world or '-'}): {'ok' if ok else out}")
        if not ok:
            return False, "\n".join(lines)

        # Chrome (Plymouth script + GRUB theme.txt): required, atomic text write.
        for src, dst in seamless.boot_theme_installs(staging=staging, root=root):
            try:
                with open(src, encoding="utf-8") as f:
                    text = f.read()
                _atomic_write(dst, text)
            except OSError as exc:
                lines.append(f"install {dst}: {exc}")
                return False, "\n".join(lines)
            lines.append(f"install {dst}: ok")

        # Scene image: best-effort — present only when the world ships a boot.png.
        scene_src, scene_dst = seamless.boot_scene_install(staging=staging, root=root)
        if os.path.exists(scene_src):
            try:
                _atomic_copy(scene_src, scene_dst)
            except OSError as exc:
                lines.append(f"install {scene_dst}: {exc}")
                return False, "\n".join(lines)
            lines.append(f"install {scene_dst}: ok")
        else:
            lines.append("scene: none for this world; keeping the current splash")

    if root:
        lines.append("initramfs rebuild: deferred to the target's kernel build")
        return True, "\n".join(lines)

    step = seamless.initramfs_regen_step()
    ok, out = _run(step.argv)
    lines.append(f"{step.label}: {'ok' if ok else out}")
    return ok, "\n".join(lines)


class BootloaderService:
    """Implements the ``org.gentoo.gest.Bootloader`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            BOOTLOADER_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in _METHODS:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, _POLKIT[method]):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized for this bootloader operation")
            return
        try:
            if method == "RegenerateGrub":
                ok, out = _run(commands.grub_mkconfig_argv(grub_mkconfig=_GRUB_MKCONFIG))
                detail = "regenerate grub.cfg"
            elif method == "ConfigureSeamlessBoot":
                (root,) = params.unpack()
                ok, out = _configure_seamless(root)
                detail = "configure seamless boot"
            elif method == "SyncBootTheme":
                accent, world, root = params.unpack()
                ok, out = _sync_boot_theme(accent, world, root)
                detail = f"sync boot theme {accent} world={world or '-'}"
            else:  # InstallGrub
                firmware, efi_dir, boot_id, removable, disk, boot_dir = params.unpack()
                argv = commands.grub_install_argv(
                    firmware, efi_directory=efi_dir, bootloader_id=boot_id,
                    removable=bool(removable), disk=disk, boot_directory=boot_dir,
                    grub_install=_GRUB_INSTALL)
                ok, out = _run(argv)
                detail = f"grub-install {firmware}"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
