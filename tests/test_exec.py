"""CI-safe tests for the execution layer: runtime selection, the fake executor,
and the direct (in-process) executor over a harmless real command."""

import asyncio

import pytest

from gest.core.exec.executor import DBusExecutor, DirectExecutor, FakeExecutor
from gest.core.exec.select import choose_executor

# --- runtime selection ------------------------------------------------------

def test_root_selects_direct():
    ex = choose_executor(geteuid=lambda: 0, environ={})
    assert isinstance(ex, DirectExecutor)


def test_non_root_selects_dbus():
    ex = choose_executor(geteuid=lambda: 1000, environ={})
    assert isinstance(ex, DBusExecutor)


def test_override_forces_path_regardless_of_euid():
    assert isinstance(choose_executor(geteuid=lambda: 1000, environ={"GEST_EXEC": "direct"}),
                      DirectExecutor)
    assert isinstance(choose_executor(geteuid=lambda: 0, environ={"GEST_EXEC": "dbus"}),
                      DBusExecutor)


def test_bad_override_raises():
    with pytest.raises(ValueError):
        choose_executor(geteuid=lambda: 0, environ={"GEST_EXEC": "nonsense"})


# --- fake executor ----------------------------------------------------------

def test_fake_executor_records_calls_and_codes():
    ex = FakeExecutor(code_for=lambda argv: 7 if argv[0] == "false" else 0)
    seen: list[str] = []
    ok = asyncio.run(ex.run(["true", "x"], on_progress=seen.extend))
    bad = asyncio.run(ex.run(["false"]))
    assert ok.code == 0 and bad.code == 7
    assert ex.calls == [["true", "x"], ["false"]]
    assert seen == ["$ true x"]                    # progress batch delivered


# --- direct executor (real subprocess, harmless) ----------------------------

def test_direct_executor_streams_output_and_exit_code():
    ex = DirectExecutor()
    lines: list[str] = []
    result = asyncio.run(ex.run(
        ["/bin/sh", "-c", "echo hello; echo world; exit 3"],
        on_progress=lines.extend,
    ))
    assert result.code == 3
    assert lines == ["hello", "world"]
    assert result.output == "hello\nworld"


def test_dbus_executor_stub_raises_until_wired():
    with pytest.raises(NotImplementedError):
        asyncio.run(DBusExecutor().run(["sgdisk", "--zap-all", "/dev/sda"]))


# --- exec failure is a legible non-zero result, not a raw OSError -----------

def test_missing_binary_returns_exec_failed_not_raise():
    from gest.core.exec.runner import EXEC_FAILED
    ex = DirectExecutor()
    lines: list[str] = []
    result = asyncio.run(ex.run(["gest-no-such-binary-xyz", "-h"], on_progress=lines.extend))
    assert result.code == EXEC_FAILED                      # 127, not an exception
    assert "could not run 'gest-no-such-binary-xyz'" in result.output
    assert lines and "could not run" in lines[-1]          # also streamed to progress


def test_eio_exec_failure_hints_at_the_medium(monkeypatch):
    import errno as _errno

    from gest.core.exec import runner

    async def _boom(*_a, **_k):
        raise OSError(_errno.EIO, "Input/output error", "env")

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", _boom)
    result = asyncio.run(runner.stream(["env", "PKGDIR=/x", "quickpkg"]))
    assert result.code == runner.EXEC_FAILED
    assert "could not run 'env'" in result.output
    assert "install medium may be failing" in result.output   # actionable hint
    assert "re-burn" in result.output
