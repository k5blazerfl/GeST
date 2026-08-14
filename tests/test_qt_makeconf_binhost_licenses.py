"""Tests for the make.conf / binhost / licenses Qt pure helpers."""

from gest.core.binhost.model import Binhost
from gest.core.licenses.model import LicenseEntry
from gest.core.makeconf.reader import Var
from gest.qt.binhost import host_label
from gest.qt.licenses import entry_label
from gest.qt.makeconf import var_label


def test_var_label():
    assert var_label(Var(name="MAKEOPTS", value="-j8")) == "MAKEOPTS = -j8"


def test_host_label():
    managed = Binhost(name="gentoobinhost", sync_uri="https://x/y", managed=True)
    assert host_label(managed) == "gentoobinhost · https://x/y"
    external = Binhost(name="hand", sync_uri="", managed=False)
    assert host_label(external) == "hand (external) · —"


def test_entry_label():
    e = LicenseEntry(atom="app-arch/unrar", licenses=["unRAR"], managed=True)
    assert entry_label(e) == "app-arch/unrar → unRAR"
    empty = LicenseEntry(atom="x/y", licenses=[], managed=False)
    assert entry_label(empty) == "x/y (external) → (none)"
