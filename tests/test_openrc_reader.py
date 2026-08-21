"""Tests for the OpenRC services reader (pure parsing + runner injection).

Runner-injected, so these pass on any host regardless of the live init.
"""

from gest.core.services import openrc_reader as rc


def test_parse_enabled():
    text = (
        "            sshd |      default\n"
        "          ollama |      default nonetwork\n"
        "         netmount |      \n"          # no runlevel token
    )
    assert rc.parse_enabled(text) == {
        "sshd": ["default"],
        "ollama": ["default", "nonetwork"],
        "netmount": [],
    }


def test_parse_status():
    text = (
        " sshd                                     [  started  ]\n"
        " ollama                                   [  stopped  ]\n"
        " crashed-svc                              [  crashed  ]\n"
    )
    assert rc.parse_status(text) == {
        "sshd": "started", "ollama": "stopped", "crashed-svc": "crashed",
    }


def test_list_services_normalizes_status_and_enabled():
    outputs = {
        ("rc-service", "--list"): "sshd\nollama\nnetmount\n",
        ("rc-update", "show"): "  sshd | default\n  ollama | default\n",
        ("rc-status", "--all"): (
            " sshd    [ started ]\n ollama   [ stopped ]\n netmount [ crashed ]\n"
        ),
    }
    services = rc.list_services(lambda argv: outputs[tuple(argv)])
    by = {s.name: s for s in services}
    # started → active (running); stopped → inactive; crashed → failed
    assert by["sshd"].status == "active" and by["sshd"].running
    assert by["ollama"].status == "inactive" and not by["ollama"].running
    assert by["netmount"].status == "failed"
    # enabled_state derived from runlevels
    assert by["sshd"].enabled and by["sshd"].enabled_state == "enabled"
    assert by["ollama"].runlevels == ["default"]
    # not in any runlevel → disabled, and it is NOT masked (systemd-only concept)
    assert not by["netmount"].enabled and by["netmount"].enabled_state == "disabled"
    assert not by["netmount"].masked


def test_list_services_includes_enabled_only_services():
    # A service enabled in rc-update but absent from rc-service --list still shows.
    outputs = {
        ("rc-service", "--list"): "sshd\n",
        ("rc-update", "show"): "  sshd | default\n  ollama | default\n",
        ("rc-status", "--all"): " sshd [ started ]\n",
    }
    names = {s.name for s in rc.list_services(lambda argv: outputs[tuple(argv)])}
    assert names == {"sshd", "ollama"}


def test_parse_describe_strips_bullet_and_label():
    assert rc.parse_describe(" * ollama: Run the ollama LLM server\n") == \
        "Run the ollama LLM server"
    assert rc.parse_describe("A plain description\n") == "A plain description"


def test_describe_service_maps_deps_and_swallows_systemd_kwargs():
    responses = {
        ("rc-service", "ollama", "describe"): " * ollama: LLM server\n",
        ("rc-service", "ollama", "ineed"): "net\n",
        ("rc-service", "ollama", "iuse"): "logger\n",
        ("rc-service", "ollama", "iwant"): "netmount\n",
        ("rc-service", "ollama", "needsme"): "\n",
    }
    d = rc.describe_service(
        "ollama", lambda argv: responses[tuple(argv)],
        status="started", enabled_state="enabled", runlevels=["default"],
        sub_state="ignored",  # systemd-only kwarg → swallowed, no error
    )
    assert d.description == "LLM server"
    assert d.requires == ["net"]                 # ineed
    assert d.wants == ["logger", "netmount"]     # iuse + iwant, sorted+deduped
    assert d.required_by == []                   # needsme empty
    assert d.after == []
    assert d.status == "active" and d.running    # normalized from "started"
    assert d.enabled_state == "enabled" and d.runlevels == ["default"]
    assert d.load_state == "loaded"
