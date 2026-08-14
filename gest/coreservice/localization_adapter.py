"""Pure adapter for the Localization core module (timezone / locale / keymap)."""

from __future__ import annotations

from typing import Any

from gest.core.system import console, locale, timezone


def get_state() -> dict[str, Any]:
    return {
        "timezone": timezone.current_timezone(),
        "locale": locale.current_locale(),
        "keymap": console.current_keymap(),
    }


def list_zones() -> list[str]:
    return timezone.list_zones()


def list_locales() -> list[str]:
    return locale.list_locales()


def list_keymaps() -> list[str]:
    return console.list_keymaps()


def validate(field: str, value: str) -> tuple[bool, str]:
    checks = {
        "timezone": timezone.valid_zone_name,
        "locale": locale.valid_locale,
        "keymap": console.valid_keymap,
    }
    check = checks.get(field)
    if check is None:
        return False, f"unknown field: {field!r} (timezone/locale/keymap)"
    return (True, "") if check(value) else (False, f"invalid {field}: {value!r}")
