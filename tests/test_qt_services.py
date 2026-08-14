"""Tests for the Services module's pure helpers (gest.qt.services)."""

from gest.core.services.model import Service
from gest.qt.services import service_label, valid_action


def test_valid_action():
    assert valid_action("start") and valid_action("stop") and valid_action("restart")
    assert not valid_action("frobnicate")


def test_service_label():
    running = Service(name="dbus", status="started", runlevels=["default"])
    assert service_label(running) == "dbus — started · enabled"
    stopped = Service(name="foo", status="stopped", runlevels=[])
    assert service_label(stopped) == "foo — stopped"
