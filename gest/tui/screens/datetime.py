"""Date & time (urwid): show clock / timezone / NTP status; set clock, toggle NTP.

Reading is unprivileged. Setting the clock goes through the polkit-gated
DateTimeBackend; toggling NTP sync starts/enables the detected daemon through the
Services backend (it's an ordinary OpenRC service).
"""

from __future__ import annotations

import urwid

from gest.core.datetime import commands, reader
from gest.core.datetime.backend_client import DateTimeBackend
from gest.core.services.backend_client import ServicesBackend
from gest.tui.runtime import App, Modal, Screen


class DateTimeScreen(Screen):
    def __init__(self, app: App) -> None:
        self._info = None
        self._text = urwid.Text(" loading …")
        super().__init__(
            app, urwid.LineBox(urwid.Filler(self._text, valign="top"),
                               title="Date & Time"),
            title="Date & Time",
            footer_keys=[("s", "Set clock"), ("n", "NTP sync"),
                         ("r", "Refresh"), ("Esc", "Back")],
            help_text=(
                "View the system clock, timezone and NTP time-sync status.\n\n"
                "s   set the clock manually (writes the hardware clock too)\n"
                "n   toggle NTP sync — enables/starts (or stops) the detected\n"
                "    daemon (chrony / ntp / openntpd); install one first if none.\n"
                "r   refresh   ·   Esc   back\n\n"
                "The timezone is changed from the separate Timezone module."
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        info = await self.app.run_blocking(reader.clock_info)
        self._info = info
        if info.has_ntp:
            state = f"  ({'running' if info.ntp_running else 'stopped'}, " \
                    f"{'enabled' if info.ntp_enabled else 'disabled'})"
            ntp = f"{info.ntp_daemon}{state}"
        else:
            ntp = "none installed (emerge chrony or ntp)"
        self._text.set_text([
            ("field", " Local time : "), f"{info.local_time}\n",
            ("field", " Timezone   : "), f"{info.timezone or '—'}\n",
            ("field", " NTP sync   : "), f"{ntp}\n\n",
            ("hint", " s set clock · n toggle NTP · r refresh"),
        ])
        self.app.refresh()

    async def _set_clock(self, timestamp: str) -> None:
        backend = DateTimeBackend()
        try:
            await backend.connect()
            ok, out = await backend.set_clock(timestamp)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        await self._load()

    def _set_clock_modal(self) -> None:
        edit = urwid.Edit("Timestamp: ", reader.now_string())

        def save():
            ts = edit.edit_text.strip()
            if not commands.valid_datetime(ts):
                self.app.notify("Use the format YYYY-MM-DD HH:MM:SS.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._set_clock(ts))

        modal = Modal(
            self.app, "Set system clock",
            [urwid.Text("Format: YYYY-MM-DD HH:MM:SS"), urwid.Divider(), edit],
            [("Set", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 60))

    async def _toggle_ntp(self) -> None:
        info = self._info
        if info is None or not info.has_ntp:
            self.app.notify("No NTP daemon installed — emerge chrony or ntp first.",
                            error=True)
            return
        enable = not (info.ntp_running and info.ntp_enabled)
        daemon = info.ntp_daemon
        backend = ServicesBackend()
        try:
            await backend.connect()
            if enable:
                await backend.set_enabled(daemon, True, "default")
                ok, out = await backend.control(daemon, "start")
            else:
                ok, out = await backend.control(daemon, "stop")
                await backend.set_enabled(daemon, False, "default")
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        verb = "enabled" if enable else "disabled"
        self.app.notify(out or (f"NTP sync {verb}" if ok else "failed"), error=not ok)
        await self._load()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "r":
            self.app.run_async(self._load())
            return None
        if key == "s":
            self._set_clock_modal()
            return None
        if key == "n":
            self.app.run_async(self._toggle_ntp())
            return None
        return key
