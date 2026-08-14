"""Tests for the Repos / Wi-Fi / sshd pure helpers."""

from gest.core.repos.reader import Repo
from gest.core.sshd.model import SshdSettings
from gest.core.wifi.model import WifiNetwork
from gest.qt.repos import repo_label
from gest.qt.sshd import sshd_summary
from gest.qt.wifi import wifi_label


def test_repo_label():
    assert repo_label(Repo(name="gentoo", main=True)) == "gentoo (main)"
    assert repo_label(Repo(name="guru", enabled=True)) == "guru"
    assert repo_label(Repo(name="old", enabled=False)) == "old (disabled)"


def test_wifi_label():
    assert wifi_label(WifiNetwork(ssid="home", key_mgmt="WPA-PSK")).startswith("home")
    assert wifi_label(WifiNetwork(ssid="cafe", key_mgmt="NONE")) == "cafe"


def test_sshd_summary():
    s = SshdSettings(port=2222, permit_root_login="no", password_authentication=False)
    assert sshd_summary(s) == "port 2222 · root login: no · password auth: off"
