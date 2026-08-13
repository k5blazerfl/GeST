"""sshd server-config module core (/etc/ssh/sshd_config).

Manages a handful of the security-relevant directives — the login port, root
login policy, password/pubkey authentication, X11 forwarding and empty passwords
— by *upserting* them into the existing sshd_config, leaving every other line
untouched. Reading and rendering the change are pure and CI-testable; the
polkit-gated backend validates the candidate file with ``sshd -t`` before it
replaces the live one and reloads the service, so a typo can never leave sshd
unable to start.

This is distinct from the deploy-key ``Ssh`` helper (client-side key for private
Portage overlays); this module is the server daemon's configuration.
"""
