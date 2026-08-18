"""Flotilla — a Helm/HeDE VM manager over libvirt/QEMU/KVM.

Phase 1 is the **pure core**: the vessel model, the libvirt domain-XML compiler,
and the Gentoo prerequisites table — all CI-testable with no libvirt. Defining and
running a domain (the host backend) and the Gangway bridge come later. See
``docs/design/flotilla.md``.
"""
