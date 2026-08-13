"""Wi-Fi module core (wpa_supplicant).

Complements the wired-only netifrc module: manages the ``network={…}`` blocks in
``/etc/wpa_supplicant/wpa_supplicant.conf`` — add a network (SSID + passphrase,
or open), remove one, and list what's configured. The passphrase is hashed by
``wpa_passphrase`` in the backend and the plaintext ``#psk`` comment is stripped,
so the raw passphrase is never written. A scan (via ``iw``) surfaces nearby SSIDs.

Block parsing, validation and rendering are pure and CI-testable; the polkit-
gated backend does the privileged write (the file is root-only, 0600) and the
scan. Associating with a network is left to netifrc/wpa_supplicant, exactly as
the wired module leaves DHCP to netifrc.
"""
