"""CI-safe tests for the installer connectivity pre-flight — a fake URL opener,
no real network."""

from gest.core.install import netcheck
from gest.core.install.netcheck import check_connectivity


class _FakeResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(status):
    def open_(url, timeout=None):
        return _FakeResp(status)
    return open_


def test_online_on_2xx_3xx():
    ok, detail = check_connectivity(opener=_opener(200))
    assert ok and "HTTP 200" in detail
    assert check_connectivity(opener=_opener(301))[0] is True


def test_offline_on_4xx_5xx():
    ok, detail = check_connectivity(opener=_opener(503))
    assert ok is False and "HTTP 503" in detail
    assert check_connectivity(opener=_opener(404))[0] is False


def test_offline_when_opener_raises():
    def boom(url, timeout=None):
        raise OSError("Network is unreachable")

    ok, detail = check_connectivity(opener=boom, probe_url="https://mirror/x")
    assert ok is False
    assert "Network is unreachable" in detail
    assert "https://mirror/x" in detail


def test_default_probe_targets_the_mirror():
    assert netcheck.DEFAULT_PROBE.startswith("https://")
    assert "/releases/" in netcheck.DEFAULT_PROBE


def test_resp_without_status_defaults_to_ok():
    class _Bare:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    assert check_connectivity(opener=lambda url, timeout=None: _Bare())[0] is True
