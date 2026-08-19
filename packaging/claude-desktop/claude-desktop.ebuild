# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# Source-of-truth ebuild for gui-apps/claude-desktop, synced into the
# Amphitheater overlay by GeST's packaging/amphi-claude-desktop.py. The file is
# version-independent — Portage derives ${PV} from the ebuild filename and the
# sync script writes claude-desktop-<PV>.ebuild + a Manifest with that version's
# DIST — so the release ebuild is a byte-for-byte copy of this template.
#
# This repackages Anthropic's OFFICIAL Linux .deb (served from their apt repo at
# downloads.claude.ai). It is a prebuilt Electron app: the binary bundles its own
# Electron runtime and app.asar, so nothing is compiled — we map the upstream
# .deb Depends to Gentoo atoms and install the tree verbatim.

EAPI=8

inherit unpacker xdg

DESCRIPTION="Official desktop application for Claude.ai (Anthropic)"
HOMEPAGE="https://claude.ai https://www.anthropic.com"
# amd64 only for now. To add arm64: keyword ~arm64, switch SRC_URI to an
# arch-conditional ( amd64? (...) arm64? (...) ), and add the arm64 .deb DIST to
# the Manifest (amphi-claude-desktop.py --arch arm64 computes it).
SRC_URI="https://downloads.claude.ai/claude-desktop/apt/stable/pool/main/c/claude-desktop/claude-desktop_${PV}_amd64.deb"
S="${WORKDIR}"

# Proprietary Anthropic application; not redistributable, ships as a prebuilt
# binary. all-rights-reserved forces an explicit ACCEPT_LICENSE opt-in.
LICENSE="all-rights-reserved"
SLOT="0"
KEYWORDS="~amd64"
# cowork = Claude's local VM sandbox ("computer use"): pulls QEMU + OVMF so the
# bundled virtiofsd/microVM image can boot. Off by default to keep installs lean;
# the app runs fine without it (the feature simply stays unavailable).
IUSE="+suid-sandbox cowork"

# Don't mirror or redistribute the proprietary binary, and never strip it (the
# Electron binary is already stripped; re-stripping corrupts it).
RESTRICT="bindist mirror strip"

# Shared libraries the bundled Electron binary links against, mapped from the
# upstream .deb Depends. gtk+:3 transitively drags in most of the X11/GLib stack
# Chromium needs; the rest are listed explicitly because Electron dlopens them.
RDEPEND="
	x11-libs/gtk+:3
	x11-libs/libnotify
	dev-libs/nss
	x11-misc/xdg-utils
	app-accessibility/at-spi2-core
	x11-libs/libdrm
	media-libs/mesa[gbm(+)]
	x11-libs/libxcb
	x11-libs/libXtst
	sys-apps/util-linux
	app-crypt/libsecret
	media-libs/alsa-lib
	dev-libs/libayatana-appindicator
	app-misc/ca-certificates
	sys-apps/xdg-desktop-portal
	|| (
		sys-apps/xdg-desktop-portal-gtk
		gnome-extra/xdg-desktop-portal-gnome
		kde-plasma/xdg-desktop-portal-kde
	)
	cowork? (
		app-emulation/qemu[qemu_softmmu_targets_x86_64]
		sys-firmware/edk2-ovmf
	)
"

# Prebuilt payload: skip the compiled-object QA scans.
QA_PREBUILT="usr/lib/claude-desktop/*"

src_unpack() {
	# unpacker.eclass: extract the .deb's data.tar into ${WORKDIR}.
	unpack_deb "${A}"
}

src_install() {
	# The .deb already targets /usr the Gentoo way: a /usr/bin/claude-desktop
	# symlink into /usr/lib/claude-desktop/, hicolor icons, and a freedesktop
	# .desktop (Exec is relative, so no path rewriting) that registers the
	# claude:// scheme handler. Install the tree verbatim, preserving the symlink.
	cp -a usr "${ED}"/ || die

	if use suid-sandbox; then
		# Electron's setuid sandbox helper must be owned by root and setuid so
		# the renderer can enter its namespace sandbox.
		fperms 4711 /usr/lib/claude-desktop/chrome-sandbox
	else
		# Without the setuid helper, launch with --no-sandbox. Replace the plain
		# symlink with a wrapper so the bare 'claude-desktop' command and the
		# .desktop entry (Exec=claude-desktop) both pick up the flag.
		rm "${ED}"/usr/bin/claude-desktop || die
		cat > "${T}"/claude-desktop <<-EOF || die
			#!/bin/sh
			exec /usr/lib/claude-desktop/claude-desktop --no-sandbox "\$@"
		EOF
		dobin "${T}"/claude-desktop
	fi
}

pkg_postinst() {
	xdg_pkg_postinst
	if ! use suid-sandbox; then
		elog "Built with USE=-suid-sandbox: Claude launches with --no-sandbox."
		elog "For the hardened Electron sandbox instead, enable USE=suid-sandbox"
		elog "(installs a setuid-root chrome-sandbox helper)."
	fi
	if ! use cowork; then
		elog "Claude's local VM sandbox (computer use) needs QEMU + OVMF:"
		elog "    enable USE=cowork to pull them in."
	fi
}
