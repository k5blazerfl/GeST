"""Privilege-escalation policy module core (sudo / doas).

GeST already grants ``wheel`` membership (Users); this module writes the policy
that makes ``wheel`` mean something — a minimal, reviewable escalation rule for
whichever tool is installed:

* **sudo** — an isolated drop-in at ``/etc/sudoers.d/10-gest-wheel`` (never the
  main sudoers file), validated with ``visudo -c`` before it is installed.
* **doas** — a clearly-delimited GeST block inside ``/etc/doas.conf`` (doas has
  no drop-in dir), preserving every other rule, validated with ``doas -C``.

Rendering, parsing and block management are pure and CI-testable; the polkit-
gated backend validates each candidate with the tool's own checker before it
replaces the live file, so a bad policy can never lock the machine's admins out
of privilege escalation.
"""
