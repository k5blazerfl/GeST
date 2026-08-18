# Desktop provisioning — installing HeDE onto the target

How the installer turns a base-Gentoo target into a **HeDE** system: making
`gui-apps/hede` resolvable in the target *and* installing it (plus the whole
desktop stack) without recompiling on the user's machine.

This is the prerequisite that lets `InstallSelections.install_desktop` default
on — and, with it, seamless boot (whose Plymouth/theme deps come from the
desktop). See `installer.md` for the step registry and `installer-flow-engine.md`
for how steps run (host vs. chroot).

## The problem is two independent gaps

`InstallDesktop` runs `emerge gui-apps/hede` in the target chroot. That fails
twice:

1. **Resolution** — the target has no overlay carrying `gui-apps/hede`, so
   Portage can't find the atom. `PrepareChroot` binds only proc/sys/dev/run;
   `SyncTree` syncs only the gentoo tree; nothing writes the target's
   `repos.conf`.
2. **Build cost** — even resolved, `hede`'s `RDEPEND` is the *whole desktop*
   (labwc, foot, gest, lxqt-policykit, wireplumber, swaylock, swayidle, with
   qtbase/llvm underneath). Compiling that in the target is **hours**.

Both must be solved.

## Grounded facts

- **Amphitheater** (`github.com/k5blazerfl/Amphitheater`, `sync-type=git`,
  ~1.2 MB) is the published overlay and carries everything the desktop needs:
  `app-admin/gest`, `gui-apps/hede`, `gui-apps/hiedi`, `media-sound/pyrrha`.
  One overlay covers it all. It tracks the *released* line (lags `main`; the
  amphi CI syncs it on release tags).
