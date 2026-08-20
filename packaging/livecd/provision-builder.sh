#!/usr/bin/env bash
# provision-builder.sh — turn a freshly-installed Gentoo box into a build host
# that can build GeST installer ISOs (via run-on-builder.sh / spin-up.sh) and
# serve binary packages back to the ISO build + the installer.
#
#   sudo packaging/livecd/provision-builder.sh [--no-emerge] [--serve [--port N]]
#
# Run this ONCE on the builder, as root, from a copy of this checkout (scp/rsync
# the repo over, or let run-on-builder.sh --sync-only push it first). It is
# idempotent — re-run it any time to re-apply config. It does NOT install the
# base OS: you provision that yourself (handbook / stage3), which is why the
# builder has no GeSI dependency.
#
# What it does:
#   1. installs the build toolchain (catalyst, qemu + OVMF, git, rsync)   [--no-emerge skips]
#   2. registers the GeST overlay (this checkout) + clones the Amphitheater
#      overlay (gui-apps/hede) into /var/db/repos
#   3. mirrors this repo's livecd portage-conf into /etc/portage (namespaced,
#      non-clobbering) so the builder's binpkgs match what the ISO wants
#   4. turns on FEATURES=buildpkg so every build populates /var/cache/binpkgs
#   5. (--serve) stands up a simple HTTP binhost systemd unit over that cache
#
# The builder should match the ISO target: an amd64 *systemd* desktop profile
# (HeDE is systemd-only). This warns — it doesn't switch your profile for you.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"
gest_overlay="/var/db/repos/gest"
amphi_overlay="/var/db/repos/amphitheater"
amphi_url="https://github.com/k5blazerfl/Amphitheater"
do_emerge=1
serve=0
port="8080"

while [ $# -gt 0 ]; do
    case "$1" in
        --no-emerge) do_emerge=0; shift ;;
        --serve)     serve=1; shift ;;
        --port)      port="$2"; shift 2 ;;
        -h|--help)   grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

say()  { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*" >&2; }
die()  { echo "provision-builder: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (writes /etc/portage, /var/db/repos, emerge)."

# --- sanity: is this a Gentoo amd64 systemd box? ----------------------------
[ -f /etc/gentoo-release ] || warn "no /etc/gentoo-release — this doesn't look like Gentoo."
case "$(uname -m)" in x86_64) ;; *) warn "arch $(uname -m) is not x86_64 — the amd64 ISO build expects x86_64." ;; esac
if [ -d /run/systemd/system ]; then
    :
else
    warn "systemd not booted here — HeDE is systemd-only; build the box on a systemd profile."
fi
prof="$(readlink -f /etc/portage/make.profile 2>/dev/null || true)"
case "${prof}" in
    *desktop/systemd*) say "profile looks right: ${prof##*/profiles/}" ;;
    *) warn "profile '${prof##*/profiles/}' is not a desktop/systemd profile — binpkgs may not match the ISO. Set: eselect profile set default/linux/amd64/23.0/desktop/systemd" ;;
esac

# --- 1. build toolchain -----------------------------------------------------
if [ "${do_emerge}" = 1 ]; then
    say "Installing the build toolchain (catalyst, qemu, OVMF, git, rsync)"
    emerge --noreplace --verbose \
        dev-util/catalyst app-emulation/qemu sys-firmware/edk2-ovmf \
        dev-vcs/git net-misc/rsync \
        || die "toolchain emerge failed — resolve it and re-run (or use --no-emerge)"
else
    say "Skipping toolchain emerge (--no-emerge)"
fi
command -v catalyst >/dev/null || warn "catalyst not on PATH — install dev-util/catalyst before building."

# --- 2. overlays ------------------------------------------------------------
register_repo() {  # name location [masters]
    local name="$1" loc="$2" masters="${3:-gentoo}"
    mkdir -p /etc/portage/repos.conf
    cat > "/etc/portage/repos.conf/${name}.conf" <<REPO
[${name}]
location = ${loc}
masters = ${masters}
auto-sync = no
REPO
}

say "Registering the GeST overlay → ${gest_overlay}"
mkdir -p "${gest_overlay}"
rsync -a --delete "${repo_root}/packaging/overlay/" "${gest_overlay}/"
register_repo gest "${gest_overlay}"

