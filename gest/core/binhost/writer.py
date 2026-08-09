"""Build the :class:`ConfigWrite`\\ s that apply binhost changes.

Two surfaces: the GeST-owned ``binrepos.conf/gest.conf`` (rendered from the
managed host set via the INI codec) and the ``FEATURES`` variable in make.conf
(a token toggle that preserves the rest of the value). Both are handed to the
Portage ``WriteConfig`` RPC.
"""

from __future__ import annotations

from gest.core.binhost.model import Binhost
from gest.core.portage import paths
from gest.core.portage.codec import ini, shell
from gest.core.portage.write import ConfigWrite


def _section(host: Binhost) -> ini.Section:
    """One INI section for a host (priority first, then uri/sig/location)."""
    entries: dict[str, str] = {}
    if host.priority:
        entries["priority"] = host.priority
    entries["sync-uri"] = host.sync_uri
    entries["verify-signature"] = "true" if host.verify_signature else "false"
    if host.location:
        entries["location"] = host.location
    return ini.Section(host.name, entries)


def write_hosts(hosts: list[Binhost], *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` for gest.conf holding exactly ``hosts``.

    An empty list renders to ``""``, which deletes the file — so removing the
    last managed host leaves no stray fragment behind.
    """
    target = path or paths.binhost_fragment()
    return ConfigWrite(target, ini.render([_section(h) for h in hosts]))


def upsert_host(hosts: list[Binhost], host: Binhost) -> list[Binhost]:
    """Return ``hosts`` with ``host`` added or replaced (matched by name)."""
    out = [h for h in hosts if h.name != host.name]
    out.append(host)
    return out


def remove_host(hosts: list[Binhost], name: str) -> list[Binhost]:
    """Return ``hosts`` without the host named ``name``."""
    return [h for h in hosts if h.name != name]


def toggle_token(value: str, token: str, enabled: bool) -> str:
    """Add or remove ``token`` from a space-separated FEATURES value."""
    tokens = value.split()
    present = token in tokens
    if enabled and not present:
        tokens.append(token)
    elif not enabled and present:
        tokens = [t for t in tokens if t != token]
    return " ".join(tokens)


def set_feature(token: str, enabled: bool, *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` toggling one FEATURES token in make.conf.

    The rest of the FEATURES value (and the whole file) is preserved.
    """
    target = path or paths.make_conf()
    try:
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    current = ""
    for var in shell.variables(text):
        if var.name == "FEATURES":
            current = var.value
    new_value = toggle_token(current, token, enabled)
    return ConfigWrite(target, shell.render(text, "FEATURES", new_value))
