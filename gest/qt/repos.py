"""Repositories module logic: pure label + sync bridges to the Repos backend."""

from __future__ import annotations

from gest.core.repos.reader import Repo
from gest.qt.backend import run_backend


def repo_label(repo: Repo) -> str:
    if repo.main:
        return f"{repo.name} (main)"
    return repo.name if repo.enabled else f"{repo.name} (disabled)"


def _repo_call(method: str, *args) -> tuple[bool, str]:
    async def run():
        from gest.core.repos.backend_client import ReposBackend

        backend = await ReposBackend().connect()
        try:
            return await getattr(backend, method)(*args)
        finally:
            await backend.close()

    return run_backend(run)


def enable(name: str) -> tuple[bool, str]:
    return _repo_call("enable", name)


def disable(name: str) -> tuple[bool, str]:
    return _repo_call("disable", name)


def remove(name: str) -> tuple[bool, str]:
    return _repo_call("remove", name)


def add(name: str, sync_type: str, uri: str) -> tuple[bool, str]:
    return _repo_call("add", name, sync_type, uri)
