"""Phase 1 of the GeSI wizard redesign: role proposals + capability/license/admin
wiring into the frozen plan. Pure — no I/O, no TUI."""

from __future__ import annotations

import pytest

from gest.core.install import assemble, capabilities
from gest.core.install.assemble import (
    InstallSelections,
    UserDraft,
    assemble_plan,
    propose,
)
from gest.core.install.plan import LICENSE_POLICIES
from gest.core.stage3.model import Stage3Selection


def _stage3() -> Stage3Selection:
    return Stage3Selection(url="u", filename="f", size=1, digests_url="d", signature_url="s")


# --- propose(role) -----------------------------------------------------------

def test_propose_rejects_unknown_role():
    with pytest.raises(ValueError):
        propose("gaming")


def test_propose_desktop_is_the_familiar_shape():
    sel = propose("desktop")
    assert sel.role == "desktop"
    assert sel.install_desktop is True
    assert sel.license == "full"
    assert sel.admin_model == "rootless" and sel.escalator == "sudo"
    assert sel.binary_pref is True
    assert sel.gpu_auto is True
    assert "bluetooth" in sel.capabilities and "wayland" in sel.capabilities


def test_propose_server_is_headless_traditional():
    sel = propose("server")
    assert sel.install_desktop is False
    assert sel.license == "redistributable"
    assert sel.admin_model == "traditional"
    assert sel.tier2 == {"sshd", "firewall"}
    assert sel.capabilities == set()
    assert sel.gpu_auto is False


def test_propose_minimal_builds_from_source():
    sel = propose("minimal")
    assert sel.install_desktop is False
    assert sel.binary_pref is False        # compile from source
    assert sel.admin_model == "traditional"
    assert sel.capabilities == set()


def test_propose_custom_is_editable_baseline():
    sel = propose("custom")
    assert sel.role == "custom"
    # custom keeps the desktop-shaped baseline, all fields editable downstream
    assert sel.install_desktop is True


# --- capabilities.resolve_global_use ----------------------------------------

def test_capabilities_enabled_and_negated():
    use = capabilities.resolve_global_use({"bluetooth"})
    assert "bluetooth" in use
    # an unchecked capability negates its tokens explicitly
    assert "-cups" in use            # printing off → -cups
    assert "pipewire" not in use     # audio off → its positive token absent
    assert "-pipewire" in use


def test_capabilities_declared_negative_token_flips():
    # audio ships ("pipewire", "-pulseaudio"); enabled → pulseaudio negated stays -,
    # disabled → -pulseaudio flips to pulseaudio (explicit "keep pulseaudio").
    on = capabilities.resolve_global_use({"audio"})
    assert "pipewire" in on and "-pulseaudio" in on
    off = capabilities.resolve_global_use(set())
    assert "-pipewire" in off and "pulseaudio" in off


def test_capabilities_unknown_key_raises():
    with pytest.raises(ValueError):
        capabilities.resolve_global_use({"teleporter"})


# --- assemble_plan wiring ----------------------------------------------------

def _base_sel(**kw) -> InstallSelections:
    sel = propose("desktop")
    sel.disk = "vda"
    # desktop is rootless → needs an admin user, not a root pw
    sel.users = [UserDraft(name="captain", admin=True)]
    for k, v in kw.items():
        setattr(sel, k, v)
    return sel


def test_plan_carries_license_admin_and_use():
    sel = _base_sel()
    plan = assemble_plan(sel, _stage3())
    assert plan.license == "full"
    assert plan.admin_model == "rootless"
    assert plan.root_password is False           # rootless locks root
    assert plan.global_use == capabilities.resolve_global_use(sel.capabilities)


def test_rootless_requires_admin_user():
    sel = _base_sel(users=[])                          # no admin user
    with pytest.raises(ValueError, match="admin-capable"):
        assemble_plan(sel, _stage3())


def test_traditional_requires_root_password():
    sel = propose("server")
    sel.disk = "vda"
    sel.admin_model = "traditional"
    sel.root_password = ""
    with pytest.raises(ValueError, match="root password"):
        assemble_plan(sel, _stage3())
    sel.root_password = "hunter2"
    plan = assemble_plan(sel, _stage3())
    assert plan.root_password is True


def test_bad_license_and_admin_rejected():
    sel = _base_sel(license="pirated")
    with pytest.raises(ValueError, match="license"):
        assemble_plan(sel, _stage3())
    sel = _base_sel(admin_model="anarchy")
    with pytest.raises(ValueError, match="admin model"):
        assemble_plan(sel, _stage3())


def test_make_conf_overrides_frozen_sorted():
    sel = _base_sel(make_conf_overrides={"VIDEO_CARDS": "amdgpu", "ACCEPT_KEYWORDS": "~amd64"})
    plan = assemble_plan(sel, _stage3())
    assert plan.make_conf_overrides == (
        ("ACCEPT_KEYWORDS", "~amd64"), ("VIDEO_CARDS", "amdgpu"))


def test_license_policies_cover_three_rungs():
    assert set(LICENSE_POLICIES) == {"libre", "redistributable", "full"}
    assert assemble.LICENSE_POLICIES["full"].endswith("@EULA")


def test_separate_home_adds_a_home_mount():
    sel = _base_sel(separate_home=True, root_size="30G", home_fs="ext4")
    plan = assemble_plan(sel, _stage3())
    paths = [m.path for m in plan.mount.mounts]
    assert "/" in paths and "/home" in paths
    assert any(f.label == "home" for f in plan.disk.filesystems)


def test_bad_clock_mode_rejected():
    import pytest
    sel = _base_sel(clock="ntpd")
    with pytest.raises(ValueError, match="clock"):
        assemble_plan(sel, _stage3())


def test_user_password_marks_set_password():
    sel = _base_sel(users=[UserDraft(name="captain", admin=True, password="hunter2")])
    plan = assemble_plan(sel, _stage3())
    assert plan.users and plan.users[0].set_password is True
