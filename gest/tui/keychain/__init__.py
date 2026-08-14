"""HeDE-facing keychain surfaces: the ``keychainctl`` CLI and a read-only TUI
viewer over :mod:`gest.core.keychain`.

These make the Phase-1 vault usable and dogfood-able by hand before the Secret
Service daemon exists. They are thin: all vault logic lives in ``gest.core``;
this package only parses arguments, prompts for a passphrase, and renders.
"""
