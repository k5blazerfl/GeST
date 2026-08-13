"""Firewall module core (nftables).

A small, declarative *simple firewall*: a default input policy (drop/accept), an
optional ICMP-echo (ping) allowance, and the sets of inbound TCP/UDP ports to
open. That policy renders to a complete stateful ``inet`` ruleset written to
``/etc/nftables.nft`` and loaded with ``nft -f`` — the same
plan-then-apply shape the disk module uses, so the whole surface is inspectable
and CI-testable without touching the kernel's packet filter.

The rendered file carries a machine-readable ``# gest:`` marker line encoding the
policy, so the module can read its own config back into a :class:`FirewallPolicy`
(and tell a GeST-managed ruleset from a hand-written one). Reading is
unprivileged; validating, rendering and loading the ruleset happen in the
polkit-gated backend, which re-renders from validated primitives so a client can
never inject raw nftables syntax.
"""
