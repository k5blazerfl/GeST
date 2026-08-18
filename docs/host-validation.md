# Host validation — Keychain, Gangway, Drydock

The CI-tested cores of the Keychain + Windows-interop subsystems are all pure; the
**live paths need real hardware** (a session D-Bus + a Secret Service consumer, an
RDP host + FreeRDP, real Wine/Proton + a GPU). This checklist is the turnkey
script for validating those on a Gentoo/HeDE box.

Run top-to-bottom: Keychain first (Gangway depends on it). Each step lists the
**command** and the **expected result**; tick the box when it matches.

> **Scope honesty.** These subsystems stop at a "locked door" that this checklist
> does *not* cover (they aren't built yet): PAM/TPM auto-unlock, prompts, the Qt
> management modules, Drydock prefix-creation/installer automation, and the
> USE/package *apply*. Where a manual step stands in for un-built automation, it
> says so.

---

## 0. Install & prerequisites

```sh
# GeST with the keychain extra (Argon2id + ChaCha20-Poly1305 + the DH transport)
pip install -e '.[keychain]'          # or: emerge the ebuild with USE=keychain
# runtime deps already pulled by GeST: dev-python/dbus-next
# a Secret Service *consumer* for testing:
emerge app-crypt/libsecret            # provides the `secret-tool` CLI
```

- [ ] `keychainctl --help`, `helm-keyringd --help`, `gangway --help`, `drydock --help` all run.
- [ ] **No other Secret Service provider is running** (gnome-keyring / kwallet) —
      `helm-keyringd` must be the sole owner of `org.freedesktop.secrets`:
      `busctl --user list | grep secrets` shows nothing before you start it.

---

## 1. Keychain — the Secret Service provider

### 1a. Vault (offline, no daemon)
```sh
keychainctl init                                   # prompts a passphrase (twice)
keychainctl add default "test wifi" --attr net=home   # prompts the secret
keychainctl search --attr net=home                 # prints the item id + label (no secret)
keychainctl get <item-id>                           # prints the secret bytes to stdout
keychainctl ls                                      # lists collections + items
keychainctl view                                    # read-only TUI; q to quit
```
- [ ] Vault created at `~/.local/share/hede/keyring/default.vault` (mode `0600`).
- [ ] `search`/`ls` never print the secret; `get` returns exactly what you stored.
- [ ] Wrong passphrase on a fresh `keychainctl ls` after `lock` fails cleanly.

### 1b. Isolated daemon smoke (mirrors CI, no session pollution)
Reuses the vault from §1a — pass **that same passphrase**:
```sh
GEST_KEYRING_PASSPHRASE='<your §1a passphrase>' \
  dbus-run-session -- sh -c '
    helm-keyringd & sleep 1
    printf s3cr3t | secret-tool store --label=t service demo user bob
    secret-tool lookup service demo user bob'          # must print: s3cr3t
```
- [ ] `secret-tool lookup` prints `s3cr3t` — **real libsecret round-trips through
      `helm-keyringd`** (this exercises the DH-encrypted transport, which libsecret
      prefers). If it hangs, another Secret Service owns the name (see §0).

### 1c. Live session daemon
```sh
# inside your real session bus (a HeDE/Wayland session):
GEST_KEYRING_PASSPHRASE=… helm-keyringd &            # autostart+PAM unlock = future
printf pw | secret-tool store --label='browser test' app firefox
secret-tool lookup app firefox                       # -> pw
```
- [ ] A **third-party libsecret app** (Firefox "Saved Logins", NetworkManager
      Wi-Fi password) can store & retrieve — the app finds us at
      `org.freedesktop.secrets`.
- [ ] `busctl --user tree org.freedesktop.secrets` shows the Collection/Item tree.

---

## 2. Gangway — remote Windows over RDP

Prereq: `emerge net-misc/freerdp:3` (USE `sdl client` → the `sdl-freerdp` binary),
a reachable RDP host (a Windows box, or `xrdp` on another Linux box), and
`helm-keyringd` running from §1c (Gangway stores its password there).

```sh
gangway add work --host <rdp-host> --user <user> --domain <dom> --quality lan
gangway set-password work                            # prompts; stored in the keychain
secret-tool lookup service gangway host <rdp-host>   # -> the password (proves storage)
gangway show work                                    # config; never prints the password
gangway install work                                 # writes the Customs .desktop
gangway open work                                    # launches sdl-freerdp
```
- [ ] Connects to the host and shows the Windows desktop.
- [ ] The password came from the keychain (you were **not** prompted by FreeRDP)
      — it's fed over `/from-stdin`, never on the argv (`ps aux | grep freerdp`
      shows no `/p:`).
