"""CI-safe tests for the gestd Localization adapter (pure validate + contract).
Live current/list reads are exercised by the round-trip on the host."""

from gest.coreservice import localization_adapter as adapter
from gest.ipc import core_contract


def test_validate_dispatches_per_field():
    assert adapter.validate("timezone", "Europe/London") == (True, "")
    assert adapter.validate("locale", "en_US.UTF-8") == (True, "")
    assert adapter.validate("keymap", "us") == (True, "")
    ok, msg = adapter.validate("timezone", "Nowhere/Bad!")
    assert not ok and "invalid timezone" in msg


def test_validate_unknown_field():
    ok, msg = adapter.validate("colour", "blue")
    assert not ok and "unknown field" in msg


def test_localization_contract_shape():
    assert core_contract.LOCALIZATION_CORE_IFACE == "org.gentoo.gest.core1.Localization"
    assert core_contract.LOCALIZATION_CORE_PATH == "/org/gentoo/gest/core/Localization"
