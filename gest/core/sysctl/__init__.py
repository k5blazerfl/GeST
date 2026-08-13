"""sysctl module core — kernel tunables in /etc/sysctl.d/.

Manages a single GeST-owned drop-in (``/etc/sysctl.d/10-gest.conf``) of
``key = value`` runtime parameters (``net.ipv4.ip_forward``, ``vm.swappiness``,
``kernel.*`` hardening, …). Parsing, validation and rendering are pure and
CI-testable; the polkit-gated backend writes the drop-in and loads it with
``sysctl -p`` so the values take effect immediately and persist across boots.
"""
