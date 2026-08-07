"""Frontend-agnostic administration modules.

Each module owns a domain (software, services, users, …) and exposes a plain
Python API: read current state, build a change *plan*, and apply it. Reads run
in-process as the invoking user; anything that mutates the system is routed
through :mod:`gest.core.software.backend_client` to the privileged backend.
"""
