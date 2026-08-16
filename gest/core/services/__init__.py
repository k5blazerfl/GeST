"""Services module — manage system services.

systemd on this system (systemctl / journalctl). Reads run as the user; start /
stop / enable / disable / mask go through the privileged backend.
"""
