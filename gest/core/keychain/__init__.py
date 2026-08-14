"""Keychain module core — GeST/HeDE as the box's secrets vault.

Per ``docs/design/keychain.md``: HeDE ships neither gnome-keyring nor kwallet, so
GeST/HeDE *becomes* the freedesktop Secret Service provider. This package is the
foundation that layer sits on — **Phase 1: the vault**.

The vault is split so the bulk is testable without any crypto dependency:

* :mod:`gest.core.keychain.model` — pure data model + on-disk *plaintext* format
  and Secret-Service-shaped CRUD/search. No cryptography; fully CI-testable.
* :mod:`gest.core.keychain.crypto` — the thin seal/unseal layer: Argon2id key
  derivation + ChaCha20-Poly1305 AEAD, via ``cryptography`` (borrowed, boring,
  standard — we own no crypto). Imported only where sealing happens.
* :mod:`gest.core.keychain.vault` — ties them together: the encrypted file, the
  unlock/lock lifecycle, and atomic persistence.

Later phases (the ``org.freedesktop.secrets`` session daemon, the DH transport,
TPM2 sealing, the Qt/TUI management module) build on this vault; none of them
are in this package yet.
"""
