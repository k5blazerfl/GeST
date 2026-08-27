"""Per-row detail copy on the non-Disk install gates (System Role, Base System,
Your Account, Get Online). Each gate's row_detail() should return purpose-written
copy for its own rows — not the whole-step help fallback."""

from __future__ import annotations

from gest.core.disk import reader as disk_reader
from gest.core.install import assemble
from gest.tui.runtime import App
from gest.tui.screens.install import wizard as wz


def _step(cls, monkeypatch, **selattrs):
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    monkeypatch.setattr(wz, "check_connectivity", lambda: (True, "ok"))
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])
    app = App()
    sel = assemble.propose("desktop")
    for k, v in selattrs.items():
        setattr(sel, k, v)
    return cls(app, sel), sel


def test_role_detail_is_per_role(monkeypatch):
    step, _ = _step(wz.RoleStep, monkeypatch)
    seen = {key: step.row_detail(f"◉ {lbl}", None) for key, lbl in step._ROLES}
    assert "headless" in seen["server"].lower()
    assert "helm desktop" in seen["desktop"].lower()
    # every role gets its own distinct copy (not the fallback help)
    assert len(set(seen.values())) == len(step._ROLES)
    assert all(d != step.help() for d in seen.values())


def test_base_system_detail_tracks_selection(monkeypatch):
    step, sel = _step(wz.BaseSystemStep, monkeypatch, admin_model="rootless",
                      license="libre", binary_pref=True)
    assert "prebuilt" in step.row_detail("Build strategy", "").lower() or \
           "binary" in step.row_detail("Build strategy", "").lower()
    assert "locked" in step.row_detail("Admin model", "").lower()      # rootless
    assert "use flag" in step.row_detail("Features (USE)", "").lower()
    assert "doas" in step.row_detail("Escalator", "").lower()
    # source strategy flips the copy
    sel.binary_pref = False
    assert "source" in step.row_detail("Build strategy", "").lower()


def test_license_detail_tracks_rung_and_relevance(monkeypatch):
    # gpu_auto off + no explicit nvidia → _nvidia_planned is deterministic (no lspci)
    step, sel = _step(wz.LicenseStep, monkeypatch, license="libre",
                      gpu_auto=False, nvidia_proprietary=False)
    assert "free/open-source" in step.row_detail("License policy", "").lower()
    # a covering rung names the agreements it requires for this machine
    sel.license = "full"
    assert "requires" in step.row_detail("License policy", "").lower()


def test_account_detail_covers_hostname_users_root(monkeypatch):
    step, _ = _step(wz.AccountStep, monkeypatch, admin_model="rootless")
    assert "hostname" in step.row_detail("Hostname", "").lower() or \
           "name this machine" in step.row_detail("Hostname", "").lower()
    assert "administrator" in step.row_detail("   + Add user", None).lower()
    assert "admin" in step.row_detail("   alice  (admin)", None).lower()
    # rootless → root is locked; traditional → root has a password
    assert "locks the root" in step.row_detail("Root", "disabled").lower()
    step2, _ = _step(wz.AccountStep, monkeypatch, admin_model="traditional")
    assert "password" in step2.row_detail("Root", "enabled").lower()


def test_online_detail_covers_actions(monkeypatch):
    step, _ = _step(wz.OnlineStep, monkeypatch)
    assert "dhcp" in step.row_detail("Bring up wired network (DHCP)", None).lower()
    assert "wi-fi" in step.row_detail("Set up Wi-Fi…", None).lower()
    assert "connected" in step.row_detail("Re-check connectivity", None).lower()
    assert "interface" in step.row_detail("enp5s0 (wired)", "up").lower()
