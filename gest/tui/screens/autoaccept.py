"""Shared auto-accept behaviour for review screens (proposal / clean-up).

A review screen resolves a plan and then, depending on the user's accept-mode
preference, either waits for a manual F10 (``manual``), auto-applies after a
short countdown (``timer``), or applies at once (``immediate``). That policy is
identical for the install/remove proposal and for the Clean Up review, so it
lives here as a mixin rather than being copy-pasted.

A host screen mixes this in, sets ``self.app``, implements ``_auto_apply`` (the
irreversible action) and ``_auto_set_status`` (render a status markup — the
countdown line with its progress bar), then calls ``arm_auto_accept()`` once its
plan is resolved and non-empty. The countdown is flag-driven (not task
cancellation) so ``stop`` is instant and the coroutine unwinds on its own. Hosts
route keys through ``_auto_key`` and consult ``_timer_running`` in their footer.
"""

from __future__ import annotations

import asyncio
import math

from gest.core import prefs

_BAR_W = 22            # countdown progress-bar width, in cells
_SUBSTEPS = 10         # bar updates per second (smoothness)


class AutoAccept:
    _auto_action = "Applying"      # verb shown in the countdown line
    _timer_running = False

    def arm_auto_accept(self) -> None:
        """Apply the accept-mode policy now that the plan is ready."""
        mode = prefs.accept_mode()
        if mode == prefs.IMMEDIATE:
            self._auto_apply()
        elif mode == prefs.TIMER:
            self._timer_running = True
            self.app.run_async(self._auto_countdown())
        # manual: nothing — the host waits for F10/Enter

    async def _auto_countdown(self) -> None:
        total = prefs.timer_seconds()
        steps = max(total * _SUBSTEPS, 1)
        self._refresh_footer()                   # show the timer's Enter/Esc keys
        for step in range(steps):
            if not self._timer_running:
                return                           # stopped mid-count
            remaining = math.ceil(total - step / _SUBSTEPS)
            filled = round(step / steps * _BAR_W)
            self._auto_set_status([
                ("ok", f" {self._auto_action} in {remaining}s   "),
                ("ok", "█" * filled),
                ("dim", "░" * (_BAR_W - filled)),
            ])
            self.app.refresh()
            await asyncio.sleep(1 / _SUBSTEPS)
        # Re-check the flag and that we're still the top screen: a stop in the
        # final moment wins, and we never fire after the user has moved on.
        if self._timer_running and self.app._stack and self.app._stack[-1] is self:
            self._timer_running = False
            self._auto_apply()

    def _auto_key(self, key):
        """Handle a key while counting down.

        Returns ``"applied"`` (bypassed → applied now), ``"stopped"`` (countdown
        halted; the host should revert its status line/footer), or ``None`` (not
        counting down / key not ours — the host handles it normally).
        """
        if not self._timer_running:
            return None
        if key in ("enter", "f10"):
            self._timer_running = False
            self._auto_apply()
            return "applied"
        if key == "esc":
            self._timer_running = False
            return "stopped"
        return None
