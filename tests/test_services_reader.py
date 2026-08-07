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


def test_words_dedupes_and_sorts():
    assert reader._words("net   sshd net\nlocalmount\n") == ["localmount", "net", "sshd"]
    assert reader._words("   \n  ") == []


def test_parse_describe_strips_markers_and_label():
    assert reader.parse_describe(" * sshd: OpenSSH server\n * more\n") == "OpenSSH server"
    assert reader.parse_describe(" * A plain description\n") == "A plain description"
    assert reader.parse_describe("\n\n") == ""


def test_describe_service_with_injected_runner():
    outputs = {
        ("rc-service", "sshd", "describe"): " * OpenSSH server\n",
        ("rc-service", "sshd", "ineed"): "net\n",
        ("rc-service", "sshd", "iuse"): "logger dns\n",
        ("rc-service", "sshd", "iwant"): "",
        ("rc-service", "sshd", "needsme"): "",
    }
    d = reader.describe_service(
        "sshd", lambda argv: outputs[tuple(argv)],
        status="started", runlevels=["default"],
    )
    assert d.name == "sshd"
    assert d.description == "OpenSSH server"
    assert d.needs == ["net"]
    assert d.uses == ["dns", "logger"]
    assert d.wants == [] and d.needed_by == []
    assert d.running and d.runlevels == ["default"]
