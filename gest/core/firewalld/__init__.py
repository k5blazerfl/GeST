"""firewalld firewall module core (pure logic + unprivileged reads).

MVP scope: the default zone's permanent services and ports. Argv builders,
input validators and output parsers live here (pure, CI-testable); the
privileged apply goes through the polkit-gated Firewalld backend.
"""
