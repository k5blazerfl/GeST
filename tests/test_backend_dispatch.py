"""Dispatch/auth tests for the backend services via a fake D-Bus invocation.

These exercise the real method routing, polkit gating and argument validation
without a live system bus: polkit and the subprocess runner are stubbed, and a
fake invocation captures the reply. They need PyGObject (gi), so they run in the
full local suite rather than the dependency-light CI subset.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from gest.backend import datetime as datetime_mod  # noqa: E402
from gest.backend import disk as disk_mod  # noqa: E402
from gest.backend import network as network_mod  # noqa: E402
from gest.backend import system as system_mod  # noqa: E402
from gest.backend import users as users_mod  # noqa: E402


class _FakeInvocation:
    def __init__(self):
        self.value = None
        self.error = None
        self.dbus_error = None

    def return_value(self, variant):
        self.value = variant.unpack()

    def return_error_literal(self, quark, code, message):
        self.error = (code, message)

    def return_dbus_error(self, name, message):
        self.dbus_error = (name, message)


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


def _disk_service():
    svc = disk_mod.DiskService.__new__(disk_mod.DiskService)
    svc._conn = None
    return svc


def _disk_call(svc, method, values):
    inv = _FakeInvocation()
    svc._on_call(None, ":1.5", "/p", "iface", method, _FakeParams(values), inv)
    return inv


def test_disk_write_unauthorized_denied(monkeypatch):
    monkeypatch.setattr(disk_mod, "check_authorization", lambda *a: False)
    monkeypatch.setattr(disk_mod, "caller_uid", lambda *a: 1000)
    inv = _disk_call(_disk_service(), "WriteFstabEntry",
                     ["UUID=x", "/mnt/data", "ext4", "defaults", 0, 0])
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.ACCESS_DENIED


def test_disk_unknown_method(monkeypatch):
    monkeypatch.setattr(disk_mod, "check_authorization", lambda *a: True)
    inv = _disk_call(_disk_service(), "Nope", [])
    assert inv.error[0] == Gio.DBusError.UNKNOWN_METHOD


def test_disk_write_protected_refused(monkeypatch):
    # writing the root entry is refused (INVALID_ARGS) before any file is touched
    monkeypatch.setattr(disk_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(disk_mod, "caller_uid", lambda *a: 0)
    inv = _disk_call(_disk_service(), "WriteFstabEntry",
                     ["UUID=x", "/", "ext4", "defaults", 0, 1])
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_disk_write_bad_options_invalid_args(monkeypatch):
    monkeypatch.setattr(disk_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(disk_mod, "caller_uid", lambda *a: 0)
    inv = _disk_call(_disk_service(), "WriteFstabEntry",
                     ["UUID=x", "/mnt/data", "ext4", "bad options", 0, 0])
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_disk_mount_bad_target_invalid_args(monkeypatch):
    monkeypatch.setattr(disk_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(disk_mod, "caller_uid", lambda *a: 0)
    inv = _disk_call(_disk_service(), "Mount", ["swap"])  # not a real mount target
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def _datetime_service():
    svc = datetime_mod.DateTimeService.__new__(datetime_mod.DateTimeService)
    svc._conn = None
    return svc


def test_datetime_setclock_unauthorized_denied(monkeypatch):
    monkeypatch.setattr(datetime_mod, "check_authorization", lambda *a: False)
    monkeypatch.setattr(datetime_mod, "caller_uid", lambda *a: 1000)
    inv = _FakeInvocation()
    _datetime_service()._on_call(None, ":1.5", "/p", "i", "SetClock",
                                 _FakeParams(["2026-08-08 12:00:00"]), inv)
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.ACCESS_DENIED


def test_datetime_bad_timestamp_invalid_args(monkeypatch):
    # authorized but a malformed timestamp is refused before `date -s` runs
    monkeypatch.setattr(datetime_mod, "check_authorization", lambda *a: True)
    monkeypatch.setattr(datetime_mod, "caller_uid", lambda *a: 0)
    inv = _FakeInvocation()
    _datetime_service()._on_call(None, ":1.5", "/p", "i", "SetClock",
                                 _FakeParams(["not-a-date"]), inv)
    assert inv.value is None
    assert inv.error[0] == Gio.DBusError.INVALID_ARGS


def test_datetime_unknown_method(monkeypatch):
    monkeypatch.setattr(datetime_mod, "check_authorization", lambda *a: True)
    inv = _FakeInvocation()
    _datetime_service()._on_call(None, ":1.5", "/p", "i", "Nope", _FakeParams([]), inv)
    assert inv.error[0] == Gio.DBusError.UNKNOWN_METHOD


def _software_service():
    from gest.backend import service as service_mod
    svc = service_mod.SoftwareService.__new__(service_mod.SoftwareService)
    svc._conn = None
    svc._active = 0
    svc._operation = ""
    svc._last_activity = 0
    return svc


def _sw_call(svc, method, values):
    inv = _FakeInvocation()
    svc._on_method_call(None, ":1.5", "/p", "iface", method, _FakeParams(values), inv)
    return inv


def test_package_status_reports_a_running_session_op():
    svc = _software_service()
    svc._active = 1
    svc._operation = "A system update"
    inv = _sw_call(svc, "PackageStatus", [])
    assert inv.value == (True, "A system update is running in another GeST session")


def test_package_status_reports_external_emerge(monkeypatch):
    from gest.backend import service as service_mod
    monkeypatch.setattr(service_mod, "external_emerge", lambda: "emerge")
    inv = _sw_call(_software_service(), "PackageStatus", [])   # _active == 0
    assert inv.value == (True, "An external emerge is running outside GeST")


def test_package_status_free_when_idle(monkeypatch):
    from gest.backend import service as service_mod
    monkeypatch.setattr(service_mod, "external_emerge", lambda: None)
    inv = _sw_call(_software_service(), "PackageStatus", [])
    assert inv.value == (False, "")


def test_mutating_call_rejected_when_busy():
    from gest.ipc.interface import BUSY_ERROR
    # A session op is active — a second update must be refused before polkit.
    called = {"polkit": False}
    svc = _software_service()
    svc._check_authorized = lambda *a: called.__setitem__("polkit", True) or True
    svc._active = 1
    svc._operation = "A system update"
    inv = _sw_call(svc, "UpdateWorld", [])
    assert inv.dbus_error is not None
    assert inv.dbus_error[0] == BUSY_ERROR
    assert "another GeST session" in inv.dbus_error[1]
    assert inv.value is None                 # nothing started
    assert called["polkit"] is False         # refused before asking for auth


def test_mutating_call_rejected_for_external_emerge(monkeypatch):
    from gest.backend import service as service_mod
    from gest.ipc.interface import BUSY_ERROR
    monkeypatch.setattr(service_mod, "external_emerge", lambda: "emerge")
    inv = _sw_call(_software_service(), "Sync", [])   # idle here, but emerge outside
    assert inv.dbus_error is not None
    assert inv.dbus_error[0] == BUSY_ERROR
    assert "external emerge" in inv.dbus_error[1]


def test_authorization_variant_builds():
    # Regression: embedding a pre-built GLib.Variant subject raised TypeError on
    # newer PyGObject; the argument must be built with an inline subject tuple.
    from gest.backend.polkit import authorization_variant
    variant = authorization_variant(":1.7", "org.gentoo.gest.software.install")
    assert variant.get_type_string() == "((sa{sv})sa{ss}us)"


def test_authorization_is_granted_handles_wrapped_and_flat():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import GLib

    from gest.backend.polkit import authorization_is_granted
    # newer PyGObject: the out-args tuple is wrapped ((bool, bool, a{ss}),)
    wrapped = GLib.Variant("((bba{ss}))", ((True, False, {}),))
    assert authorization_is_granted(wrapped) is True
    denied = GLib.Variant("((bba{ss}))", ((False, False, {}),))
    assert authorization_is_granted(denied) is False
    # older PyGObject: the struct came back flat (bool, bool, a{ss})
    flat = GLib.Variant("(bba{ss})", (True, False, {}))
    assert authorization_is_granted(flat) is True
