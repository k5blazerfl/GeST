"""CI-safe tests for the gestd Hostname adapter (pure core<->data; no D-Bus)."""

from gest.coreservice import hostname_adapter as adapter
from gest.ipc import core_contract


def test_get_state_has_hostname_key():
    state = adapter.get_state()
    assert set(state) == {"hostname"}
    assert isinstance(state["hostname"], str) and state["hostname"]


def test_validate_accepts_good_and_rejects_bad():
    ok, msg = adapter.validate("my-host")
    assert ok and msg == ""
    ok, msg = adapter.validate("bad host!")
    assert not ok and "invalid hostname" in msg
    assert not adapter.validate("")[0]


def test_render_matches_the_conf_form():
    assert adapter.render("web01") == 'hostname="web01"\n'


def test_render_is_the_core_single_source():
    # gestd Render and the backend writer must render identically (both call core).
    from gest.core.system import hostname as core
    assert adapter.render("web01") == core.render_conf("web01")


def test_contract_is_versioned():
    assert core_contract.CORE_API_VERSION == 1
    assert core_contract.HOSTNAME_CORE_IFACE == "org.gentoo.gest.core1.Hostname"
    assert core_contract.CORE_BUS_NAME == "org.gentoo.gest.Core"
    assert core_contract.HOSTNAME_CORE_PATH == "/org/gentoo/gest/core/Hostname"
