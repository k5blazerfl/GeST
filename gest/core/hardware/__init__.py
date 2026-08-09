"""Hardware information module core.

A read-only inventory of the machine: CPU, memory, storage, PCI/USB devices,
and DMI/firmware identity. Everything is gathered as the invoking user — no
root, no D-Bus, no polkit — from `lscpu`/`lspci`/`lsusb`/`lsblk`, /proc/meminfo,
and the world-readable attributes under /sys/class/dmi/id. Each parser is a pure
function over command/file text, so it's CI-testable without the real hardware.
"""
