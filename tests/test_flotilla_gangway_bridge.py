"""CI-safe tests for the Flotilla → Gangway bridge (IP parse + profile synth) and
the `flotilla connect`/`address` commands. No libvirt, no FreeRDP."""

from __future__ import annotations

from gest.core.flotilla import gangway_bridge, vessels
from gest.core.flotilla.model import OS_LINUX, OS_WINDOWS, Vessel
from gest.core.rdp import store as rdp_store
from gest.tui.flotilla.cli import CliIO, FlotillaEnv, run_cli

_DOMIFADDR = """\
 Name       MAC address          Protocol     Address
-------------------------------------------------------------------------------
 lo         00:00:00:00:00:00    ipv4         127.0.0.1/8
 Ethernet   52:54:00:aa:bb:cc    ipv4         192.168.122.50/24
"""


# ---- pure bridge -------------------------------------------------------
def test_parse_agent_ipv4_skips_loopback():
    assert gangway_bridge.parse_agent_ipv4(_DOMIFADDR) == "192.168.122.50"


def test_parse_agent_ipv4_empty_when_none():
    assert gangway_bridge.parse_agent_ipv4("no addresses here") == ""
    assert gangway_bridge.parse_agent_ipv4("") == ""


def test_profile_for_uses_ip_and_stable_name():
    v = Vessel(id="win11", name="Windows 11", os=OS_WINDOWS)
    p = gangway_bridge.profile_for(v, "10.0.0.9")
    assert p.host == "10.0.0.9" and p.name == "Windows 11 VM"
    assert p.drive_redirect and p.clipboard and p.nla  # sensible RDP defaults
    # a linked profile name is reused so re-connect updates the same profile.
    v.gangway_profile = "my-win"
    assert gangway_bridge.profile_for(v, "10.0.0.9").name == "my-win"


def test_profile_for_carries_provisioned_username():
    # NLA/CredSSP needs the guest's local account; the bridge must pass it through
    # (previously only `host` was set — the real gap this phase closes).
    v = Vessel(id="win11", name="Windows 11", os=OS_WINDOWS, unattend_username="flotilla")
    p = gangway_bridge.profile_for(v, "10.0.0.9")
    assert p.username == "flotilla"
    assert p.credential_attributes()["user"] == "flotilla"  # keys the Keychain lookup


# ---- CLI ---------------------------------------------------------------
class _H:
    def __init__(self, tmp_path, *, ip_output=_DOMIFADDR):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.launched: list = []
        self.store = str(tmp_path / "vessels")
        self.gw = str(tmp_path / "gangway")
        self.env = FlotillaEnv(
            io=CliIO(out=self.out.append, err=self.err.append), store_base=self.store,
            run_argv=lambda a: self.calls.append(a) or 0,
            capture=lambda a: ip_output,
            gangway_store_base=self.gw,
            launch_rdp=lambda profile: self.launched.append(profile) or 0)

    def make(self, os=OS_WINDOWS, entry="rdp"):
        vessels.save_vessel(Vessel(id="win11", name="Windows 11", os=os, entry=entry), self.store)


def test_address_reports_guest_ip(tmp_path):
    h = _H(tmp_path)
    h.make()
    assert run_cli(["address", "win11"], env=h.env) == 0
    assert h.out == ["192.168.122.50"]


def test_connect_rdp_provisions_profile_and_launches(tmp_path):
    h = _H(tmp_path)
    h.make(entry="rdp")
    assert run_cli(["connect", "win11"], env=h.env) == 0
    # a Gangway profile was saved at the discovered IP…
    saved = rdp_store.load_profile("Windows 11 VM", h.gw)
    assert saved is not None and saved.host == "192.168.122.50"
    # …and Gangway was launched with it; libvirt was NOT touched (no console).
    assert len(h.launched) == 1 and h.launched[0].host == "192.168.122.50"
    assert h.calls == []
    # the vessel remembers its linked profile.
    assert vessels.load_vessel("win11", h.store).gangway_profile == "Windows 11 VM"


def test_connect_console_opens_virtviewer(tmp_path):
    h = _H(tmp_path)
    h.make(entry="console")
    assert run_cli(["connect", "win11"], env=h.env) == 0
    assert h.calls[-1][0] == "virt-viewer" and h.launched == []


def test_connect_rdp_flag_overrides_console_entry(tmp_path):
    h = _H(tmp_path)
    h.make(entry="console")
    assert run_cli(["connect", "win11", "--rdp"], env=h.env) == 0
    assert len(h.launched) == 1


def test_connect_rdp_rejected_for_linux(tmp_path):
    h = _H(tmp_path)
    h.make(os=OS_LINUX, entry="console")
    assert run_cli(["connect", "win11", "--rdp"], env=h.env) == 2
    assert h.launched == []


def test_connect_no_ip_errors(tmp_path):
    h = _H(tmp_path, ip_output="no addresses")
    h.make(entry="rdp")
    assert run_cli(["connect", "win11"], env=h.env) == 1
    assert h.launched == [] and h.err
