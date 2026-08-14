# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DISTUTILS_USE_PEP517=setuptools
PYTHON_COMPAT=( python3_{11..14} )

inherit distutils-r1

DESCRIPTION="GeST — a YaST-style system administration tool for Gentoo"
HOMEPAGE="https://github.com/k5blazerfl/GeST"
SRC_URI="https://github.com/k5blazerfl/GeST/archive/refs/tags/v${PV}.tar.gz -> ${P}.tar.gz"
S="${WORKDIR}/GeST-${PV}"

LICENSE="GPL-2+"
SLOT="0"
KEYWORDS="~amd64 ~arm64"

IUSE="qt"

# portage: the query API. PyGObject: GLib/Gio for the root backend.
# urwid + dbus-next: the TUI frontend and its async D-Bus client.
# qt: PySide6 for the optional Qt/Wayland Control Center (gest-settings), the
# frontend HeDE embeds; the widgets module set is all the frontend needs.
RDEPEND="
	sys-apps/portage[${PYTHON_USEDEP}]
	dev-python/pygobject:3[${PYTHON_USEDEP}]
	dev-python/urwid[${PYTHON_USEDEP}]
	dev-python/dbus-next[${PYTHON_USEDEP}]
	sys-auth/polkit
	sys-apps/dbus
	qt? ( dev-python/pyside:6[${PYTHON_USEDEP},widgets] )
"

# Test suite: pytest with the asyncio plugin (pyproject sets asyncio_mode = auto).
distutils_enable_tests pytest
BDEPEND+=" test? ( dev-python/pytest-asyncio[${PYTHON_USEDEP}] )"

src_install() {
	distutils-r1_src_install

	# System integration files (outside site-packages).
	insinto /usr/share/dbus-1/system.d
	doins data/org.gentoo.gest.conf

	insinto /usr/share/dbus-1/system-services
	doins data/org.gentoo.gest.service

	insinto /usr/share/polkit-1/actions
	doins data/org.gentoo.gest.policy

	# Root backend launcher used by D-Bus activation. Unlike the dev
	# install-backend.sh, this runs the *installed* package (system python),
	# not a working tree.
	exeinto /usr/libexec
	newexe - gest-backend <<-_LAUNCHER_
		#!/bin/sh
		exec "${EPREFIX}/usr/bin/python3" -m gest.backend.service "\$@"
	_LAUNCHER_
}

pkg_postinst() {
	elog "GeST installed. Launch the TUI with: gest"
	elog "The privileged backend bus-activates on first use (polkit-gated)."
	elog "If D-Bus doesn't see the new policy yet: rc-service dbus reload"
	if use qt; then
		elog "Qt Control Center enabled: run 'gest-settings' (also embedded by HeDE)."
	fi
}
