"""License acceptance configuration.

Two surfaces from the Handbook's licensing step:

* the global ``ACCEPT_LICENSE`` in ``make.conf`` (e.g.
  ``-* @FREE @BINARY-REDISTRIBUTABLE``);
* per-package acceptance in ``/etc/portage/package.license/`` — atom-keyed
  lines like ``app-arch/unrar unRAR``.

GeST owns ``package.license/gest`` (leaving any hand-written fragment alone),
edits it through the shared ``atomfile`` codec, and applies everything via the
Portage ``WriteConfig`` RPC. See ``docs/design/portage-config-core.md``.
"""