- [ ] **Clipboard** copies both ways; **drive** redirection: `\\tsclient\HeDE`
      shows your `$HOME`; **audio** plays on the Linux side.
- [ ] `gangway install work` → **"work (RDP)" appears in `helm-menu`** with the
      Gangway icon; launching it from the menu opens the same session.
- [ ] The RDP window shows a sensible **taskbar** entry (StartupWMClass
      `sdl-freerdp`).
- [ ] `--quality wan` vs `lan` visibly changes compression/GFX.

---

## 3. Drydock — local Windows apps via Wine/Proton

Prereq (report it, then install): `drydock prereqs <barrel>` prints the atoms.
- **wine barrel:** `emerge app-emulation/wine-vanilla` (+ `ABI_X86="32"` / multilib
  for `--arch win32`); `app-emulation/dxvk`, `app-emulation/vkd3d-proton` if
  toggled; `app-arch/icoutils` for icons.
- **proton barrel:** enable the **GURU** overlay, `emerge games-util/umu-launcher`.
- **game mode:** `gui-wm/gamescope`, `games-util/gamemode`,
  `games-util/mangohud[mangoapp]`.

> **Locked door:** Drydock v1 does **not** create prefixes or run installers yet.
> Create the prefix and install the app manually, then let Drydock manage/launch it.

### 3a. Wine barrel
```sh
drydock create office --runner wine --arch win64
drydock prereqs office                               # verify the atom list looks right
# --- manual prefix setup (Drydock prefix-creation is the locked door) ---
WINEPREFIX=~/.local/share/hede/drydock/office/prefix WINEARCH=win64 wineboot -i
WINEPREFIX=~/.local/share/hede/drydock/office/prefix wine <some-installer>.exe
# --- back to Drydock ---
drydock register office \
  ~/.local/share/hede/drydock/office/prefix/drive_c/…/App.exe --name "My App"
drydock run office my-app                            # launches via `wine <exe>`
drydock scan office                                  # adopt wine's Start-menu launchers
```
- [ ] `drydock run` launches the app with `WINEPREFIX`/`WINEARCH` set correctly
      (`drydock run … &` then check the env of the wine process).
- [ ] `drydock register` → **"My App" appears in `helm-menu`**; its Exec is
      `drydock-run office my-app`; launching from the menu runs it.
- [ ] `drydock scan` **adopts** the `.desktop`s wine wrote under
      `~/.local/share/applications/wine/` — they reappear as Drydock-managed
      launchers (`drydock-office-*`).
- [ ] The running app has the right **taskbar icon/title** (StartupWMClass).

### 3b. Proton barrel + game mode
```sh
drydock create game --runner proton --version GE-Proton9-27
drydock register game <game.exe> --name "My Game" --game --gamescope --fsr --gamemode --mangohud
drydock run game my-game                             # umu-run inside gamescope
```
- [ ] Launches through `umu-run` (Proton auto-downloads if needed; protonfixes apply).
- [ ] **gamescope** hosts it (fullscreen); **FSR** upscaling works; **MangoHud**
      overlay shows via `--mangoapp` (not the env var); **gamemode** engages
      (`gamemoded -s` reports active).
- [ ] `ps` confirms the wrap order: `gamemoderun → gamescope … --mangoapp -- → umu-run → exe`.

---

## 4. Cross-cutting — Customs desktop integration

- [ ] Both `gangway install` and `drydock register` land entries in
      `~/.local/share/applications/` that `helm-menu` shows immediately (or after
      `update-desktop-database`).
- [ ] Double-clicking a `.rdp` file opens Gangway; a `.exe` offers Drydock (MIME
      handlers) — after the launchers are registered as defaults.
- [ ] `rm` cleans up: `gangway rm` / `drydock rm` remove both the profile/barrel
      **and** their `.desktop` launchers.

---

## 5. Not expected yet (don't file these as failures)

- Auto-unlock at login (PAM) and TPM2-sealed unlock — **Keychain Phase 4/5**.
- Secret Service **prompts** and per-object locking — the daemon runs unlocked.
- Qt management modules for any subsystem — **gated on the Qt frontend**.
- Drydock **prefix creation / installer automation** and the **USE/package apply**
  — host-only automation not yet built (manual steps above stand in).
- Gangway **seamless RemoteApp** (single-window RAIL) — **Gangway v2**, experimental.
