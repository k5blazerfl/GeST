"""The read dispatcher routes to the systemd vs OpenRC reader by init."""

from gest.core.services import dispatch


def _systemd_outputs():
    from gest.core.services import reader
    return {
        tuple(reader._LIST_UNIT_FILES): "sshd.service enabled\n",
        tuple(reader._LIST_UNITS): "sshd.service loaded active running OpenSSH\n",
    }


def test_dispatch_list_routes_to_openrc(monkeypatch):
    monkeypatch.setenv("GEST_INIT", "openrc")
    outputs = {
        ("rc-service", "--list"): "ollama\n",
        ("rc-update", "show"): "  ollama | default\n",
        ("rc-status", "--all"): " ollama [ stopped ]\n",
    }
    services = dispatch.list_services(lambda argv: outputs[tuple(argv)])
    assert [s.name for s in services] == ["ollama"]
    assert services[0].runlevels == ["default"]


def test_dispatch_list_routes_to_systemd(monkeypatch):
    monkeypatch.setenv("GEST_INIT", "systemd")
    outputs = _systemd_outputs()
    services = dispatch.list_services(lambda argv: outputs[tuple(argv)])
    assert [s.name for s in services] == ["sshd.service"]
    assert services[0].runlevels == []  # systemd services carry no runlevels


def test_dispatch_describe_routes_and_accepts_uniform_kwargs(monkeypatch):
    # The adapter/TUI pass a superset of kwargs; dispatch routes each to the
    # reader that accepts it without either path raising on the other's kwargs.
    monkeypatch.setenv("GEST_INIT", "openrc")
    d = dispatch.describe_service(
        "ollama", lambda argv: "",
        status="started", sub_state="running", enabled_state="enabled",
        runlevels=["default"],
    )
    assert d.name == "ollama" and d.status == "active" and d.runlevels == ["default"]
