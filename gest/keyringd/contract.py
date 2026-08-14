"""The freedesktop Secret Service D-Bus contract we implement.

These are *standard* names owned by the spec (not GeST's own), because the whole
point of the provider decision is that unmodified libsecret apps find us at
``org.freedesktop.secrets``. See
https://specifications.freedesktop.org/secret-service/ .
"""

from __future__ import annotations

# Well-known name we claim on the SESSION bus.
SECRETS_BUS_NAME = "org.freedesktop.secrets"

# Interfaces.
SERVICE_IFACE = "org.freedesktop.Secret.Service"
COLLECTION_IFACE = "org.freedesktop.Secret.Collection"
ITEM_IFACE = "org.freedesktop.Secret.Item"
SESSION_IFACE = "org.freedesktop.Secret.Session"
PROMPT_IFACE = "org.freedesktop.Secret.Prompt"

# Object-path bases.
SERVICE_PATH = "/org/freedesktop/secrets"
COLLECTION_BASE = "/org/freedesktop/secrets/collection"
SESSION_BASE = "/org/freedesktop/secrets/session"
ALIAS_BASE = "/org/freedesktop/secrets/aliases"

# The object path a method returns to mean "no prompt was required". Because the
# vault is unlocked at daemon startup (Phase 2), every operation returns this.
NO_PROMPT = "/"

# The only session algorithm implemented in Phase 2; the DH transport is Phase 3.
ALGO_PLAIN = "plain"
