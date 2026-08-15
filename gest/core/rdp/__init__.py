"""Gangway — remote Windows over RDP (docs/design/hede-windows-interop.md §3).

The GeST/core (Python) side of the RDP module: connection **profiles**, ``.rdp``
file interop, and the ``sdl-freerdp`` launch-command builder. Credentials live in
the Keychain (this module only computes the lookup attributes); the launcher
entry is synthesized via :mod:`gest.core.customs`.

All pure/CI-testable. Actually launching a session against a real RDP host — like
the keyring daemon needing a real bus — is validated on a host, not in CI.
Privilege note: launching a client and editing profiles is a *user* action, so
Gangway needs no polkit (unlike the system-config modules).
"""
