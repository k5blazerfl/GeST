"""Date & Time module logic: pure summary + a sync bridge to the DateTime
backend (widget → core → backend). Named clock.py to avoid shadowing datetime.
"""

from __future__ import annotations

import asyncio

from gest.core.datetime.model import ClockInfo


def clock_summary(info: ClockInfo) -> list[tuple[str, str]]:
    """Display rows for the current clock state."""
    rows = [
        ("Local time", info.local_time or "—"),
        ("Timezone", info.timezone or "—"),
    ]
    if info.has_ntp:
        state = "running" if info.ntp_running else "stopped"
        if info.ntp_enabled:
            state += ", enabled at boot"
        rows.append((f"NTP ({info.ntp_daemon})", state))
    else:
        rows.append(("NTP", "not configured"))
    return rows


def set_clock(timestamp: str) -> tuple[bool, str]:
    async def run():
        from gest.core.datetime.backend_client import DateTimeBackend

        backend = await DateTimeBackend().connect()
        try:
            return await backend.set_clock(timestamp)
        finally:
            await backend.close()

    try:
        result = asyncio.run(run())
        if isinstance(result, (list, tuple)) and result:
            return (bool(result[0]), str(result[1]) if len(result) > 1 else "")
        return (True, "")
    except Exception as e:  # surface backend/D-Bus/polkit errors to the UI
        return (False, str(e))
