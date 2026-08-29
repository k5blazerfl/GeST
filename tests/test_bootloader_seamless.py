"""Tests for the installed-system seamless-boot config
(gest.core.bootloader.seamless): the pure /etc/default/grub transform + the
theme-staging steps."""

from gest.core.bootloader import seamless


def test_grub_settings_has_quiet_splash_and_theme():
    s = seamless.grub_settings()
    assert "quiet" in s["GRUB_CMDLINE_LINUX_DEFAULT"]
    assert "splash" in s["GRUB_CMDLINE_LINUX_DEFAULT"]
    assert s["GRUB_TERMINAL_OUTPUT"] == "gfxterm"
    assert s["GRUB_THEME"] == seamless.THEME_TXT


def test_apply_appends_to_empty():
    out = seamless.apply_grub_default("", {"GRUB_TIMEOUT": "5"})
    assert 'GRUB_TIMEOUT="5"' in out
    assert out.endswith("\n")


def test_apply_replaces_existing_in_place():
    existing = 'GRUB_TIMEOUT="30"\nGRUB_DISTRIBUTOR="Gentoo"\n'
    out = seamless.apply_grub_default(existing, {"GRUB_TIMEOUT": "5"})
    assert 'GRUB_TIMEOUT="5"' in out
    assert 'GRUB_TIMEOUT="30"' not in out
    assert 'GRUB_DISTRIBUTOR="Gentoo"' in out  # untouched
    assert out.count("GRUB_TIMEOUT") == 1       # replaced in place, not duplicated


def test_apply_replaces_commented_key():
    out = seamless.apply_grub_default("#GRUB_THEME=\n", {"GRUB_THEME": "/x/theme.txt"})
    assert 'GRUB_THEME="/x/theme.txt"' in out
    assert out.count("GRUB_THEME") == 1


def test_apply_is_idempotent():
    settings = seamless.grub_settings()
    once = seamless.apply_grub_default('GRUB_DISTRIBUTOR="Gentoo"\n', settings)
    twice = seamless.apply_grub_default(once, settings)
    assert once == twice


def test_grub_default_uses_settings():
    out = seamless.grub_default("")
    assert seamless.SEAMLESS_CMDLINE in out
    assert seamless.THEME_TXT in out


def test_stage_theme_steps_argv():
    steps = seamless.stage_theme_steps()
    cp = next(s for s in steps if s.argv[0] == "cp")
    assert seamless.THEME_SRC in cp.argv and seamless.THEME_DST in cp.argv
    ply = next(s for s in steps if s.argv[0] == "plymouth-set-default-theme")
    assert ply.argv[1] == "hede"


def test_stage_theme_steps_root_prefix():
    steps = seamless.stage_theme_steps(root="/mnt/gentoo")
    cp = next(s for s in steps if s.argv[0] == "cp")
    assert "/mnt/gentoo/boot/grub/themes/hede" in cp.argv


def test_boot_theme_installs_pairs():
    pairs = seamless.boot_theme_installs(staging="/run/x")
    srcs = [s for s, _ in pairs]
    dsts = [d for _, d in pairs]
    assert "/run/x/plymouth/hede/hede.script" in srcs
    assert "/run/x/grub/hede/theme.txt" in srcs
    # Plymouth's script goes into its theme dir (baked into the initramfs);
    # GRUB's theme.txt overwrites the copy in /boot (read directly at boot).
    assert seamless.PLYMOUTH_SCRIPT_DST in dsts
    assert seamless.GRUB_THEME_TXT_DST in dsts
    assert seamless.GRUB_THEME_TXT_DST == seamless.THEME_TXT


def test_boot_theme_installs_root_prefix():
    pairs = seamless.boot_theme_installs(staging="/run/x", root="/mnt/gentoo")
    dsts = [d for _, d in pairs]
    assert f"/mnt/gentoo{seamless.PLYMOUTH_SCRIPT_DST}" in dsts
    assert "/mnt/gentoo/boot/grub/themes/hede/theme.txt" in dsts


def test_boot_scene_install_pair():
    src, dst = seamless.boot_scene_install(staging="/run/x")
    assert src == "/run/x/plymouth/hede/background.png"
    assert dst == seamless.PLYMOUTH_BG_DST
    assert dst.endswith("/plymouth/themes/hede/background.png")
    # root prefix seam
    _, dst2 = seamless.boot_scene_install(staging="/run/x", root="/mnt/gentoo")
    assert dst2 == f"/mnt/gentoo{seamless.PLYMOUTH_BG_DST}"


def test_initramfs_regen_step_is_genkernel_initramfs_plymouth():
    step = seamless.initramfs_regen_step()
    assert step.argv[0] == "genkernel"
    assert "--plymouth" in step.argv
    assert step.argv[-1] == "initramfs"  # initramfs-only, no kernel recompile


# --- hibernate resume cmdline -------------------------------------------------

def test_resume_cmdline_builds_uuid_arg():
    assert seamless.resume_cmdline("abc-123") == "resume=UUID=abc-123"
    assert seamless.resume_cmdline("") == ""       # no swap -> nothing to resume


def test_apply_resume_cmdline_appends_key_when_absent():
    out = seamless.apply_resume_cmdline('GRUB_TIMEOUT="5"\n', "abc-123")
    assert 'GRUB_CMDLINE_LINUX="resume=UUID=abc-123"' in out
    assert 'GRUB_TIMEOUT="5"' in out               # untouched


def test_apply_resume_cmdline_merges_into_existing_line():
    # composes with the GPU step's GRUB_CMDLINE_LINUX (same rail), deduped
    existing = 'GRUB_CMDLINE_LINUX="nouveau.modeset=0 nvidia_drm.modeset=1"\n'
    out = seamless.apply_resume_cmdline(existing, "abc-123")
    assert out.count("GRUB_CMDLINE_LINUX=") == 1   # merged in place, not duplicated
    assert "nouveau.modeset=0" in out              # existing args preserved
    assert "resume=UUID=abc-123" in out


def test_apply_resume_cmdline_is_idempotent():
    once = seamless.apply_resume_cmdline("", "abc-123")
    twice = seamless.apply_resume_cmdline(once, "abc-123")
    assert once == twice
    assert twice.count("resume=UUID=abc-123") == 1


def test_apply_resume_cmdline_noop_without_swap():
    existing = 'GRUB_TIMEOUT="5"\n'
    assert seamless.apply_resume_cmdline(existing, "") == existing
