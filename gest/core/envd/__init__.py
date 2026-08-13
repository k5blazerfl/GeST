"""env.d module core — environment variables in /etc/env.d/.

Manages a single GeST-owned drop-in (``/etc/env.d/99gest``) of ``VAR="value"``
assignments. ``env-update`` concatenates every /etc/env.d/ file into
/etc/profile.env (and ld.so.conf), so this is the general, env-update-aware way
to set login-shell environment variables. Parsing/validation/rendering are pure
and CI-testable; the polkit-gated backend writes the drop-in and runs
``env-update``.
"""
