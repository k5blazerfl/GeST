#!/usr/bin/env bash
# run-on-builder.sh — offload the catalyst ISO build to a remote Gentoo builder,
# then pull the finished ISO back to this machine for boot-testing.
#
#   packaging/livecd/run-on-builder.sh [--builder user@host] [--out DIR]
#                                      [--workdir DIR] [--snapshot ID]
#                                      [--storedir DIR] [--sync-only]
#                                      [--boot [--uefi]] [--smoke [--uefi]]
#
# Catalyst is heavy (CPU + IO); this drives it on a dedicated Gentoo build host
# instead of your laptop. It does three things over SSH:
#   1. rsyncs this checkout to the builder (→ the builder always builds latest
#      HEAD, no git push required)
#   2. runs `spin-up.sh --no-boot` on the builder (stages snapshot + stage3 seed,
#      writes config.env, runs catalyst)
#   3. rsyncs the built ISO (+ .sha256 if present) back to --out on this machine
#
# Boot-testing stays LOCAL on purpose: QEMU runs on this machine, not the
# headless builder. Two options once the ISO lands:
#   --smoke   unattended pass/fail — boot headless and assert the image reaches
#             the greeter (boot-smoke.sh). This is the gate; use it in scripts.
#   --boot    interactive — open a QEMU window (qemu-test.sh) to click through
#             the installer yourself.
# Add --uefi to either for OVMF instead of SeaBIOS.
#
# The builder is a normal Gentoo box you provisioned yourself (handbook / stage3
# — no GeSI dependency). It must have: dev-util/catalyst configured, a matching
# systemd desktop profile, this repo's portage-conf mirrored into /etc/portage,
# git + rsync, and passwordless (or interactive) sudo for the invoking user.
#
# The builder host is resolved from (highest precedence first):
#   --builder user@host   >   $BUILDER env   >   a `BUILDER=` line in config.env
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"
arch="amd64"                 # spin-up.sh is amd64-only; arm64 goes to the Asahi box
builder=""
workdir="gest-build"         # remote checkout dir (relative → ~/gest-build)
out="${HOME}/gest-isos"      # local landing dir for the pulled ISO
snapshot=""
storedir=""
sync_only=0
boot=0
smoke=0
firmware="bios"

while [ $# -gt 0 ]; do
    case "$1" in
        --builder)  builder="$2"; shift 2 ;;
        --workdir)  workdir="$2"; shift 2 ;;
        --out)      out="$2"; shift 2 ;;
        --snapshot) snapshot="$2"; shift 2 ;;
        --storedir) storedir="$2"; shift 2 ;;
        --sync-only) sync_only=1; shift ;;
        --boot)     boot=1; shift ;;
        --smoke)    smoke=1; shift ;;
        --uefi)     firmware="uefi"; shift ;;
        -h|--help)  grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

say() { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }
die() { echo "run-on-builder: $*" >&2; exit 1; }

# --- resolve the builder host -----------------------------------------------
# --builder > $BUILDER > BUILDER= in config.env (config.env is regenerated on the
# *builder* by spin-up.sh, so keep the authoritative host here, on the dev box).
if [ -z "${builder}" ]; then
    builder="${BUILDER:-}"
