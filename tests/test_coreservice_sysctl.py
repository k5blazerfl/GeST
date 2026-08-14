"""CI-safe tests for the gestd sysctl adapter (pure validate/render + contract).
Live GetSettings read is exercised by the round-trip on the host."""

from gest.coreservice import sysctl_adapter as adapter
from gest.ipc import core_contract


def test_validate_good_and_bad():
    assert adapter.validate({"net.ipv4.tcp_syncookies": "1"}) == (True, "")
    ok, msg = adapter.validate({"bad key!": "x"})
    assert not ok and "invalid sysctl" in msg


def test_render_matches_core():
    from gest.core.sysctl import config
    settings = {"net.ipv4.tcp_syncookies": "1", "kernel.kptr_restrict": "1"}
    assert adapter.render(settings) == config.render_conf(settings)


def test_sysctl_contract_shape():
    assert core_contract.SYSCTL_CORE_IFACE == "org.gentoo.gest.core1.Sysctl"
    assert core_contract.SYSCTL_CORE_PATH == "/org/gentoo/gest/core/Sysctl"
