"""CI-safe tests for firewall backend detection and menu-routing logic.

The active-backend reduction is pure over four booleans, so it is asserted by
constructing FirewallStatus directly; the individual probes are driven with a
fake runner returning canned (code, stdout) pairs.
"""

from gest.core import firewall_detect
from gest.core.firewall_detect import FirewallStatus


def _runner(mapping):
    """A fake runner: argv[0..] first token → (code, stdout). Matches on the
    ``firewall-cmd --state`` invocation the probes actually make."""
    def run(argv):
        return mapping.get(tuple(argv), (127, ""))
    return run


# --- active reduction (pure over the four signals) --------------------------

def test_active_firewalld_running_only():
    s = FirewallStatus(firewalld_installed=True, firewalld_running=True,
                       nftables_installed=True, nftables_active=False)
    assert s.active == "firewalld"


def test_active_nftables_only():
    s = FirewallStatus(firewalld_installed=False, firewalld_running=False,
                       nftables_installed=True, nftables_active=True)
    assert s.active == "nftables"


def test_active_both():
    s = FirewallStatus(firewalld_installed=True, firewalld_running=True,
                       nftables_installed=True, nftables_active=True)
    assert s.active == "both"


def test_active_none():
    s = FirewallStatus(firewalld_installed=False, firewalld_running=False,
                       nftables_installed=False, nftables_active=False)
    assert s.active == "none"


# --- running probe via fake runner ------------------------------------------

def test_firewalld_running_true_when_state_running():
    run = _runner({("firewall-cmd", "--state"): (0, "running\n")})
    assert firewall_detect.firewalld_running(run)


def test_firewalld_running_false_when_not_running():
    run = _runner({("firewall-cmd", "--state"): (252, "not running\n")})
    assert not firewall_detect.firewalld_running(run)
    # a plain non-zero exit with no output is also "not running"
    assert not firewall_detect.firewalld_running(_runner({}))


# --- nftables_active best-effort signal -------------------------------------

def test_nftables_active_tracks_managed(monkeypatch):
    monkeypatch.setattr(firewall_detect.nft_reader, "is_managed", lambda: True)
    assert firewall_detect.nftables_active()
    monkeypatch.setattr(firewall_detect.nft_reader, "is_managed", lambda: False)
    assert not firewall_detect.nftables_active()


# --- detect() wires the probes together -------------------------------------

def test_detect_reports_firewalld_when_running(monkeypatch):
    monkeypatch.setattr(firewall_detect.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(firewall_detect.nft_reader, "is_managed", lambda: False)
    run = _runner({("firewall-cmd", "--state"): (0, "running\n")})
    status = firewall_detect.detect(run)
    assert status.firewalld_installed and status.firewalld_running
    assert status.nftables_installed and not status.nftables_active
    assert status.active == "firewalld"


def test_detect_reports_none_when_nothing_present(monkeypatch):
    monkeypatch.setattr(firewall_detect.shutil, "which", lambda name: None)
    monkeypatch.setattr(firewall_detect.nft_reader, "is_managed", lambda: False)
    status = firewall_detect.detect(_runner({}))
    assert status.active == "none"
    assert not status.firewalld_installed and not status.nftables_installed