fi
if [ -z "${builder}" ] && [ -f "${here}/config.env" ]; then
    builder="$(sed -nE 's/^BUILDER="?([^"#]*)"?.*/\1/p' "${here}/config.env" | tr -d '[:space:]' | head -1)"
fi
[ -n "${builder}" ] || die "no builder host — pass --builder user@host, set \$BUILDER, or add a BUILDER= line to config.env"

# --- preflight (this machine) -----------------------------------------------
command -v rsync >/dev/null || die "rsync not installed on this machine"
command -v ssh   >/dev/null || die "ssh not installed on this machine"

# Keep long catalyst runs alive; -t so remote sudo can prompt if needed.
ssh_opts=(-o ServerAliveInterval=60 -o ServerAliveCountMax=10)
bssh()  { ssh    "${ssh_opts[@]}" "${builder}" "$@"; }
bssht() { ssh -t "${ssh_opts[@]}" "${builder}" "$@"; }

say "Builder: ${builder}   (remote workdir: ~/${workdir})"
bssh true || die "cannot ssh to '${builder}' — check the host/key"

# --- 1. push this checkout to the builder -----------------------------------
say "Syncing this checkout → ${builder}:~/${workdir}"
rsync -az --delete \
    --exclude '.git' --exclude '.claude' \
    --exclude 'build/' --exclude 'dist/' --exclude '*.iso' \
    --exclude '__pycache__/' --exclude '.pytest_cache/' \
    --exclude '.mypy_cache/' --exclude '.ruff_cache/' --exclude '*.qcow2' \
    -e "ssh ${ssh_opts[*]}" \
    "${repo_root}/" "${builder}:${workdir}/"

if [ "${sync_only}" = 1 ]; then
    say "Synced (--sync-only). Build it yourself with:"
    echo "  ssh ${builder} 'sudo ${workdir}/packaging/livecd/spin-up.sh --no-boot'"
    exit 0
fi

# --- 2. build on the builder (catalyst) -------------------------------------
spin_args=(--no-boot)
[ -n "${snapshot}" ] && spin_args+=(--snapshot "${snapshot}")
[ -n "${storedir}" ] && spin_args+=(--storedir "${storedir}")
say "Building on ${builder} (catalyst — this takes a while)"
bssht "sudo ${workdir}/packaging/livecd/spin-up.sh ${spin_args[*]}" \
    || die "remote build failed (see catalyst output above)"

# --- 3. locate + pull the ISO back ------------------------------------------
# Resolve the builder's catalyst storedir the same way spin-up.sh does, then
# grab the newest matching ISO path (+ its .sha256 sibling if present).
say "Locating the built ISO on ${builder}"
remote_iso="$(bssh "
    sd='${storedir}'
    if [ -z \"\$sd\" ]; then
        sd=\$(sed -nE 's/^[[:space:]]*storedir[[:space:]]*=[[:space:]]*\"?([^\"#]+)\"?.*/\1/p' \
             /etc/catalyst/catalyst.conf 2>/dev/null | tr -d '[:space:]' | head -1)
        sd=\${sd:-/var/tmp/catalyst}
    fi
    ls -t \"\$sd/builds\"/*/gest-installer-${arch}-*.iso 2>/dev/null | head -1
" | tr -d '\r')"
[ -n "${remote_iso}" ] || die "build finished but no ISO found on the builder"
say "Built: ${remote_iso}"

mkdir -p "${out}"
say "Pulling ISO → ${out}/"
rsync -az --progress -e "ssh ${ssh_opts[*]}" \
    "${builder}:${remote_iso}" "${out}/"
# Best-effort: pull the checksum sidecar too, if the builder made one.
rsync -az -e "ssh ${ssh_opts[*]}" \
    "${builder}:${remote_iso}.sha256" "${out}/" 2>/dev/null || true

local_iso="${out}/$(basename "${remote_iso}")"
say "ISO ready: ${local_iso}  ($(du -h "${local_iso}" | cut -f1))"

# --- 4. optional local boot-test --------------------------------------------
# --smoke: unattended headless pass/fail (the gate). Needs boot-smoke.sh, which
# ships alongside this script once the ISO-build-gates change has landed; degrade
# gracefully if this checkout predates it.
if [ "${smoke}" = 1 ]; then
    command -v qemu-system-x86_64 >/dev/null \
        || die "--smoke needs qemu on THIS machine (emerge app-emulation/qemu)"
    if [ -x "${here}/boot-smoke.sh" ]; then
        say "Headless boot-smoke (${firmware})"
        exec "${here}/boot-smoke.sh" "${local_iso}" "${firmware}"
    fi
    die "--smoke needs boot-smoke.sh (not in this checkout) — pull the ISO-build-gates change, or use --boot"
fi

# --boot: interactive QEMU window.
if [ "${boot}" = 1 ]; then
    command -v qemu-system-x86_64 >/dev/null \
        || die "--boot needs qemu on THIS machine (emerge app-emulation/qemu)"
    say "Booting locally in QEMU (${firmware})"
    exec "${here}/qemu-test.sh" "${local_iso}" "${firmware}"
fi
echo
if [ -x "${here}/boot-smoke.sh" ]; then
    echo "Smoke-test it locally with:  packaging/livecd/boot-smoke.sh '${local_iso}' ${firmware}"
fi
echo "Boot it locally with:  packaging/livecd/qemu-test.sh '${local_iso}' ${firmware}"
