"""Read systemd service state as the invoking user (no mutations).

Combines two read-only listings and, per service, one ``systemctl show``:
  systemctl list-unit-files --type=service   → install state (enabled/disabled/…)
  systemctl list-units --type=service --all  → runtime state (active/inactive/…)
  systemctl show <name>                       → description + dependency metadata

All of these query the system manager read-only and need no privilege; mutations
(start/stop/enable/mask) go through the polkit root backend.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.services.model import Service, ServiceDetail

Runner = Callable[[list[str]], str]

_LIST_UNIT_FILES = ["systemctl", "list-unit-files", "--type=service",
                    "--no-legend", "--no-pager", "--plain"]
_LIST_UNITS = ["systemctl", "list-units", "--type=service", "--all",
               "--no-legend", "--no-pager", "--plain"]
# Properties pulled in one `systemctl show` for the detail view.
_SHOW_PROPS = ("Description", "Requires", "Wants", "After", "RequiredBy",
               "WantedBy", "ActiveState", "SubState", "UnitFileState", "LoadState")


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def _words(text: str) -> list[str]:
    """Split systemd space-separated unit lists into a sorted, de-duped list."""
    return sorted({w for w in text.split() if w})


def parse_unit_files(text: str) -> dict[str, str]:
    """Parse `systemctl list-unit-files`: ``unit  state  [preset]`` lines.

    Template unit files (``foo@.service``) are skipped — they cannot be started
    or shown directly; their concrete instances appear via ``list-units``.
    """
    files: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, state = parts[0], parts[1]
        if name.endswith("@.service"):
            continue
        files[name] = state
    return files


def parse_units(text: str) -> dict[str, tuple[str, str, str]]:
    """Parse `systemctl list-units`: ``UNIT LOAD ACTIVE SUB DESCRIPTION…`` lines.

    Returns ``{name: (active_state, sub_state, description)}``. A leading status
    bullet (``●``) is stripped so failed units parse like the rest.
    """
    units: dict[str, tuple[str, str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line[:1] in ("●", "*"):
            line = line[1:].strip()
        parts = line.split()
        if len(parts) < 4:
            continue
        name, _load, active, sub = parts[0], parts[1], parts[2], parts[3]
        description = " ".join(parts[4:])
        units[name] = (active, sub, description)
    return units


def list_services(runner: Runner | None = None) -> list[Service]:
    run = runner or _default_runner
    files = parse_unit_files(run(_LIST_UNIT_FILES))
    units = parse_units(run(_LIST_UNITS))
    services = []
    for name in sorted(set(files) | set(units)):
        active, sub, desc = units.get(name, ("inactive", "", ""))
        services.append(Service(
            name=name,
            status=active,
            sub_state=sub,
            enabled_state=files.get(name, ""),
            description=desc,
        ))
    return services


def parse_show(text: str) -> dict[str, str]:
    """Parse `systemctl show` ``Key=value`` lines into a dict."""
    props: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key.strip()] = value
    return props


def describe_service(
    name: str,
    runner: Runner | None = None,
    *,
    status: str = "inactive",
    sub_state: str = "",
    enabled_state: str = "disabled",
) -> ServiceDetail:
    """Introspect one service via a single read-only ``systemctl show``.

    ``status``/``sub_state``/``enabled_state`` are passed through from an
    already-loaded Service as fallbacks; ``systemctl show`` re-reports them so
    the returned detail is authoritative when the call succeeds.
    """
    run = runner or _default_runner
    argv = ["systemctl", "show", name, "--no-pager",
            "-p", ",".join(_SHOW_PROPS)]
    props = parse_show(run(argv))
    required_by = _words(props.get("RequiredBy", "") + " " + props.get("WantedBy", ""))
    return ServiceDetail(
        name=name,
        description=props.get("Description", "").strip(),
        requires=_words(props.get("Requires", "")),
        wants=_words(props.get("Wants", "")),
        after=_words(props.get("After", "")),
        required_by=required_by,
        status=props.get("ActiveState", "").strip() or status,
        sub_state=props.get("SubState", "").strip() or sub_state,
        enabled_state=props.get("UnitFileState", "").strip() or enabled_state,
        load_state=props.get("LoadState", "").strip(),
    )
