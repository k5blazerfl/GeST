"""The unprivileged session-bus read service for the desktop shell (HeDE).

``org.gentoo.gest.Shell`` exposes read-only ``core`` data (starting with the
pending ``@world`` update count) plus change signals, so the C++ shell can show
indicators without re-implementing ``core``. Reads only; mutations still go
through the polkit-gated system backend. See ``docs/design/hede-phase2.md`` §2.
"""
