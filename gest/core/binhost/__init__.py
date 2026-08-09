"""Binary package host (binhost) configuration.

A binhost lets Portage download pre-built binary packages instead of compiling
from source. Configuring one is the Handbook's "binary package host" step:

* declare the host(s) in ``/etc/portage/binrepos.conf/`` (INI);
* enable ``getbinpkg`` and ``binpkg-request-signature`` in ``FEATURES``;
* run ``getuto`` once to set up the binary-package trust keyring.

GeST owns ``binrepos.conf/gest.conf`` (leaving any hand-written fragment
alone), renders it through the shared INI codec, and applies everything via the
Portage ``WriteConfig`` RPC. See ``docs/design/portage-config-core.md``.
"""
