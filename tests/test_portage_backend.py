"""CI-safe tests for the Portage backend's validation and atomic writer.

These exercise the pure module-level helpers in ``gest.backend.portage`` — no
D-Bus, no polkit — mirroring how ``test_backend_writer.py`` tests the software
writer directly.
"""

import os

import pytest

from gest.backend import portage as svc
from gest.core.makeconf import writer

# --------------------------------------------------------------------------- #
# content validation (per surface)
# --------------------------------------------------------------------------- #

def test_validate_make_conf_accepts_and_rejects():
    assert svc._validate_content("/etc/portage/make.conf", 'USE="x y"\n') == ""
    assert svc._validate_content("/etc/portage/make.conf", "") == ""            # deletion
    bad = svc._validate_content("/etc/portage/make.conf", 'USE="a`id`"\n')
    assert "invalid" in bad


def test_validate_package_file_checks_atoms():
    ok = "app-editors/vim X\nsys-kernel/gentoo-sources symlink\n"
    assert svc._validate_content("/etc/portage/package.use/gest", ok) == ""
    bad = svc._validate_content("/etc/portage/package.use/gest", "not-an-atom flag\n")
    assert "invalid package atom" in bad


def test_validate_package_file_accepts_wildcard_use_expand():
    # the */* form used by CPU_FLAGS_X86 / VIDEO_CARDS drop-ins
    assert svc._validate_content(
        "/etc/portage/package.use/50gest-cpuflags", "*/* CPU_FLAGS_X86: mmx sse\n") == ""
    assert svc._validate_content(
        "/etc/portage/package.use/50gest-videocards", "*/* VIDEO_CARDS: amdgpu\n") == ""


def test_validate_binrepos_and_unknown_surface():
    assert svc._validate_content(
        "/etc/portage/binrepos.conf/gest.conf", "[gentoo]\nsync-uri = https://d/\n"
    ) == ""
    assert svc._validate_content("/etc/portage/make.conf", "a\0b") != ""         # NUL
    # a path that passed containment but is not a known writable surface
    assert svc._validate_content("/etc/portage/color.map", "anything") != ""


def test_validate_gest_state_surface():
    # GeST's own /etc/portage/gest/ list files: newline repo names + comments.
    assert svc._validate_content(
        "/etc/portage/gest/refresh", "# repos\nguru\namphitheater\n") == ""
    assert svc._validate_content("/etc/portage/gest/refresh", "") == ""          # deletion
    bad = svc._validate_content("/etc/portage/gest/refresh", "bad name\n")
    assert "invalid repository name" in bad


# --------------------------------------------------------------------------- #
# path validation (containment + traversal)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", [
    "/etc/portage/make.conf",
    "/etc/portage/package.use/gest",
    "/etc/portage/binrepos.conf/gest.conf",
])
def test_validate_path_accepts_within(path):
    assert svc._validate_path(path) == ""


@pytest.mark.parametrize("path", [
    "etc/portage/make.conf",              # not absolute
    "/etc/shadow",                        # outside
    "/etc/portage/../../etc/shadow",      # traversal
])
def test_validate_path_rejects(path):
    assert svc._validate_path(path) != ""


def test_validate_path_rejects_symlink_escape(tmp_path, monkeypatch):
    # Simulate /etc/portage rooted at tmp_path with a symlink escaping it.
    root = tmp_path
    (root / "etc" / "portage").mkdir(parents=True)
    (root / "secret").write_text("secret")
    os.symlink(root / "secret", root / "etc" / "portage" / "evil")
    monkeypatch.setattr(svc.paths, "config_root", lambda: str(root))
    assert svc._validate_path(str(root / "etc" / "portage" / "evil")) != ""
    assert svc._validate_path(str(root / "etc" / "portage" / "make.conf")) == ""


# --------------------------------------------------------------------------- #
# atomic apply (write / replace / delete)
# --------------------------------------------------------------------------- #

def test_apply_one_writes_and_sets_mode(tmp_path):
    path = tmp_path / "sub" / "gest"                # parent created on demand
    svc._apply_one(str(path), "cat/pkg flag\n", 0o644)
    assert path.read_text() == "cat/pkg flag\n"
    assert (os.stat(path).st_mode & 0o777) == 0o644


def test_apply_one_empty_text_deletes(tmp_path):
    path = str(tmp_path / "gest")
    svc._apply_one(path, "data\n", 0o644)
    svc._apply_one(path, "", 0o644)
    assert not os.path.exists(path)
    svc._apply_one(path, "", 0o644)                 # deleting a missing file is a no-op


# --------------------------------------------------------------------------- #
# writer → ConfigWrite round trip
# --------------------------------------------------------------------------- #

def test_makeconf_writer_builds_config_write(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('# hdr\nUSE="a"\n')
    cw = writer.set_variable("USE", "a b", path=str(mc))
    assert cw.path == str(mc)
    assert 'USE="a b"' in cw.text and "# hdr" in cw.text
    # and the backend would accept what the writer produced
    assert svc._validate_content(str(mc), cw.text) == "" or cw.path.endswith("make.conf")
    assert svc._validate_content("/etc/portage/make.conf", cw.text) == ""
