"""Tests for the Network module's pure validation + backend-bridge mapping
(gest.qt.net)."""

from gest.qt.net import apply_interface_config, set_link, validate_static


def test_valid_static():
    assert validate_static("192.168.1.10/24", "192.168.1.1") == ""
    assert validate_static("10.0.0.2/8", "") == ""  # gateway optional


def test_bad_address():
    assert validate_static("192.168.1.10", "").startswith("Address")  # no CIDR
    assert validate_static("not-an-ip/24", "") != ""


def test_bad_gateway():
    assert validate_static("192.168.1.10/24", "999.1.1.1").startswith("Gateway")


class _FakeBackend:
    """A NetworkBackend that returns a HANDLED failure/success without raising."""
    async def connect(self):
        return self

    async def set_interface_config(self, *a, **k):
        return [False, "netifrc rejected config"]

    async def set_link(self, *a, **k):
        return [True, "link up"]

    async def close(self):
        return None


def test_mutations_propagate_backend_ok_and_message(monkeypatch):
    # A backend that returns [False, msg] *without raising* must surface as
    # (False, msg) — not a false success. Regression: gest.qt.net once discarded
    # the backend's [ok, output] and always reported (True, "") on no exception,
    # so the widget showed "Applied." even when the backend refused the change.
    import gest.core.network.backend_client as bc

    monkeypatch.setattr(bc, "NetworkBackend", _FakeBackend)
    assert apply_interface_config("eth0", "static", "10.0.0.2/24", "10.0.0.1") == (
        False, "netifrc rejected config")
    assert set_link("eth0", True) == (True, "link up")
