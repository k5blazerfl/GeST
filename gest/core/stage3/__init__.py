"""Stage3 module core: select, verify and unpack a Gentoo stage3 tarball.

An installer building block — the first genuinely-new step of the system
installer (see ``docs/design/installer.md``). It resolves a stage3 variant from a
Gentoo mirror, downloads it, **verifies its integrity** against the mirror's
``.DIGESTS`` (BLAKE2B + SHA512, the two algorithms Gentoo publishes), best-effort
checks its GPG signature, and unpacks it into a confined install target root.

Split like every other module so the dangerous parts are inspectable:

* ``model``    — the offered variants and a resolved selection (pure data);
* ``index``    — pure parsers + URL builders for the mirror's
  ``latest-stage3-*.txt`` index, plus a thin unprivileged ``fetch_text`` for the
  small index/DIGESTS files;
* ``verify``   — pure hashing + ``.DIGESTS`` parsing and the mandatory
  integrity check (``verify_hashes``);
* ``commands`` — pure, validated argv builders (``tar`` unpack, ``gpg --verify``);
* ``backend_client`` — the async client driving the streaming ``Stage3`` backend.

Safety: the unpack target root is confined to the ``/mnt`` / ``/media`` /
``/run/media`` prefixes by ``core.disk.mount.guard_target_root`` (it rejects
``/``), and hash verification is mandatory and must pass *before* any unpack —
unpacking a stage3 over the running system would destroy it.
"""
