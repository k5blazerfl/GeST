"""Date & time module core.

Shows the system clock, timezone, and NTP time-sync status, and lets the user
set the clock manually or enable an NTP daemon. Reading is unprivileged; setting
the clock runs through the polkit-gated backend, while enabling the NTP daemon
reuses the Services backend (it's just an OpenRC service). Timezone display is
reused from [[system-timezone]] (`gest.core.system.timezone`).
"""
