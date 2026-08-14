"""The GeST Qt frontend (PySide6) — a second renderer over ``core``.

A modular Control Center: each module is a widget + a descriptor, hosted by
``gest-settings`` standalone and (later) embedded in the HeDE shell. The registry
is Qt-free so ordering/grouping is unit-testable without a display. See
``docs/design/qt-frontend.md``. Gate lifted 2026-08-14.
"""
