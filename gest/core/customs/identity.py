"""Map a running foreign window back to its synthesized ``.desktop``.

A Wine/Proton app is an Xwayland toplevel with a ``WM_CLASS``; a Wine-Wayland or
RemoteApp window has a Wayland ``app_id``. When Customs synthesizes a launcher it
records which class/app-id that app presents, so HeDE's foreign-toplevel taskbar
can show the right icon/title instead of a generic "wine"/"freerdp" blob.

Pure: a registry of ``key → desktop_id`` with case/format-normalized lookup. The
HeDE C++ taskbar consults an equivalent map at runtime; this is the source of
truth GeST writes when it creates the entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def normalize(key: str) -> str:
    """Normalize an ``app_id``/``WM_CLASS`` for matching: strip + lowercase, and
    for an X11 ``WM_CLASS`` take the instance (the part before a NUL). Dots are
    left intact — reverse-DNS Wayland app-ids (``org.freerdp.client``) use them."""
    key = key.strip().lower()
    if "\x00" in key:
        key = key.split("\x00", 1)[0]
    return key


@dataclass
class IdentityMap:
    """``normalized key → desktop_id``. Multiple keys may point at one launcher
    (an app can present different WM_CLASS values across versions)."""

    _by_key: dict[str, str] = field(default_factory=dict)

    def register(self, keys: list[str], desktop_id: str) -> None:
        for key in keys:
            norm = normalize(key)
            if norm:
                self._by_key[norm] = desktop_id

    def resolve(self, key: str) -> str | None:
        return self._by_key.get(normalize(key))

    def unregister(self, desktop_id: str) -> None:
        self._by_key = {k: v for k, v in self._by_key.items() if v != desktop_id}

    def keys_for(self, desktop_id: str) -> list[str]:
        return sorted(k for k, v in self._by_key.items() if v == desktop_id)