- The **GeSI live session already has** `/var/db/repos/amphitheater` +
  `repos.conf` baked in (catalyst's `repos:` directive), and the **desktop is
  installed** in the squashfs — the running image *is* a HeDE system. So the
  provisioning source is the live system itself.
- `hede`'s `RDEPEND` pulls `app-admin/gest`, so emerging `hede` drags in gest +
  the full stack.

## Axis A — ebuild resolution (cheap)

| Option | How | Trade |
| --- | --- | --- |
| A1. Git `repos.conf` | Write `[amphitheater]` (git sync-uri) into the target; `emerge --sync amphitheater` in the chroot | Persistent + updatable; but needs install-time network and pulls amphitheater's published versions |
| **A2. Seed-copy + git `repos.conf`** ✅ | Copy the in-image overlay into the target **and** write the git-backed `repos.conf` | Offline for the install; installed system keeps a real, syncable overlay for day-2 `hede`/`gest` updates; 1.2 MB |

**Chosen: A2.**

## Axis B — build avoidance (the expensive one)

| Option | How | Trade |
| --- | --- | --- |
| B1. Compile in target | plain `emerge` | Hours + full toolchain — rejected |
| **B2. Network binhost** | `PORTAGE_BINHOST` → prebuilt HeDE binpkgs | Smallest images, best at scale — but needs hosting infra + install-time network + version sync. **Future**, not now. |
| B3. Ship binpkgs in the ISO | Bundle the desktop subset of catalyst's pkgcache; `emerge --usepkgonly` | Self-contained, deterministic; but grows the ISO by the desktop binpkg set |
| **B4. `quickpkg` the live env** ✅ | The live CD *is* a HeDE system — `quickpkg @installed` into the target's pkgdir, then `emerge --usepkgonly` | No extra ISO size (reuses already-installed files); offline; no recompile; installs the exact versions you're looking at |

**Chosen: B4 for now.** B2 (a real binhost) is worth building later — it makes
installs and updates cheapest at scale — but it's infra we don't need yet. B4 is
philosophically clean: "install" = repackage the running desktop onto disk.

## The chosen shape (A2 + B4)

Three additions to the step registry, all gated on `plan.desktop`, in the
BASE_SYSTEM phase between `@world` and the kernel/boot phase (so plymouth + the
HeDE theme exist before a seamless build bakes the splash / stages the GRUB
theme):

1. **ProvisionDesktop** (host-side): 
   - `PKGDIR=<root>/var/cache/binpkgs quickpkg --include-config=y @installed` —
     repackages every installed package on the live env into binpkgs *inside the
     target's pkgdir*. `@installed` guarantees the full `hede` closure is present
     as binaries, so nothing compiles.
   - Seed the overlay: `cp -a /var/db/repos/amphitheater <root>/var/db/repos/…`
     and write `<root>/etc/portage/repos.conf/amphitheater.conf` (git sync-uri,
     `auto-sync = no` — the installed system updates on the user's terms).
2. **InstallDesktop** (chroot): `emerge --usepkgonly gui-apps/hede
   sys-boot/plymouth` — binary-only, so it's offline, fast, and needs no ebuild
   tree at install time. Recorded in `@world`.
3. **CleanupDesktopBinpkgs** (host): remove the target pkgdir afterward, so the
   transient `@installed` binpkgs don't bloat the finished install.

`emerge --usepkgonly` only pulls the desktop delta the target lacks (the base is
already installed by `@world`); the rest of the quickpkg'd binpkgs are unused and
cleaned in step 3.

### Version currency

B4 installs the **live image's** versions (we pin those at ISO build time). A1's
git-sync would instead track amphitheater's published line. Seeding (A2) keeps
the installed system matching the ISO, diverging only when the user chooses to
`emerge --sync`.

## quickpkg's one sharp edge: non-idempotent `pkg_preinst` (bug #10)

`quickpkg @installed` repackages a package's **installed** files — i.e. its state
*after* `pkg_preinst` already ran once. Most ebuilds don't care, but a few juggle
their own image across `src_install`/`pkg_preinst`, and those break on re-merge.
The archetype is `x11-misc/xkeyboard-config` (upstream bug #957712):

```
src_install():  mv "${ED}"/usr/share/X11/xkb{,.workaround}   # image ends: xkb.workaround
pkg_preinst():  mv "${ED}"/usr/share/X11/xkb{.workaround,}   # renamed back at merge
```

The installed files are `xkb`; a **real `--buildpkg` binpkg's image is
`xkb.workaround`**. quickpkg captures `xkb`, so on re-merge `pkg_preinst` can't find
`xkb.workaround` → `die`. (Found the hard way at package 5/198 of the first install
whose `--usepkgonly` step actually ran.)

**Fix — ship the real binpkg for exactly these packages.** catalyst's stage1 build
already produces correct, source-built binpkgs in its pkgcache (their images are
pre-`pkg_preinst`). `packaging/livecd/build.sh` **auto-detects** the hostile set —
any installed ebuild whose `pkg_preinst`/`pkg_postinst`/`pkg_setup` does an `mv` of
an `${ED}`/`${D}` path — and stages those binpkgs into the image under
`/var/cache/gest-binpkgs` (`desktop.BINPKG_FIXUP_DIR`) via the root overlay. Today
that's one package (~2.5 MB); the detection keeps the set correct as the closure
changes, so it's not a hand-maintained list. At install time `ProvisionDesktop`
overlays these onto the quickpkg'd PKGDIR (`desktop.binpkg_fixup_pairs` → rm+copy)
and `InstallDesktop` runs `emaint binhost --fix` to rebuild the index before
`--usepkgonly`. Deliberately narrow: the guarded `cp ${EROOT}→${ED}` cache-restores
(gtk+/glib/…) are quickpkg-safe and are **not** shipped, keeping the ISO cost tiny.

This is a scoped instance of **B2**: for the packages that need it, we ship real
binpkgs instead of quickpkg-repackaged ones. A full B2 binhost remains the eventual
win for the whole closure.

## Known costs / follow-ups

- **`quickpkg @installed` repackage time** — repackaging the whole live system
  (a few hundred packages, ~GBs) takes minutes, and transiently writes those GBs
  to the target before cleanup. Acceptable vs. hours of compile. A future
  optimization: narrow to `hede`'s dependency closure instead of `@installed`.
- **B2 binhost** — the real long-term win for install/update speed and image
  size; deferred.
- **End-to-end verification** — the argv/wiring is unit-tested, but the full
  path (quickpkg → `--usepkgonly` resolves the whole closure) must be verified by
  a QEMU install off an ISO that carries this code before we lean on it.
