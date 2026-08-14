# Testing GeST's Apple Silicon (Asahi) support on a real M2

A working plan for using an installed **Asahi Gentoo** machine (e.g. an M2) to test
and harden GeST's arm64 install path. The dev box GeST is normally built on is amd64;
the M2 is a separate arm64 target you drive.

## Two things to test — keep them separate

| Mode | Risk | What it covers |
|---|---|---|
| **GeST *running on* Asahi** (day-2 admin, gestd, C++ reference) | Safe | The TUI/Qt frontends, `gestd`, the polkit backend writes, and the qdbusxml2cpp C++ path — all on real aarch64. |
| **GeST *installing* onto the M2** | Destructive | The installer pipeline. A full install onto the M2's boot disk is **off the table** (it's your working machine). Validate non-destructively (scratch target) only. |

## What we've already built (the arm64 boot path, modeled + tested on amd64)

```
Apple Silicon boot chain:   iBoot → m1n1 → U-Boot → GRUB → kernel
                                    └─ v0.51.4 ─┘   └ v0.51.3 (arm64-efi)
```

- **v0.51.3** — the installer is arch-aware. `InstallPlan.arch` flows from the chosen
  stage3 variant; `bootloader/commands.grub_target(arch, firmware)` emits `arm64-efi`
  for arm64 UEFI instead of the old hardcoded `x86_64-efi`. `stage3/model` has
  `ARM64_VARIANTS` / `variants_for(arch)`; arm64 validated as UEFI-only.
- **v0.51.4** — `core/bootloader/m1n1.py` (`update_m1n1_argv`, `default_boot_bin`) +
  the arch-gated `registry.InstallBootStub` step (writes `<ESP>/m1n1/boot.bin` on
  arm64, no-op on x86).

Both were scaffolded **conservatively** — the exact `update-m1n1` invocation and the
Asahi kernel package atoms want confirmation on real hardware. That's what step 1 does.

## Step 1 — Ground-truth the scaffolds (highest value, zero risk)

Run the read-only probe on the M2 and paste its output back:

```sh
git pull
bash packaging/livecd/asahi-probe.sh 2>&1 | tee asahi-probe.out
```

It reads (never writes) the real values GeST guessed at. Each section maps to a code
site to confirm or fix:

| Probe section | Confirms / corrects |
|---|---|
| `update-m1n1 --help` + `/etc/default/m1n1` | `core/bootloader/m1n1.py::update_m1n1_argv` — real CLI: positional path vs config-driven, and the true `boot.bin` target |
| ESP / boot payload layout | `default_boot_bin()` path convention (`<ESP>/m1n1/boot.bin`) and the ESP mount point |
| GRUB version + config | that `--target=arm64-efi` matches how GRUB is really installed on Asahi |
| Asahi packages | the exact kernel/meta atoms for the **next** increment — likely `virtual/dist-kernel:asahi`, `sys-apps/asahi-meta`, `sys-apps/asahi-scripts` (confirm names/slots) |
| kernel install style | whether Asahi uses a **distribution kernel** (emerge, no genkernel) — drives how the kernel step should branch on arm64 |

## Step 2 — Prove the code runs on aarch64

What our amd64 CI can't exercise:

```sh
pip install -e '.[dev,qt]'
pytest -q                                    # full suite incl. needs_live_system, real arm64
cmake -S examples/hede-qt -B /tmp/href && cmake --build /tmp/href   # qdbusxml2cpp / Qt6 DBus on aarch64
gest-core &                                  # gestd on real arm64 → then run examples/hede-qt/build/gest-hede-ref
```

Catches arch-specific bugs (16K pages, path/format assumptions) x86 runners miss.

## Step 3 — Make it durable: a self-hosted arm64 CI runner

Register the M2 as a GitHub Actions **self-hosted runner** (label `arm64`) and add a CI
job so every push gets real arm64 coverage:

```yaml
arm64-live:
  runs-on: [self-hosted, linux, ARM64]
  steps:
    - uses: actions/checkout@v4
    - run: pytest -m "not needs_live_system" -q
    - run: cmake -S examples/hede-qt -B build && cmake --build build
```

**Caveats:** a self-hosted runner on a personal machine has security implications —
scope it to this repo and non-fork pushes only (fork PRs must not run on it), and the
M2 must be online for CI to pass.

## Step 4 — Non-destructive install-flow test

Not onto the boot disk. Run the real installer pipeline against a **scratch target** —
a spare USB/external NVMe, or a file-backed loopback + chroot — so it exercises
partition → stage3 → … → `update-m1n1` emitting the **right arm64 commands** on real
arm64, without touching macOS or your working install. It can't test the actual Apple
boot handoff (that needs a real target), but it proves the pipeline end to end.

## What's still ahead for a *complete* Asahi install

- **The Asahi kernel step** — branch `BuildKernel` (or add an `"asahi"` method) so arm64
  emerges `virtual/dist-kernel:asahi` / `sys-apps/asahi-meta` instead of genkernel.
  (Step-1 output pins the exact atoms.)
- **Firmware extraction** from the macOS partition (`asahi-fwextract` → `/lib/firmware`).
- **Backend arch threading** — the day-2 `InstallGrub` D-Bus method is still amd64.
- **UI** — wire `variants_for(arch)` so arm64 is actually offered in the installer.

## Related

- `packaging/livecd/run-on-asahi.sh` — run GeST *on* an installed Asahi Gentoo today.
- `packaging/livecd/asahi-probe.sh` — the read-only probe used in step 1.
- `docs/design/installer-flow-engine.md` — the install step engine/registry design.
