"""Privileged backend — the only component that runs as root.

The frontend never imports this package. It reaches these methods over the
system D-Bus bus (name ``org.gentoo.gest``), and every mutating call is gated
by polkit. See ``backend/README.md`` for installing the system data files.
"""
