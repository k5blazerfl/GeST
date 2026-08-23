"""CI-safe tests for the desktop-provisioning command/config builders (pure)."""

from gest.core.install import desktop


def test_desktop_atoms_are_hede_plymouth_and_greetd():
    assert desktop.DESKTOP_ATOMS == ("gui-apps/hede", "sys-boot/plymouth", "gui-libs/greetd")


def test_greetd_autologin_config_targets_the_user_and_helm_session():
    cfg = desktop.greetd_autologin_config("alice")
    assert "[initial_session]" in cfg and "[default_session]" in cfg
    assert 'user = "alice"' in cfg
    assert "dbus-run-session helm-session" in cfg
    assert cfg == desktop.greetd_autologin_config("alice")   # deterministic


def test_quickpkg_writes_into_the_given_pkgdir():
    # @installed covers the full closure so --usepkgonly never compiles; PKGDIR env
    # points quickpkg at the target's pkgdir.
    assert desktop.quickpkg_argv(pkgdir="/mnt/gentoo/var/cache/binpkgs") == [
        "env", "PKGDIR=/mnt/gentoo/var/cache/binpkgs", "quickpkg",
        "--include-config=y", "@installed"]


def test_seed_overlay_copies_amphitheater_under_root():
    assert desktop.seed_overlay_argv(root="/mnt/gentoo") == [
        "cp", "-a", "/var/db/repos/amphitheater", "/mnt/gentoo/var/db/repos/amphitheater"]
    assert desktop.seed_overlay_argv() == [
        "cp", "-a", "/var/db/repos/amphitheater", "/var/db/repos/amphitheater"]


def test_overlay_parent_is_created_under_root():
    assert desktop.overlay_parent_argv(root="/mnt/gentoo") == [
        "mkdir", "-p", "/mnt/gentoo/var/db/repos"]


def test_emerge_desktop_is_binary_only():
    # --usepkgonly: install from the quickpkg'd binpkgs, no ebuild tree / network / compile
    assert desktop.emerge_desktop_argv() == [
        "emerge", "--usepkgonly", "--color", "n",
        "gui-apps/hede", "sys-boot/plymouth", "gui-libs/greetd"]


def test_emerge_desktop_network_mode_uses_getbinpkg():
    # CLI ISO path: no local binpkgs → --getbinpkg (binhost, source fallback)
    assert desktop.emerge_desktop_argv(binary_only=False) == [
        "emerge", "--getbinpkg", "--color", "n",
        "gui-apps/hede", "sys-boot/plymouth", "gui-libs/greetd"]


def test_sync_overlay_argv_force_syncs_amphitheater():
    assert desktop.sync_overlay_argv() == ["emaint", "sync", "-r", "amphitheater"]


def test_has_desktop_binpkg_detects_hede_in_pkgdir(tmp_path):
    assert desktop.has_desktop_binpkg(str(tmp_path)) is False       # empty target
    pkg = tmp_path / "var/cache/binpkgs/gui-apps"
    pkg.mkdir(parents=True)
    (pkg / "hede-0.7.0-1.gpkg.tar").write_text("x")
    assert desktop.has_desktop_binpkg(str(tmp_path)) is True


def test_cleanup_removes_target_pkgdir():
    assert desktop.cleanup_pkgdir_argv(root="/mnt/gentoo") == [
        "rm", "-rf", "/mnt/gentoo/var/cache/binpkgs"]


def test_accept_keywords_covers_the_curated_desktop_closure():
    kw = desktop.accept_keywords("amd64")
    # the HeDE desktop stack is ~arch; --usepkgonly masks it otherwise
    for atom in ("app-admin/gest", "gui-apps/hede", "gui-libs/greetd",
                 "dev-libs/wayland", "gui-wm/labwc", "media-libs/vulkan-loader"):
        assert f"{atom} ~amd64" in kw
    # arch-parameterized, and NOT a blanket */* (that slot-conflicts perl)
    assert "*/*" not in kw
    assert desktop.accept_keywords("arm64").count(" ~arm64") == kw.count(" ~amd64")


def test_regen_binhost_argv_rebuilds_the_index():
    assert desktop.regen_binhost_argv() == ["emaint", "binhost", "--fix"]


def test_binpkg_fixup_pairs_maps_shipped_dirs_to_target(tmp_path):
    # the ISO ships real binpkgs for image-mutating packages under BINPKG_FIXUP_DIR;
    # each <cat>/<pn> maps to the copy that must be replaced in the target PKGDIR.
    fixup = tmp_path / "gest-binpkgs"
    (fixup / "x11-misc" / "xkeyboard-config").mkdir(parents=True)
    (fixup / "x11-misc" / "xkeyboard-config" / "xkeyboard-config-2.48-2.gpkg.tar").write_text("x")
    (fixup / "x11-misc" / "loose.txt").write_text("ignored")  # non-dir → skipped
    pairs = desktop.binpkg_fixup_pairs(
        fixup_dir=str(fixup), target_pkgdir="/mnt/gentoo/var/cache/binpkgs")
    assert pairs == [(f"{fixup}/x11-misc/xkeyboard-config",
                      "/mnt/gentoo/var/cache/binpkgs/x11-misc/xkeyboard-config")]


def test_binpkg_fixup_pairs_empty_without_the_dir(tmp_path):
    # base-Gentoo install / older ISO with no fixups → no-op, not an error.
    assert desktop.binpkg_fixup_pairs(
        fixup_dir=str(tmp_path / "nope"),
        target_pkgdir="/mnt/gentoo/var/cache/binpkgs") == []


def test_repos_conf_is_a_git_backed_amphitheater_entry():
    conf = desktop.repos_conf()
    assert "[amphitheater]" in conf
    assert "location = /var/db/repos/amphitheater" in conf
    assert "sync-type = git" in conf
    assert "sync-uri = https://github.com/k5blazerfl/Amphitheater" in conf
    assert "auto-sync = no" in conf          # installed system syncs on the user's terms
