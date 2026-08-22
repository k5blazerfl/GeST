# Design: Flotilla — a VM manager for HeDE (with Gangway-seamless Windows)

*Status: vision · Scope: a Helm/HeDE virtual-machine manager over libvirt/QEMU/KVM for **Windows, Linux, and general** guests — with first-class **Gangway** integration so a local Windows VM feels as seamless as a remote Windows box · Depends on: libvirt/QEMU/KVM, [Gangway](hede-windows-interop.md#3-gangway--remote-windows-over-rdp) (RDP client), [Customs](hede-windows-interop.md#2-customs--the-shared-foreign-app-integration-layer) (launchers/identity), the GeST software/USE core (Gentoo-native prereqs), the Qt frontend (gated, for the management module) · Defers: cloud orchestration, clustering/live-migration, a hypervisor of our own · Milestone: after Gangway v1 + the Qt frontend*

> **This is the hypervisor story Gangway deliberately punted.** The Gangway
> Phase-5 scope says *"No hypervisor / VM path — Gangway is a client."* Flotilla
> **is** that path: it runs the VMs; Gangway becomes its RDP client for the
> Windows ones. Drydock (Wine, no VM) and Flotilla+Gangway (a full Windows VM,
> seamless over RDP) are the two answers to *"I need Windows"* — light vs. heavy.

## 0. Thesis

**A virtual machine on your own box should be a first-class HeDE citizen — a
named vessel you start from `helm-menu`, run the traditional way in a console
window, and (for Windows) *optionally* light up as a seamless native-feeling app
via Gangway.** Flotilla is a *manager + a launch pipeline + the Customs/Gangway
integration + the Gentoo-native prerequisite automation* over the virtualization
stack that already exists (libvirt/QEMU/KVM) — the same wager Drydock and Gangway
make.

**Two first-class modes, the user's choice.** Every vessel runs the traditional
way — a SPICE/VNC console window, like virt-manager or Boxes. For **Windows**
vessels that's fully supported *and* joined by an opt-in **seamless RDP** mode via
Gangway (§5). Seamless is a target enhancement layered on top; it never replaces
the console. The user picks the default entry per vessel and always has both.

## 1. The wager

> A desktop VM manager is not a hypervisor project. It is **(a)** a *vessel*
> model over a libvirt domain, **(b)** a *pure* definition pipeline that compiles
> a vessel to domain XML + a launch/console plan, **(c)** the Customs integration
> that puts vessels in the menu/taskbar, **(d)** the **Gangway bridge** that turns
> a Windows guest into a seamless RDP app, and **(e)** a Gentoo prerequisite
> checker that drives GeST's software/USE path. The engine — QEMU, KVM, libvirt,
> OVMF, swtpm, virtiofs, SPICE — is all adopted.

## 2. Prior art (and what Flotilla takes)

| Tool | Strength | What Flotilla adopts |
|---|---|---|
| **virt-manager** | The reference libvirt GUI: domains, snapshots, storage, net | Use **libvirt** as the engine; don't reinvent domain management |
| **GNOME Boxes** | Dead-simple "download an ISO → running VM" UX; express installs | The turnkey new-vessel flow (fetch ISO / image → sane defaults → boot) |
| **Cockpit-machines** | Clean web management over the libvirt API | The thin-frontend-over-a-core split |
| **Proxmox / oVirt** | Serious cluster virtualization | *Nothing* — Flotilla is a single-box desktop manager, not a datacenter |

**The two things none of the desktop managers do — Flotilla's reason to exist:**
1. **HeDE-native + Gangway-seamless** — a Windows vessel runs traditionally in a
   console *and* can opt into Gangway RDP: clipboard/drive/audio redirection, a
   real taskbar identity, per-app windows once RAIL lands. Local VM ≡ remote box,
   when you want it.
2. **Gentoo-native prerequisites** — Flotilla can *enable KVM, install
   qemu/libvirt/OVMF/swtpm/virtiofsd, start `libvirtd`, and add you to the
   `libvirt` group* through GeST's polkit'd software core. "Turn on
   virtualization" becomes one button, not a wiki page.

## 3. Foundations (the adopted engine)

- **libvirt + QEMU/KVM** — a **vessel = a libvirt domain**. Flotilla builds the
  domain XML and drives `libvirtd` over the libvirt API (system or session URI).
- **UEFI + Secure Boot + TPM 2.0** — `edk2-ovmf` (OVMF firmware) + `swtpm` give
  the UEFI/SecureBoot/TPM a **Windows 11** guest requires; BIOS/SeaBIOS for older
  guests. Firmware is per-vessel.
- **virtio everywhere** — virtio-blk/scsi, virtio-net, virtio-balloon,
  virtio-gpu; for Windows guests the **virtio-win** driver ISO is attached at
  install for performant disk/net/gpu.
- **Display/console** — **SPICE** (with `spice-vdagent` in the guest: clipboard,
  auto-resize, USB redir) or VNC, via a SPICE client; **headless** for servers.
  For Windows guests the SPICE console is a full first-class way to run the vessel;
  **Gangway RDP** is the opt-in seamless alternative (§5).
- **Shared folders** — **virtiofs** (`virtiofsd`) for Linux guests; Windows uses
  the Gangway `/drive` redirection instead.
- **Guest integration** — `qemu-guest-agent` for IP reporting, graceful
  shutdown, and (Windows) fsfreeze for consistent snapshots; libvirt **DHCP
  leases** as a fallback way to learn a guest's address.
- **Networking** — libvirt's default NAT network out of the box; bridged and
  isolated networks as options.

## 4. The vessel model

A **vessel** = a managed libvirt domain + Flotilla config, under
`$XDG_DATA_HOME/hede/flotilla/<id>/`:

- **os**: `windows | linux | other` — drives firmware/driver/integration defaults.
- **firmware**: `uefi | bios`, `secureboot: bool`, `tpm: bool` (UEFI+SB+TPM
  auto-on for `windows`/Win11).
- **cpu/memory**: vCPUs, RAM (+ optional balloon), topology.
- **disks**: `[{path, size, bus: virtio, format: qcow2, boot: bool}]`.
- **media**: install ISO + (Windows) the virtio-win ISO, detached post-install.
- **networks**: `[{mode: nat|bridge|isolated, model: virtio}]`.
- **display**: `spice | vnc | none`; **spice_agent: bool**; USB redirection —
  always present, this is the traditional console (and the only mode for non-Windows).
- **entry**: the default way `flotilla connect`/the launcher opens a Windows
  vessel — **`console` or `rdp`** (default `console`; `rdp` once the Gangway link
  is set up). The other mode is always one click away.
- **guest_agent: bool**, **shared_folders** (virtiofs, Linux).
- **gangway**: for a Windows vessel, the optional **linked Gangway profile id**
  that powers the seamless RDP entry (§5).

A vessel compiles to **domain XML** — a *pure* transform, unit-testable without a
hypervisor (the same discipline as Gangway's `commands.py` and Drydock's launch
pipeline). Applying it (define/start/snapshot) is the host-only edge.

## 5. The Gangway bridge — the seamless option

A Windows vessel supports **two first-class modes**: the **traditional console**
(SPICE/VNC — run it like any VM, always available) and — the differentiator — an
opt-in **seamless RDP** mode via Gangway. Neither is mandatory; the user's `entry`
choice (§4) decides which opens by default, and the launcher's jump-list (§7)
offers the other. Traditional operation is a fully-supported first-class path —
right for pre-RDP setup, GPU/gaming where RDP underperforms, watching the boot/
firmware, an offline guest, or simple preference. RDP is the enhancement, not a
requirement. When the user opts into it, Flotilla wires it to Gangway:

1. **At install** — attach virtio-win; optionally seed an **`unattend.xml`** (or a
   firstboot script via the guest agent) that **enables Remote Desktop**, opens
   the firewall rule, and enables NLA. (Manual "turn on RDP" stands in until this
   automation lands — flagged, not hidden.)
2. **Address discovery** — once the guest is up, learn its IP via
   `qemu-guest-agent` (or the libvirt DHCP lease) and **provision/update a Gangway
   profile** (`host = <guest-ip>`, sensible redirections on).
3. **Connect** — when the vessel's `entry` is `rdp`, `flotilla connect <vessel>`
   (and the launcher's default action) opens **Gangway**: clipboard/drive/audio
   redirection, a proper taskbar identity via [Customs], and — once Gangway Phase 5
   (RAIL) lands — per-app seamless windows. When `entry` is `console`, the same
   command opens the SPICE/VNC console instead. **Both are always one action away**
   (`flotilla console <vessel>` / `flotilla connect --rdp`, and both in the
   launcher jump-list) — the console is a full daily-use mode, not a rescue-only
   fallback.
4. **Credentials** — the guest password lives in the Keychain via Gangway's
   existing `set-password`; Flotilla never stores it.

Net: *when you want it*, a **local** Windows VM gets the exact first-class RDP
experience Gangway gives a **remote** Windows box — this is why Gangway's
redirection/quality/Customs work pays off twice. (Conceptually the same as
Hyper-V's "enhanced session," but built on FreeRDP + our stack.) And when you
don't, it's an ordinary, fully-supported VM in a console window.

## 6. Linux & general vessels (first-class, not an afterthought)

- **Console**: SPICE with `spice-vdagent` (clipboard, dynamic resize, USB redir),
  or headless for servers.
- **Shared folders**: virtiofs mounts between host and guest.
- **Guest agent**: IP/shutdown/snapshot integration.
- **No Gangway** — RDP is a Windows path; Linux guests use SPICE/console, and SSH
  is the natural remote-shell story (a future `flotilla ssh <vessel>` is a small
  add). The vessel model, snapshots, networking, Customs launchers, and the
  Gentoo-native prereqs are **identical** to Windows vessels; only the *display*
  differs.

## 7. Customs integration (shared spine)

- A vessel gets a synthesized **`.desktop`** ("Start Windows 11", "Start Debian")
  in `helm-menu`, Exec → `flotilla-open <vessel>` (boots if needed, then opens the
  vessel's chosen `entry` — console by default, or Gangway-RDP if the user set it).
- The window carries a **taskbar identity** via the same Customs `identity.json`
  Drydock and Gangway write.
- Jump-list actions (like #137/#138): "Console", "Connect (RDP)", "Force off",
  "Snapshot".

## 8. Gentoo-native prerequisites

Mirrors Drydock's `prereqs`: a checker + the software-core apply path.
- KVM (`CONFIG_KVM*` modules, `/dev/kvm` perms), `app-emulation/qemu`
  (`QEMU_SOFTMMU_TARGETS`), `app-emulation/libvirt`, `sys-firmware/edk2-ovmf`,
  `app-crypt/swtpm` (TPM), `virtiofsd`, `spice`/`virt-viewer` for the console.
- Enable + start **`libvirtd`** (systemd), add the user to the **`libvirt`** group.
- All offered/applied through GeST's polkit'd software core — the difference
  between "it works" and "chase the Gentoo virtualization wiki."

## 9. Architecture (the GeST pattern)

- **`gest/core/flotilla/`** — **pure** core: the vessel model, the domain-XML
  compiler, the launch/console plan, the Gangway-profile synthesizer, and the
  prereq table. CI-testable with **zero** libvirt.
- **Host backend** — a thin layer that talks to `libvirtd` (define/start/stop/
  snapshot/list, DHCP-lease/agent IP lookup). Host-validated, not CI, like
  Drydock's `install --run` and Gangway's live connect. Injectable so the core
  stays pure.
- **`flotilla` CLI** (`gest/tui/flotilla/`) — `create/list/show/start/stop/
  console/connect/snapshot/prereqs/rm`, each `cmd_*` returning an exit code over
  an injectable env (the house pattern).
- **Qt module** (`gest/qt/flotilla.py`, gated on the Qt frontend) — the HeDE
  Control Center surface; reuses the pure core.

## 10. Roadmap (phased)

1. **Vessel model + domain-XML compiler** — the pure core (model, XML, prereq
   table), unit-tested. No libvirt.
2. **libvirt backend** (host-validated) — define/start/stop/list/snapshot; the
   `flotilla` CLI; SPICE/VNC console launch.
3. **New-vessel flow** — ISO/image in → sane defaults (UEFI+TPM for Windows) →
   boot; virtio-win auto-attach for Windows.
4. **The Gangway bridge** — agent/lease IP discovery → auto Gangway profile →
   `flotilla connect` opens RDP; Customs launcher + identity + jump-lists.
5. **Guest-side automation** — `unattend.xml`/firstboot to enable RDP, spice
   agent, virtiofs mounts; graceful shutdown via the guest agent. *(RemoteApp
   provisioning landed: `unattend.py` + `--provision/--remote-app`; the FreeRDP
   RAIL spike that consumes this target is next.)*
6. **Gentoo prereqs apply** — the checker + the software-core path (KVM/qemu/
   libvirt/OVMF/swtpm/libvirtd/group).
7. **Qt Control Center module** — gated on the Qt frontend.
8. **Later** — bridged/isolated networks UI, disk management, snapshot trees,
   `flotilla ssh`, GPU passthrough (vfio) as an advanced escape hatch.

## 11. Non-goals

- **Not a hypervisor.** QEMU/KVM/libvirt is the engine; we never fork it.
- **Not a datacenter tool** — no clustering, HA, or live migration in v1
  (Proxmox/oVirt own that).
- **No cloud provisioning** (no Terraform/cloud-init fleets) — this is *your box*.
- **No nested-virt or GPU-passthrough promises** in the core path — advanced,
  hardware-dependent, later escape hatches.
- **We don't reimplement Gangway or a SPICE client** — we drive FreeRDP (via
  Gangway) and `virt-viewer`/a SPICE widget.

## 12. Open decisions

1. **libvirt session vs system URI.** Session (`qemu:///session`, rootless,
   per-user) is the friendlier default for a desktop; system (`qemu:///system`)
   gives bridged networking + shared storage. *Lean:* session by default, offer
   system when the user needs bridge/passthrough (routed through the polkit'd
   core).
2. **Guest-side RDP enablement.** `unattend.xml` at install vs. a guest-agent
   `exec` post-boot vs. a documented manual step. *Lean:* manual first (honest
   locked door), then `unattend.xml` for the turnkey Windows flow. **Landed
   (phase 5a-guest):** `flotilla launch --provision/--remote-app` now builds an
   `autounattend.xml` + `firstboot.ps1` provisioning ISO (`gest/core/flotilla/
   unattend.py`, pure) that boots the guest RemoteApp-ready — RDP + NLA + firewall
   + guest-tools + a login account + the TSAppAllowList allow-list. Host-validated
   (a real Windows install must consume it), not CI-able.
3. **Vessel vocabulary.** "Vessel" for a VM (a ship in the flotilla) reads
   cleanly next to Drydock's *barrels* and Gangway's *profiles*; confirm before
   it sets in code.
