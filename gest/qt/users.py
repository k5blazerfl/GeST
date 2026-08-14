"""Users module logic: pure label + sync bridges to the Users backend."""

from __future__ import annotations

from gest.core.users.model import User
from gest.qt.backend import run_backend


def user_label(user: User) -> str:
    tag = " (system)" if user.system else ""
    if user.full_name:
        return f"{user.name} — {user.full_name}{tag}"
    return f"{user.name}{tag}"


def add_user(name: str, comment: str = "", shell: str = "", groups: str = "",
             system: bool = False) -> tuple[bool, str]:
    async def run():
        from gest.core.users.backend_client import UsersBackend

        backend = await UsersBackend().connect()
        try:
            return await backend.add_user(name, comment, shell, "", groups, system)
        finally:
            await backend.close()

    return run_backend(run)


def delete_user(name: str, remove_home: bool = False) -> tuple[bool, str]:
    async def run():
        from gest.core.users.backend_client import UsersBackend

        backend = await UsersBackend().connect()
        try:
            return await backend.delete_user(name, remove_home)
        finally:
            await backend.close()

    return run_backend(run)


def set_password(name: str, password: str) -> tuple[bool, str]:
    async def run():
        from gest.core.users.backend_client import UsersBackend

        backend = await UsersBackend().connect()
        try:
            return await backend.set_password(name, password)
        finally:
            await backend.close()

    return run_backend(run)
