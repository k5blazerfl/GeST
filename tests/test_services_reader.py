"""Tests for the OpenRC services reader (pure parsing + runner injection)."""

from gest.core.services import reader


def test_parse_enabled():
    text = "svc1 | default\nsvc2 | boot default\nnoise without pipe\n"
    assert reader.parse_enabled(text) == {
        "svc1": ["default"],
        "svc2": ["boot", "default"],
    }


def test_parse_status():
    text = "Runlevel: default\n foo   [  started  ]\n bar   [  stopped  ]\n"
    assert reader.parse_status(text) == {"foo": "started", "bar": "stopped"}


def test_list_services_with_injected_runner():
    outputs = {
        ("rc-service", "--list"): "sshd\ndbus\n",
        ("rc-update", "show"): "dbus | default\n",
        ("rc-status", "--all"): "Runlevel: default\n dbus  [ started ]\n",
    }
    services = reader.list_services(lambda argv: outputs[tuple(argv)])
    by = {s.name: s for s in services}
    assert by["dbus"].running and by["dbus"].enabled
    assert by["dbus"].runlevels == ["default"]
    assert not by["sshd"].running and not by["sshd"].enabled
