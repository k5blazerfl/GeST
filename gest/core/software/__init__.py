"""Software-management module — the Portage front for GeST.

Queries use the in-process Portage Python API (fast, structured, no output
scraping). Mutations (building/merging, editing /etc/portage) are the job of
the privileged backend and are invoked through ``backend_client``.

Note: this package ``__init__`` deliberately imports nothing, so the pure-logic
submodules (``news``, ``preview``) stay importable without Portage — which lets
that subset of the test suite run on non-Gentoo CI.
"""
