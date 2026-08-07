# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DISTUTILS_USE_PEP517=setuptools
PYTHON_COMPAT=( python3_{11..14} )

inherit distutils-r1 git-r3

DESCRIPTION="GeST — a YaST-style system administration tool for Gentoo"
HOMEPAGE="https://github.com/k5blazerfl/GeST"
EGIT_REPO_URI="https://github.com/k5blazerfl/GeST.git"

LICENSE="GPL-2+"
SLOT="0"
KEYWORDS=""

# portage: the query API. PyGObject: GLib/Gio for the root backend.
# textual + dbus-next: the TUI frontend and its async D-Bus client.
RDEPEND="
	sys-apps/portage[${PYTHON_USEDEP}]
	dev-python/pygobject:3[${PYTHON_USEDEP}]
	dev-python/textual[${PYTHON_USEDEP}]
	dev-python/dbus-next[${PYTHON_USEDEP}]
	sys-auth/polkit
	sys-apps/dbus
"

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
}
