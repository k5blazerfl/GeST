# Design: Keychain — GeST/HeDE as the box's Secret Service provider

*Status: vision · Scope: a secrets manager for GeST/HeDE that **is** the freedesktop Secret Service — a per-user vault + session daemon + a Control Center module — so HeDE needs no gnome-keyring or kwallet · Depends on: the GeST Qt frontend ([gated](desktop-environment.md#relationship-to-the-qt-frontend-gate)) and its module=widget+descriptor seam ([§9](desktop-environment.md#9-gest-integration--the-seam-in-detail)); the HeDE session (autostart + PAM) · Defers: the Tier-1 root/polkit system store, an ssh-agent, any cloud/sync · Milestone: its own track; the [Gangway RDP module](hede-windows-interop.md#3-gangway--remote-windows-over-rdp) is its first consumer*

> **Decision (2026-08-14).** HeDE ships **neither gnome-keyring nor kwallet** — no
> GNOME/KDE runtime dependency on a lean Gentoo desktop. The consequence is not
> "GeST has no keyring"; it is "**GeST/HeDE becomes the keyring.**" A desktop that
> refuses both incumbents must *provide* the standard interface itself, or every
> libsecret app (browsers, NetworkManager) has a keyring-shaped hole to fall into.
> So we own a vault. We do **not** own any cryptography.

## 0. The one-sentence thesis

**Keychain is the freedesktop Secret Service (`org.freedesktop.secrets`),
implemented by us, backed by a vault we own and primitives we borrow.** Every app
on a HeDE box — browsers, NetworkManager, any libsecret consumer, and Gangway —
talks to *one* keyring, and that keyring is GeST-native, Gentoo-aware, and
TPM-sealable, with no GNOME or KDE dependency dragged in behind it.

## 1. The wager

The other design docs each wagered a subsystem was really orchestration over
pieces that already exist. Keychain makes the sharper version of that bet:

> A keyring is **not** a cryptography project. It is **(a)** a small encrypted
> **vault** (a file format), **(b)** a session-bus **daemon** that implements a
> *published* D-Bus API and a *published* transport, and **(c)** a management UI.
> The crypto — AEAD, argon2id, TPM2 sealing, the DH transport — is all borrowed,
> standard, and boring. The only genuinely new owned surfaces are the vault
> format and the daemon.

The memory's first locked decision — *"don't roll your own crypto"* — survives
intact. Providing Secret Service means implementing a wire protocol and storing
bytes with standard AEAD; it never means inventing an algorithm.

## 2. The inversion this introduces

Every GeST module to date is a **client** of a root/polkit backend on the
**system** bus: `widget → core → backend (polkit)`. Keychain's user tier is the
mirror image — a **daemon that owns a name on the *session* bus and *serves*
arbitrary apps**. This is the first time `gest/core` ships a *server*, not a
caller. Two things follow, and both are fine:

- **No polkit, no root.** User secrets are per-login; root is *not* the
  custodian (root can read your disk anyway — the threat model is "another
  user / a stolen disk," not "defend against your own root"). So the user tier
  adds **no** `ipc/interface.py` names and **no** `gest/backend/` code. The
  golden rule ("core is the sole bus-speaker") holds — core just speaks the
  session bus here.
- **The Tier-1 system store is separate and deferred.** A root/polkit-gated,
  TPM-sealed store for *system* credentials (the thing Secret Service structurally
  can't serve, being per-login) is a later track that *does* add
  `KEYCHAIN_PATH/IFACE/POLKIT`. Out of scope for v1.

## 3. The three components

### 3a. `helm-keyringd` — the provider daemon *(name option: **Purser**)*

A long-running, per-user process, autostarted by the HeDE session, that:

- **Owns `org.freedesktop.secrets`** on the session bus.
- Implements the Secret Service object model: **`Service`**, **`Session`** (both
  the `plain` algorithm and the encrypted
  `dh-ietf1024-sha256-aes128-cbc-pkcs7` transport), **`Collection`** (a default
  `login` collection plus user-made ones), **`Item`**, and **`Prompt`**.
- Backs every operation onto the vault (§3b).

**Language: Python** (`dbus-next`/`jeepney` + `cryptography` + `tpm2-pytss`), to
share `gest/core`. Secret operations are infrequent, so a Python daemon is
performant enough; the one real cost is that a GC'd runtime makes *secure
wiping* of decrypted key material harder — recorded as a hardening item
(mlock/zeroing where the binding allows), not a blocker. (If profiling ever
demands it, the daemon is a replaceable seam — the vault format and the API are
the durable contracts.)

### 3b. The vault — `gest/core/keychain/vault.py`

- **At rest** under `$XDG_DATA_HOME/hede/keyring/`, AEAD-sealed
  (XChaCha20-Poly1305 or AES-GCM). A master key wraps item keys; the master key
  is unlocked by the login passphrase (**argon2id** KDF) or **TPM2-sealed** so it
  opens automatically on a trusted boot, with the passphrase as fallback.
- **Format decision (open, §7):** a **bespoke** format vs. **KDBX4** (the KeePass
  format). KDBX4 is argon2-native, well-audited, and comes with
  `keepassxc-cli`/KeePassXC for free backup and inspection — a strong pull toward
  adopting it over inventing a format. The counter-pull is that KDBX's model
  (entries/groups) isn't a perfect 1:1 with Secret Service's
  collections/items/attributes and needs a mapping layer.

### 3c. The management UI — `gest/qt/keychain.py` + `gest/tui/keychain/`

The only "normal GeST module" part, and the only part behind the frontend gate:
browse collections/items, reveal/copy a secret (with re-auth), lock/unlock,
change the passphrase, enroll/withdraw TPM sealing, and see *which apps stored
what*. Runs standalone in `gest-settings` and embeddable in HeDE per the §9 seam.

**Supporting library** — `gest/core/keychain/`:

| File | Role |
|---|---|
| `vault.py` | encrypted store + crypto (AEAD/argon2id/TPM2) |
| `service.py` | Secret Service object implementations |
| `session.py` | the `dh-ietf1024-sha256-aes128-cbc-pkcs7` transport |
| `model.py` | collection/item data types |
| `reader.py` | list collections/items for the UI |
| `manager.py` | UI-side mutations (create/delete collection, passphrase, TPM) |

Note **`manager.py`, not `backend_client.py`** — there is no root backend for the
user tier. The deferred Tier-1 store is what later adds a `backend_client.py`.

## 4. HeDE session integration (the make-or-break UX)

A keyring is only pleasant if it opens *with* your login and stays out of the way:

- **Autostart** `helm-keyringd` early in the session (before apps that want
  secrets) — a `hede/data`/session-supervisor entry.
- **PAM unlock** — a `pam_gest_keyring`-style module so the login/greeter
  passphrase auto-unlocks the vault. Without it, users get *double-prompted*
  (once to log in, once to open the keyring) and resent it. This is the single
  most important integration point; it ties into greetd and the HeDE greeter.
- **No name contention** — because HeDE ships without gnome-keyring/kwallet,
  `helm-keyringd` is the sole claimant of `org.freedesktop.secrets`. (The one
  place to be careful: GeST-as-Control-Center running on someone *else's*
  GNOME/KDE desktop must **not** silently grab the name — an explicit, reversible
  opt-in there, never a takeover.)

## 5. Threat model (state it plainly, so nothing is over-promised)

- **Protects against:** a stolen/offline disk (vault is AEAD-sealed at rest), and
  another *user* on the box (per-login, file-permission + encryption bounded).
- **Does *not* protect against:** a malicious process **in your own session**.
  D-Bus is not a security boundary between same-session processes — any process
  running as you can ask the keyring for unlocked secrets. This is **by design**
  and identical to gnome-keyring/kwallet; the Secret Service model assumes your
  session is your trust domain. We inherit that assumption; we do not claim to
  beat it.
- **Not the system-credential store.** Machine-wide secrets (needed before any
  user logs in) are the deferred Tier-1 job, sealed to TPM2 and polkit-gated.

## 6. Phased roadmap

Ordered so **Gangway unblocks early** — it needs only store + lookup, not the
whole keyring:

1. **Vault + user tier.** Encrypted store, argon2id unlock, lock/unlock. No D-Bus
   yet; pure and unit-testable.
2. **Secret Service: the store/lookup path.** `Service`/`Collection`/`Item`,
   `CreateItem`/`SearchItems`/`GetSecret` over the `plain` session. **← Gangway
   can consume from here (~40% in).** Also enough for `secret-tool` and simple
   libsecret apps.
3. **Prompts + DH transport.** The async `Prompt` flow and the
   `dh-ietf1024-sha256-aes128-cbc-pkcs7` encrypted session — needed for full
   browser/NetworkManager compatibility.
4. **HeDE session wiring.** Autostart + the `pam_gest_keyring` unlock; the
   management UI (Qt + TUI).
5. **TPM2 sealing.** Seal the master key to the TPM with passphrase fallback.
6. **(Later track) Tier-1 system store** — root/polkit, new IPC names; and an
   **ssh-agent** front for stored SSH keys.

## 7. Open decisions

1. **Vault format:** KDBX4 (audited, tooled, argon2-native — needs a
   Secret-Service↔KeePass mapping) vs. a bespoke format (1:1 with the API, but we
   own its audit surface). *Leaning KDBX4.*
2. **Daemon language:** Python (shares `core`, easy) vs. a compiled daemon
   (better secret-wiping, smaller attack surface). *Leaning Python*, with the
   daemon kept as a replaceable seam behind the format + API contracts.
3. **Names:** `helm-keyringd` / **Purser** (nautical — the officer who guards
   valuables) for the daemon; **Keychain** for the Control Center module. Not
   locked.
4. **PAM module:** ship our own `pam_gest_keyring`, or adapt an existing
   Secret-Service PAM helper. Resolve during phase 4.

## 8. Non-goals

- **No custom cryptography.** Borrow AEAD/argon2id/TPM2 and implement the
  published DH transport; invent nothing.
- **No cloud/sync/sharing.** A local vault. Sync is a later, separate question.
- **No Tier-1 system store in v1** (root/polkit/TPM machine credentials) — its
  own track.
- **No ssh-agent in v1** — a natural follow-on once the vault exists, not part of
  the first cut.
- **No silent takeover** of `org.freedesktop.secrets` on a non-HeDE desktop —
  explicit opt-in only.

## 9. Testing (when building begins)

- **Vault (pure, headless):** encrypt/decrypt round-trips, argon2id unlock,
  wrong-passphrase rejection, TPM path behind a mock — no display, no bus.
- **Secret Service impl:** against **`python-dbusmock`'s Secret Service
  template** in CI (no real keyring needed), asserting the object model,
  `SearchItems` attribute matching, `default`-collection aliasing, and the
  `Prompt` lifecycle.
- **Compatibility smoke (manual/tagged, not CI):** real `secret-tool`,
  NetworkManager wifi secrets, a browser's *save password*, and **Gangway**
  storing/fetching an RDP credential — the four consumers that prove "we are the
  keyring."
- **Privilege path:** the user tier asserts **no** polkit prompt (session-bus,
  per-user); only the deferred Tier-1 store would assert the polkit path.
