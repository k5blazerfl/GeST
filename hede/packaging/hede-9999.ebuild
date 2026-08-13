# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

inherit cmake git-r3

DESCRIPTION="HeDE — the Helm Desktop Environment (Phase 0 skeleton)"
HOMEPAGE="https://github.com/k5blazerfl/hede"
EGIT_REPO_URI="https://github.com/k5blazerfl/hede.git"

LICENSE="GPL-3"
SLOT="0"
KEYWORDS=""

DEPEND="
	dev-qt/qtbase:6[widgets,wayland]
	kde-frameworks/layer-shell-qt:6
"
RDEPEND="
	${DEPEND}
	gui-wm/labwc
	gui-apps/foot
"
BDEPEND="dev-qt/qtbase:6[test]"

src_test() {
	cmake_src_test
}
