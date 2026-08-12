"""The backend client's busy-error translation (gest.core.software.backend_client).

Verifies that a D-Bus BUSY_ERROR fault becomes a typed BackendBusy carrying the
message, while any other D-Bus error propagates unchanged.
"""

import asyncio

import pytest
from dbus_next.errors import DBusError

from gest.core.software.backend_client import BackendBusy, _guard_busy
from gest.ipc.interface import BUSY_ERROR


async def _raise(exc):
    raise exc


def test_busy_error_becomes_backendbusy():
    err = DBusError(BUSY_ERROR, "An external emerge is running outside GeST", None)
    with pytest.raises(BackendBusy) as caught:
        asyncio.run(_guard_busy(_raise(err)))
    assert caught.value.message == "An external emerge is running outside GeST"


def test_other_dbus_error_propagates():
    err = DBusError("org.freedesktop.DBus.Error.AccessDenied", "nope", None)
    with pytest.raises(DBusError):
        asyncio.run(_guard_busy(_raise(err)))


def test_success_passes_through():
    async def _ok():
        return (True, "done")
    assert asyncio.run(_guard_busy(_ok())) == (True, "done")
