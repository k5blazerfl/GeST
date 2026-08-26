"""Curated *default application* catalogs (browser first).

The cockpit's answer to "which app handles the web/mail/media" — a short,
hand-picked list per capability, not a searchable store. Pure and CI-testable:
each module here is a catalog plus the ``xdg-settings`` argv to read/set the
default; a thin caller (the Qt module) runs the command and installs the atom
through the Software backend.
"""
