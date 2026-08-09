"""Unified Portage configuration core.

Everything under ``/etc/portage/`` — ``make.conf``, ``repos.conf/``,
``binrepos.conf/``, and the ``package.*`` drop-ins — is read, modelled, and
rendered here so the frontend modules (software, makeconf, repos, and the
binhost / license / cpuflags surfaces to come) share one implementation.

Layering:

* :mod:`gest.core.portage.codec` — three pure, I/O-free grammars
  (``shell`` assignments, ``ini`` sections, ``atomfile`` atom-keyed lines).
* :mod:`gest.core.portage.paths` — the single source of truth for file
  locations, honouring ``PORTAGE_CONFIGROOT``.
* :mod:`gest.core.portage.write` — the :class:`~gest.core.portage.write.ConfigWrite`
  value type the privileged backend applies.

See ``docs/design/portage-config-core.md`` for the full design.
"""
