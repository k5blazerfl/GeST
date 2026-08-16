"""Tests for the systemd services reader (pure parsing + runner injection)."""

from gest.core.services import reader


def test_parse_unit_files():
    text = (
        "sshd.service      enabled\n"
        "dbus.service      static\n"
        "getty@.service    enabled\n"          # template unit file — skipped
        "cups.service      disabled  disabled\n"
    )
    assert reader.parse_unit_files(text) == {
        "sshd.service": "enabled",
        "dbus.service": "static",
        "cups.service": "disabled",
    }


def test_parse_units_strips_bullet():
    text = (
        "sshd.service    loaded active   running OpenSSH server daemon\n"
        "● foo.service   loaded failed   failed  A failing unit\n"
    )
    units = reader.parse_units(text)
    assert units["sshd.service"] == ("active", "running", "OpenSSH server daemon")
    assert units["foo.service"] == ("failed", "failed", "A failing unit")


def test_list_services_merges_files_and_units():
    outputs = {
        tuple(reader._LIST_UNIT_FILES): "sshd.service enabled\ndbus.service static\n",
        tuple(reader._LIST_UNITS): "dbus.service loaded active running D-Bus\n",
    }
    services = reader.list_services(lambda argv: outputs[tuple(argv)])
    by = {s.name: s for s in services}
    assert by["dbus.service"].running and by["dbus.service"].enabled_state == "static"
    assert by["dbus.service"].description == "D-Bus"
    # sshd installed but not loaded → inactive, still enabled-at-boot
    assert not by["sshd.service"].running and by["sshd.service"].enabled
    assert by["sshd.service"].status == "inactive"


def test_words_dedupes_and_sorts():
    assert reader._words("net.target sshd.service net.target\nfoo\n") == [
        "foo", "net.target", "sshd.service",
    ]
    assert reader._words("   \n  ") == []


def test_parse_show():
    props = reader.parse_show("Description=OpenSSH server\nRequires=sysinit.target\nWants=\n")
    assert props["Description"] == "OpenSSH server"
    assert props["Requires"] == "sysinit.target"
    assert props["Wants"] == ""


def test_describe_service_with_injected_runner():
    show = (
        "Description=OpenSSH server\n"
        "Requires=sysinit.target\n"
        "Wants=network.target\n"
        "After=network.target sshd-keygen.target\n"
        "RequiredBy=\n"
        "WantedBy=multi-user.target\n"
        "ActiveState=active\n"
        "SubState=running\n"
        "UnitFileState=enabled\n"
        "LoadState=loaded\n"
    )
    d = reader.describe_service(
        "sshd.service", lambda argv: show,
        status="inactive", enabled_state="disabled",
    )
    assert d.name == "sshd.service"
    assert d.description == "OpenSSH server"
    assert d.requires == ["sysinit.target"]
    assert d.wants == ["network.target"]
    assert d.after == ["network.target", "sshd-keygen.target"]
    assert d.required_by == ["multi-user.target"]     # merged RequiredBy + WantedBy
    assert d.status == "active" and d.running and d.sub_state == "running"
    assert d.enabled_state == "enabled" and d.enabled and d.load_state == "loaded"
