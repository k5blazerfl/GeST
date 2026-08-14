"""Pure adapter for the sysctl core module — the GeST sysctl.d drop-in."""

from __future__ import annotations

from gest.core.sysctl import config, reader


def get_settings() -> dict[str, str]:
    """The current key/values in the GeST sysctl.d drop-in."""
    return dict(reader.current_settings())


def validate(settings: dict[str, str]) -> tuple[bool, str]:
    if config.valid_settings(settings):
        return True, ""
    return False, "invalid sysctl settings (bad key or value)"


def render(settings: dict[str, str]) -> str:
    """The sysctl.d drop-in text a write would produce (preview)."""
    return config.render_conf(settings)
