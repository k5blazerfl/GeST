"""Drydock — Wine/Proton apps as first-class HeDE citizens (docs/design/drydock.md).

The GeST/core (Python) side: the **bottle** model, the pure **launch pipeline**
(env + wrapped argv), the config store, and the Gentoo **prerequisites** checker.
Desktop integration is via :mod:`gest.core.customs`; the runtime — Wine, Proton
(through ``umu-run``), DXVK/VKD3D, gamescope — is adopted, never reinvented.

All pure/CI-testable. Creating prefixes, running installers, and actually
launching apps need real Wine/Proton/GPU, so live execution is validated on a
host (like Gangway's client and the keyring daemon's bus). No polkit for bottle
management; only the prerequisite *apply* (USE/multilib/packages) routes through
GeST's existing polkit'd software core.
"""
