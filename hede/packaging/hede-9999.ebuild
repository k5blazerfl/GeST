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
	KEYWORDS="~amd64"
fi

LICENSE="GPL-3"
SLOT="0"

# Qt 6 Widgets + Wayland, the QtWayland client (foreign-toplevel protocol
# bindings + qtwaylandscanner), and the layer-shell binding (the KF6 micro-dep).
DEPEND="
	dev-qt/qtbase:6[widgets,wayland]
	dev-qt/qtwayland:6
	kde-frameworks/layer-shell-qt:6
"
# Runtime: the compositor HeDE drives and the default terminal helm-panel spawns.
RDEPEND="
	${DEPEND}
	gui-wm/labwc
	gui-apps/foot
"

src_test() {
	cmake_src_test
}

pkg_postinst() {
	elog "HeDE installed. Select 'HeDE' at your Wayland greeter, or run:"
	elog "    helm-session"
	elog "Per-user config lives at ~/.config/hede/hede.conf"
}
