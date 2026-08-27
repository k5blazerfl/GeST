# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

inherit cmake

DESCRIPTION="HeDE — the Helm Desktop Environment (Qt/Wayland shell for Gentoo)"
HOMEPAGE="https://github.com/k5blazerfl/HeDE"

if [[ ${PV} == 9999 ]]; then
	inherit git-r3
	EGIT_REPO_URI="https://github.com/k5blazerfl/HeDE.git"
else
	SRC_URI="https://github.com/k5blazerfl/HeDE/archive/refs/tags/v${PV}.tar.gz -> ${P}.tar.gz"
	S="${WORKDIR}/HeDE-${PV}" # GitHub archives extract to <RepoName>-<version>
	KEYWORDS="~amd64"
fi

LICENSE="GPL-3"
SLOT="0"
IUSE="wayfire" # opt-in "effects" compositor profile

# Qt 6 Widgets + Wayland, the QtWayland client (foreign-toplevel protocol
# bindings + qtwaylandscanner), and the layer-shell binding. layer-shell-qt is
# mid-move between categories in ::gentoo (kde-plasma → kde-frameworks); accept
# either so the ebuild resolves whatever the tree snapshot ships (an unsatisfiable
# atom here silently makes emerge fall back to the old binpkg — see the bug note).
DEPEND="
	dev-qt/qtbase:6[dbus,widgets,wayland]
	dev-qt/qtwayland:6
	|| ( kde-plasma/layer-shell-qt:6 kde-frameworks/layer-shell-qt:6 )
	dev-libs/libvterm
"
# Runtime: the compositor HeDE drives, the default terminal helm-panel spawns,
# GeST (the Control Center + the org.gentoo.gest.Shell read seam), and a polkit
# agent for the session (auth prompts for GeST's polkit-gated backend).
RDEPEND="
	${DEPEND}
	gui-wm/labwc
	gui-apps/foot
	app-admin/gest
	lxqt-base/lxqt-policykit
	media-video/wireplumber
	gui-apps/swaylock
	gui-apps/swayidle
	wayfire? ( gui-wm/wayfire )
"
# The Wayland protocol code generator, needed at build time by Qt6WaylandClient
# (find_package fails without it). ::gentoo split it out of dev-libs/wayland into
# its own build-tool package, so it must be pulled explicitly.
BDEPEND="dev-util/wayland-scanner"

src_test() {
	cmake_src_test
}

src_install() {
	cmake_src_install
	# The effects profile (wayfire session + config) only ships with USE=wayfire.
	if ! use wayfire; then
		rm -f "${ED}"/usr/share/wayland-sessions/hede-effects.desktop || die
		rm -rf "${ED}"/usr/share/hede/wayfire || die
	fi
}

pkg_postinst() {
	elog "HeDE installed. Select 'HeDE' at your Wayland greeter, or run:"
	elog "    helm-session"
	elog "Per-user config lives at ~/.config/hede/hede.conf"
}