say "Setting up the Amphitheater overlay (gui-apps/hede) → ${amphi_overlay}"
if [ -d "${amphi_overlay}/.git" ]; then
    git -C "${amphi_overlay}" pull --ff-only || warn "could not update ${amphi_overlay} — using the existing checkout."
elif command -v git >/dev/null; then
    git clone --depth 1 "${amphi_url}" "${amphi_overlay}" \
        || warn "could not clone ${amphi_url} — clone it manually to ${amphi_overlay} (gui-apps/hede must resolve)."
else
    warn "git missing — cannot fetch Amphitheater; clone ${amphi_url} to ${amphi_overlay} yourself."
fi
[ -d "${amphi_overlay}" ] && register_repo amphitheater "${amphi_overlay}"

# --- 3. matched portage config (namespaced, non-clobbering) -----------------
say "Mirroring livecd portage-conf into /etc/portage (so binpkgs match the ISO)"
for kind in package.use package.accept_keywords package.license; do
    src="${here}/portage-conf/${kind}"
    [ -f "${src}" ] || continue
    # Use the directory form so we drop a single owned file instead of clobbering
    # the host's own (possibly file-form) config.
    if [ -f "/etc/portage/${kind}" ] && [ ! -d "/etc/portage/${kind}" ]; then
        warn "/etc/portage/${kind} is a file; leaving it. Merge these lines yourself:"
        sed 's/^/    /' "${src}" >&2
        continue
    fi
    mkdir -p "/etc/portage/${kind}"
    install -m 0644 "${src}" "/etc/portage/${kind}/gest-livecd"
    echo "  wrote /etc/portage/${kind}/gest-livecd"
done

# --- 4. binpkg cache --------------------------------------------------------
mkconf="/etc/portage/make.conf"
if [ -f "${mkconf}" ] && grep -q '# gest-builder: buildpkg' "${mkconf}"; then
    say "FEATURES=buildpkg already enabled in ${mkconf}"
else
    say "Enabling FEATURES=buildpkg (every build fills /var/cache/binpkgs)"
    { echo ''
      echo '# gest-builder: buildpkg — populate a binary package cache for every build'
      echo 'FEATURES="${FEATURES} buildpkg"'
    } >> "${mkconf}"
fi
mkdir -p /var/cache/binpkgs

# --- 5. optional HTTP binhost -----------------------------------------------
if [ "${serve}" = 1 ]; then
    command -v python3 >/dev/null || die "--serve needs python3"
    unit="/etc/systemd/system/gest-binhost.service"
    say "Installing binhost HTTP service on :${port} (serving /var/cache/binpkgs)"
    cat > "${unit}" <<UNIT
[Unit]
Description=GeST binary package host (Portage binhost)
After=network.target

[Service]
ExecStart=/usr/bin/python3 -m http.server ${port} --directory /var/cache/binpkgs
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now gest-binhost.service \
        || warn "could not start gest-binhost.service — check 'systemctl status gest-binhost'."
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo
    echo "  Binhost live. On the ISO build + installed clients set:"
    echo "    PORTAGE_BINHOST=\"http://${ip:-<builder-ip>}:${port}\""
else
    echo
    echo "(binpkgs will accumulate in /var/cache/binpkgs; re-run with --serve to expose them over HTTP.)"
fi

# --- done -------------------------------------------------------------------
sd="$(sed -nE 's/^[[:space:]]*storedir[[:space:]]*=[[:space:]]*"?([^"#]+)"?.*/\1/p' \
      /etc/catalyst/catalyst.conf 2>/dev/null | tr -d '[:space:]' | head -1)"
say "Builder provisioned."
echo "  catalyst storedir: ${sd:-<set one in /etc/catalyst/catalyst.conf>}"
echo "  GeST overlay:      ${gest_overlay}"
echo "  HeDE overlay:      ${amphi_overlay}"
echo
echo "From your DEV box, kick off a build with:"
echo "    packaging/livecd/run-on-builder.sh --builder $(id -un)@$(hostname -f 2>/dev/null || hostname) --boot"
