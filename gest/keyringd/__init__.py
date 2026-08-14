"""``helm-keyringd`` — GeST/HeDE as the freedesktop Secret Service provider.

Phase 2 of the Keychain (docs/design/keychain.md): a per-user session-bus daemon
that owns ``org.freedesktop.secrets`` and serves the **store/lookup path** of the
Secret Service API over the Phase-1 :mod:`gest.core.keychain` vault. This is what
lets libsecret apps, NetworkManager, and Gangway use the keyring.

Split for testability the same way ``gest.coreservice`` is:

* :mod:`gest.keyringd.contract` — the freedesktop bus name, interface names, and
  object-path bases (constants).
* :mod:`gest.keyringd.paths` — a pure object-path codec (collection/item/session
  id ↔ D-Bus path).
* :mod:`gest.keyringd.session` — the ``plain`` session (secret transport identity;
  the DH transport is Phase 3).
* :mod:`gest.keyringd.store` — the pure adapter mapping Secret-Service operations
  onto the vault; tested against a crypto-free fake vault.
* :mod:`gest.keyringd.service` — the ``dbus_next`` ``Service``/``Collection``/
  ``Item``/``Session`` objects and the daemon entry point. This is the only module
  that imports ``dbus_next``; like ``coreservice``, the bus wiring is validated on
  a real session bus, not in the dependency-light CI job.

Deferred to later phases: prompts, the DH-encrypted transport, TPM2 sealing, and
the PAM/session auto-unlock (the daemon here unlocks at startup from a prompt or
``GEST_KEYRING_PASSPHRASE``).
"""
