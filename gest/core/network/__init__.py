"""Network module core (frontend-agnostic).

Reads interface state from ``ip`` (universal, regardless of netifrc /
NetworkManager); the privileged backend brings links up/down via ``ip link``.
Pure and dependency-free, so it is unit-testable on CI.
"""
