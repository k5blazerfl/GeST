"""CI-safe tests for the sysctl core: validation, parse/render round-trip, and
the reader over a fixture drop-in."""

from gest.core.sysctl import commands, config, reader


def test_valid_key_and_value():
    for good in ("net.ipv4.ip_forward", "vm.swappiness", "kernel/kptr_restrict", "fs.file-max"):
        assert config.valid_key(good)
    for bad in ("", "Bad Key", "a b", "up.PER", "x" * 129):
        assert not config.valid_key(bad)
    assert config.valid_value("1") and config.valid_value("262144")
    for bad in ("", "a\nb", "has # comment", "x" * 257):
        assert not config.valid_value(bad)


def test_valid_settings_requires_nonempty_and_all_valid():
    assert config.valid_settings({"vm.swappiness": "10"})
    assert not config.valid_settings({})
    assert not config.valid_settings({"bad key": "1"})
    assert not config.valid_settings({"vm.swappiness": "a\nb"})


def test_parse_handles_equals_and_whitespace_forms():
    text = ("# a comment\n"
            "net.ipv4.ip_forward = 1\n"
            "vm.swappiness=10\n"
            "kernel/kptr_restrict 2\n"
            "\n")
    assert config.parse_conf(text) == {
        "net.ipv4.ip_forward": "1",
        "vm.swappiness": "10",
        "kernel/kptr_restrict": "2",
    }


def test_render_is_sorted_with_marker_and_round_trips():
    settings = {"vm.swappiness": "10", "net.ipv4.ip_forward": "1"}
    text = config.render_conf(settings)
    assert text.startswith("# Managed by GeST\n")
    # sorted: net.* before vm.*
    assert text.index("net.ipv4.ip_forward") < text.index("vm.swappiness")
    assert config.parse_conf(text) == settings


def test_sysctl_argv():
    assert commands.sysctl_load_argv("/etc/sysctl.d/10-gest.conf") == \
        ["sysctl", "-p", "/etc/sysctl.d/10-gest.conf"]
    assert commands.sysctl_read_argv("vm.swappiness") == ["sysctl", "-n", "vm.swappiness"]


def test_current_settings_reads_dropin(tmp_path):
    p = tmp_path / "10-gest.conf"
    p.write_text("# Managed by GeST\nvm.swappiness = 5\n")
    assert reader.current_settings(str(p)) == {"vm.swappiness": "5"}
    assert reader.current_settings(str(tmp_path / "missing")) == {}


def test_live_value_via_fake_runner():
    assert reader.live_value("vm.swappiness", lambda argv: "60\n") == "60"
    assert reader.live_value("bad key", lambda argv: "x") == ""    # invalid key short-circuits
