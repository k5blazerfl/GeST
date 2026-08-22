# Host validation — Keychain, Gangway, Drydock, Flotilla

The CI-tested cores of the Keychain + Windows-interop subsystems are all pure; the
**live paths need real hardware** (a session D-Bus + a Secret Service consumer, an
RDP host + FreeRDP, real Wine/Proton + a GPU). This checklist is the turnkey
script for validating those on a Gentoo/HeDE box.

Run top-to-bottom: Keychain first (Gangway depends on it). Each step lists the
**command** and the **expected result**; tick the box when it matches.

> **Scope honesty.** These subsystems stop at a "locked door" that this checklist
> does *not* cover (they aren't built yet): PAM/TPM auto-unlock, prompts, the Qt
> management modules, the USE/package *apply*, and running the Wine *command*
> steps of a recipe (wineboot/winetricks/wineexec) — those need real Wine, so
> they're validated live here, not in CI. Where a manual step stands in for
> un-built automation, it says so.

> **Offline first.** Everything that needs *no* Wine runtime and *no* RDP host —
> the recipe toolchain plumbing (lint/plan/materialize/export) and the Gangway
> `.rdp` round-trip / dry-run / discovery — is automated in
> [`scripts/host-validation/validate-offline.sh`](../scripts/host-validation/validate-offline.sh)
> (it runs in a throwaway `HOME`, using the sample
> [`notepad.recipe`](../scripts/host-validation/notepad.recipe)). Run it first;
> it should print `N passed, 0 failed`. Then work the live steps below.

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

### 2b. The `.rdp` / `rdp://` handler + ad-hoc open
```sh
gangway register-handler                             # installs the default .rdp/rdp:// handler
xdg-mime query default application/x-rdp             # -> gangway-rdp-handler.desktop
gangway open-file some.rdp                           # launch a .rdp WITHOUT saving a profile
gangway open-file rdp://<host>                       # same, from a URI
```
- [ ] After `register-handler`, **double-clicking a `.rdp` opens that file** (not a
      fixed profile) and an `rdp://` link launches the right host.
- [ ] `register-handler` writes the shared identity map
      (`~/.local/share/hede/customs/identity.json`) mapping `sdl-freerdp` /
      `freerdp` / `org.freerdp.client` → `gangway-rdp-handler`, so any RDP window
      gets a "Remote Desktop" taskbar identity. `unregister-handler` clears both.

### 2c. Import / export / discover (no live host needed for these)
```sh
gangway export work -o work.rdp        # a saved profile -> a shareable .rdp
gangway import work.rdp --name copy     # a .rdp -> a saved profile
gangway open work --dry-run             # print the sdl-freerdp argv instead of launching
gangway discover 192.168.1.0/24 --add   # scan the LAN for open-RDP hosts; save them
```
- [ ] `export` then `import` round-trips host/user/domain/quality.
- [ ] `--dry-run` prints the full `sdl-freerdp …` command (quality/redirection/NLA
      flags visible) and launches nothing.
- [ ] `discover` finds your real RDP box on the LAN and (`--add`) saves it as a
      profile named for its address; it **refuses** a range wider than `--max`.

---

## 3. Drydock — local Windows apps via Wine/Proton

Prereq (report it, then install): `drydock prereqs <barrel>` prints the atoms.
- **wine barrel:** `emerge app-emulation/wine-vanilla` (+ `ABI_X86="32"` / multilib
  for `--arch win32`); `app-emulation/dxvk`, `app-emulation/vkd3d-proton` if
  toggled; `app-arch/icoutils` for icons.
- **proton barrel:** enable the **GURU** overlay, `emerge games-util/umu-launcher`.
- **game mode:** `gui-wm/gamescope`, `games-util/gamemode`,
  `games-util/mangohud[mangoapp]`.

> **What's unlocked now:** the recipe toolchain (§3c) **does** create prefixes and
> run a recipe's filesystem steps (extract/move/copy/chmodx/write). The **Wine
> command** steps (`create_prefix`→`wineboot`, `winetricks`, `wineexec`) run
> through the real host — validated live here, not in CI. Still locked: running
> arbitrary GUI installers unattended, and the USE/package *apply*.

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

### 3c. The recipe toolchain (zero-download, real Wine)
Uses the bundled [`notepad.recipe`](../scripts/host-validation/notepad.recipe) —
it creates a fresh prefix and exposes Wine's built-in Notepad, so no downloads.
```sh
R=scripts/host-validation/notepad.recipe
drydock lint "$R"                                    # -> ok, no issues
drydock plan "$R"                                    # dry run: shows `wineboot -i`
drydock install "$R" --run                           # REAL: creates the WINEPREFIX
ls ~/.local/share/hede/drydock/notepad-test/prefix/drive_c/windows   # prefix exists
drydock materialize "$R"                             # recipe -> a managed barrel
drydock run notepad-test notepad                     # launches Wine Notepad (a window!)
drydock export-recipe notepad-test -o /tmp/out.recipe   # barrel -> recipe (round-trip)
```
- [ ] `install --run` runs `wineboot -i` and a real `WINEPREFIX` appears; the
      summary reports the create_prefix op `ok` (a `write`/`extract`-bearing recipe
      also lands those files).
- [ ] `install --run` **refuses** a recipe with lint errors unless `--no-lint`.
- [ ] `drydock run notepad-test notepad` opens a **Notepad window** — proving the
      env+argv launch pipeline end-to-end.
- [ ] `materialize` then `drydock list`/`show` shows the barrel + program, with the
      Customs launcher + identity wired (per §4).
- [ ] **One-shot (seam closed):** `drydock install-recipe "$R" --run` does
      materialize + install against the **barrel's own prefix** in one command, so
      `install` and later `drydock run` share one `WINEPREFIX`. (The standalone
      `install`/`materialize` still compute prefixes separately — prefer
      `install-recipe`.)
- [ ] **Proton path (needs `games-util/umu-launcher`, GURU overlay):** a recipe
      whose `barrel.runner: proton` now plans its command steps through
      `umu-run` — `drydock plan` shows `umu-run createprefix`,
      `umu-run <installer.exe>`, `umu-run winetricks …`, `umu-run regedit …`
      (env `GAMEID=umu-0 STORE=none WINEPREFIX=… [PROTONPATH=<runner_version>]`),
      not the old `manual: Proton install not yet planned`. `install --run`
      against a Proton barrel then drives umu for real. *(The argv/env are
      CI-tested; the live umu forwarding of built-ins is what this step confirms.)*
- [ ] **Registry / execute / eject steps** now plan to real commands (were
      `manual`): `regedit`→`wine reg add …`, `regdelete`→`wine reg delete …`,
      `execute`→`wine <exe>` (or a native command), `eject_disc`→`eject` — visible
      in `drydock plan`. A Lutris import that used `set_regedit` /
      `delete_registry_key` / `execute` / `eject_disc` now materializes with **0
      manual steps** for those.

---

## 4. Cross-cutting — Customs desktop integration

- [ ] Both `gangway install` and `drydock register` land entries in
      `~/.local/share/applications/` that `helm-menu` shows immediately (or after
      `update-desktop-database`).
- [ ] Double-clicking a `.rdp` file opens Gangway (via `register-handler`, §2b); a
      `.exe` offers Drydock (`drydock register` sets the MIME default).
- [ ] **Shared identity map** — `~/.local/share/hede/customs/identity.json` is
      written by *both* subsystems (Drydock per program's WM_CLASS, Gangway the
      FreeRDP classes → the handler). The taskbar resolves foreign windows through
      it instead of showing a raw `wine`/`freerdp` blob.
- [ ] Drydock launchers get a **real icon** — `drydock register` runs
      `wrestool`+`icotool` to drop `~/.local/share/icons/hicolor/48x48/apps/drydock-*.png`.
- [ ] `rm` cleans up: `gangway rm` / `drydock rm` (and `unregister-handler`) remove
      the profile/barrel, their `.desktop` launchers, **and** their identity-map
      entries.

---

## 5. Flotilla — VMs (vessels) over libvirt/QEMU

Prereq: `flotilla prereqs <vessel>` prints the atoms — `app-emulation/{qemu,libvirt}`,
`sys-firmware/edk2-ovmf` (UEFI), `app-crypt/swtpm` (TPM/Win11), `app-emulation/
virt-viewer`. Enable + start **`libvirtd`** and add your user to the **`libvirt`**
+ **`kvm`** groups. Uses `qemu:///session` by default.

### 5a. Turnkey Linux vessel
```sh
flotilla images                                      # the media catalog
flotilla launch debian --os linux --iso debian       # fetch → allocate → define → boot → console
```
- [ ] The ISO is fetched to `~/.cache/flotilla/images/`, a `disk.qcow2` is
      allocated, `virsh define` registers it, `virsh start` boots it, and
      **virt-viewer opens the installer console**.
- [ ] `flotilla list`/`show` reflect the vessel; `flotilla stop`/`start` work;
      `flotilla xml debian` matches what libvirt defined (`virsh dumpxml`).

### 5b. Windows vessel + the Gangway bridge (the flagship)
```sh
flotilla fetch win11                                 # via mido (Microsoft ISO)
flotilla launch win11 --os windows --iso ~/.cache/flotilla/images/Win11*.iso
#   → UEFI + Secure Boot + TPM 2.0 + virtio-win auto-attached; install Windows,
#     enable Remote Desktop in the guest (manual until unattend.xml automation)
flotilla address win11                               # the guest IP (needs the guest agent)
flotilla connect win11 --rdp                         # provisions a Gangway profile → seamless RDP
```
- [ ] The guest boots the Windows installer with virtio storage visible (virtio-win).
- [ ] `flotilla address` returns the guest IP (qemu-guest-agent installed).
- [ ] `flotilla connect --rdp` creates a Gangway profile at that IP and opens
      **FreeRDP** — clipboard/drive/audio redirection, a real taskbar identity —
      i.e. the **local VM is as seamless as a remote box**.
- [ ] `flotilla connect --console` still opens the SPICE console (both modes are
      first-class).

---

## 6. Not expected yet (don't file these as failures)

- Auto-unlock at login (PAM) and TPM2-sealed unlock — **Keychain Phase 4/5**.
- Secret Service **prompts** and per-object locking — the daemon runs unlocked.
- Qt management modules for any subsystem — **gated on the Qt frontend**.
- Drydock **unattended GUI installers** and the **USE/package apply** — not yet
  built (prefix creation + filesystem install steps now *are*, via §3c).
- Gangway **seamless RemoteApp** (single-window RAIL) and **per-profile** taskbar
  identity — **Phase 5** (see the Gangway Phase-5 scope design doc), experimental
  and upstream-gated. The RAIL engine (5b) is gated on a host-validation spike:
  run [`scripts/host-validation/rail-spike.py`](../scripts/host-validation/rail-spike.py)
  against a provisioned vessel (protocol +
  findings: [`docs/design/gangway-phase5b-rail-spike.md`](design/gangway-phase5b-rail-spike.md);
  pin FreeRDP ≥ 3.24.0). GREEN unlocks the engine; the 5a taskbar identity spine
  ships regardless.
- Flotilla **Customs launchers/jump-lists** for vessels and the **Qt module** —
  later Flotilla phases. (Guest-side RDP-enable automation — `autounattend.xml` +
  RemoteApp `TSAppAllowList` — is now built: `flotilla … --provision/--remote-app`,
  the prerequisite target the RAIL spike above measures against.)
