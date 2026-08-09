"""The three pure file grammars used under ``/etc/portage/``.

Each codec parses text to a model and renders a model back to text with no I/O
and no dependency on the ``portage`` module, so they are trivially testable:

* :mod:`~gest.core.portage.codec.shell` — ``make.conf`` ``NAME="value"`` assignments.
* :mod:`~gest.core.portage.codec.ini` — ``repos.conf`` / ``binrepos.conf`` sections.
* :mod:`~gest.core.portage.codec.atomfile` — ``package.*`` atom-keyed lines.
"""
