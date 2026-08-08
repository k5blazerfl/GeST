"""Dispatch/auth tests for the backend services via a fake D-Bus invocation.

These exercise the real method routing, polkit gating and argument validation
without a live system bus: polkit and the subprocess runner are stubbed, and a
fake invocation captures the reply. They need PyGObject (gi), so they run in the
full local suite rather than the dependency-light CI subset.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from gest.backend import network as network_mod  # noqa: E402
from gest.backend import system as system_mod  # noqa: E402
from gest.backend import users as users_mod  # noqa: E402


class _FakeInvocation:
    def __init__(self):
        self.value = None
        self.error = None

    def return_value(self, variant):
        self.value = variant.unpack()

    def return_error_literal(self, quark, code, message):
        self.error = (code, message)


class _FakeParams:
    def __init__(self, values):
        self._values = tuple(values)

    def unpack(self):
        return self._values


def _users_service():
    # __init__ registers on a connection; pass None and skip registration.
    svc = users_mod.UsersService.__new__(users_mod.UsersService)
    svc._conn = None
    return svc


def _call(svc, method, values):
    inv = _FakeInvocation()
    svc._on_call(None, ":1.5", "/p", "iface", method, _FakeParams(values), inv)
    return inv


def test_adduser_authorized_runs(monkeypatch):
    monkeypatch.setattr(users_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(users_mod, "caller_uid", lambda *a: 1000)
    monkeypatch.setattr(users_mod, "_run", lambda argv, stdin=None: (True, "created"))
    inv = _call(_users_service(), "AddUser", ["alice", "", "", "", "", False])
    assert inv.error is None
    assert inv.value == (True, "created")


def test_adduser_unauthorized_denied(monkeypatch):
    monkeypatch.setattr(users_mod, "check_authorization", lambda *a: False)
    monkeypatch.setattr(users_mod, "caller_uid", lambda *a: 1000)
    inv = _call(_users_service(), "AddUser", ["alice", "", "", "", "", False])
    assert inv.value is None
    assert inv.error is not None
    assert inv.error[0] == Gio.DBusError.ACCESS_DENIED


def test_adduser_bad_name_invalid_args(monkeypatch):
    monkeypatch.setattr(users_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(users_mod, "caller_uid", lambda *a: 0)
    monkeypatch.setattr(users_mod, "_run", lambda argv, stdin=None: (True, "x"))
    inv = _call(_users_service(), "AddUser", ["Bad Name", "", "", "", "", False])
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_unknown_method(monkeypatch):
    monkeypatch.setattr(users_mod, "check_authorization", lambda *a: True)
    inv = _call(_users_service(), "Nope", [])
    assert inv.error[0] == Gio.DBusError.UNKNOWN_METHOD


def test_sethostname_validates(monkeypatch):
    monkeypatch.setattr(system_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(system_mod, "caller_uid", lambda *a: 0)
    svc = system_mod.SystemService.__new__(system_mod.SystemService)
    svc._conn = None
    inv = _FakeInvocation()
    svc._on_call(None, ":1.5", "/p", "i", "SetHostname",
                 _FakeParams(["bad host"]), inv)
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_setinterfaceconfig_bad_address_invalid_args(monkeypatch):
    monkeypatch.setattr(network_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(network_mod, "caller_uid", lambda *a: 0)
    svc = network_mod.NetworkService.__new__(network_mod.NetworkService)
    svc._conn = None
    inv = _FakeInvocation()
    # static with a non-CIDR address must be rejected before any file write
    svc._on_call(None, ":1.5", "/p", "i", "SetInterfaceConfig",
                 _FakeParams(["eth0", "static", "not-a-cidr", ""]), inv)
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_setlink_unauthorized_denied(monkeypatch):
    monkeypatch.setattr(network_mod, "check_authorization", lambda *a: False)
    monkeypatch.setattr(network_mod, "caller_uid", lambda *a: 1000)
    svc = network_mod.NetworkService.__new__(network_mod.NetworkService)
    svc._conn = None
    inv = _FakeInvocation()
    svc._on_call(None, ":1.5", "/p", "i", "SetLink", _FakeParams(["eth0", True]), inv)
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.ACCESS_DENIED


def test_authorization_variant_builds():
    # Regression: embedding a pre-built GLib.Variant subject raised TypeError on
    # newer PyGObject; the argument must be built with an inline subject tuple.
    from gest.backend.polkit import authorization_variant
    variant = authorization_variant(":1.7", "org.gentoo.gest.software.install")
    assert variant.get_type_string() == "((sa{sv})sa{ss}us)"
