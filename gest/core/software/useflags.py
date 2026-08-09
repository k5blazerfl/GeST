"""Per-package USE-flag model and the /etc/portage/package.use/gest file.

GeST manages one file, ``package.use/gest``, holding explicit per-package flag
pins. Each flag is tri-state:

    default — inherit the profile/ebuild default (no token written)
    on      — force enabled  (token ``flag``)
    off     — force disabled (token ``-flag``)

Reads happen as the user; the file is *written* by the privileged Portage
backend via ``WriteConfig`` (polkit action ``org.gentoo.gest.portage.configure``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import portage

from gest.core.portage.codec import atomfile
from gest.core.portage.write import ConfigWrite
from gest.core.software import reader, usedesc

DEFAULT, ON, OFF = "default", "on", "off"


def package_use_dir() -> str:
    return os.path.join(
        portage.settings["PORTAGE_CONFIGROOT"], "etc", "portage", "package.use"
    )


def gest_file() -> str:
    return os.path.join(package_use_dir(), "gest")


@dataclass(slots=True)
class FlagRow:
    """One USE flag as shown in the editor."""

    name: str
    effective: bool  # currently-applied state (best-effort)
    state: str  # DEFAULT / ON / OFF — the GeST pin
    description: str = ""


def _base_state(cp: str) -> tuple[list[str], dict[str, bool]]:
    """(flag names, effective-enabled map) for a package.

    Installed packages report the USE they were actually built with (accurate);
    for available-only packages we approximate with the ebuild's IUSE defaults.
    """
    vardb = portage.db[portage.root]["vartree"].dbapi
    portdb = portage.db[portage.root]["porttree"].dbapi

    inst = vardb.cp_list(cp)
    if inst:
        iuse_raw, use_raw = vardb.aux_get(inst[-1], ["IUSE", "USE"])
        enabled = set(use_raw.split())
        flags = sorted({t.lstrip("+-") for t in iuse_raw.split()})
        return flags, {f: f in enabled for f in flags}

    best = reader._best_available(cp)
    if not best:
        return [], {}
    (iuse_raw,) = portdb.aux_get(best, ["IUSE"])
    flags = sorted({t.lstrip("+-") for t in iuse_raw.split()})
    default_on = {t.lstrip("+-") for t in iuse_raw.split() if t.startswith("+")}
    return flags, {f: f in default_on for f in flags}


def read_overrides() -> dict[str, dict[str, bool]]:
    """Parse package.use/gest into {cp: {flag: enabled}}."""
    result: dict[str, dict[str, bool]] = {}
    try:
        with open(gest_file(), encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                cp, toks = parts[0], parts[1:]
                flags: dict[str, bool] = {}
                for tok in toks:
                    if tok.startswith("-"):
                        flags[tok[1:]] = False
                    else:
                        flags[tok] = True
                if flags:
                    result[cp] = flags
    except OSError:
        pass
    return result


def flags_for(cp: str) -> list[FlagRow]:
    """The editable flag rows for ``cp``, with any existing GeST pins applied."""
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    names, effective = _base_state(cp)
    overrides = read_overrides().get(cp, {})
    # include any pinned flag even if it's not in IUSE (rare, but honour it)
    for extra in overrides:
        if extra not in names:
            names.append(extra)
    rows: list[FlagRow] = []
    for name in sorted(set(names)):
        pin = overrides.get(name)
        state = ON if pin is True else OFF if pin is False else DEFAULT
        rows.append(
            FlagRow(
                name=name,
                effective=effective.get(name, False),
                state=state,
                description=usedesc.describe(cp, name),
            )
        )
    return rows


def build_line(cp: str, states: dict[str, str]) -> str:
    """The package.use line for ``cp`` from a {flag: state} map ("" if all default)."""
    toks = []
    for flag in sorted(states):
        st = states[flag]
        if st == ON:
            toks.append(flag)
        elif st == OFF:
            toks.append(f"-{flag}")
    return f"{cp} " + " ".join(toks) if toks else ""


def _current_file_text() -> str:
    try:
        with open(gest_file(), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def render_file(cp: str, line: str) -> str:
    """New full contents of package.use/gest with ``cp``'s line set to ``line``."""
    return atomfile.upsert(_current_file_text(), cp, line)


def preview(cp: str, states: dict[str, str]) -> tuple[str, str]:
    """(old_file_text, new_file_text) for the pending change."""
    return _current_file_text(), render_file(cp, build_line(cp, states))


def write_for(cp: str, states: dict[str, str]) -> ConfigWrite:
    """A :class:`ConfigWrite` setting ``cp``'s package.use/gest line from ``states``."""
    return ConfigWrite(gest_file(), render_file(cp, build_line(cp, states)))
