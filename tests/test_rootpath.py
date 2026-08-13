"""CI-safe tests for the target-root seam (:mod:`gest.core.rootpath`).

Pure path resolution and the confined-root guard — no filesystem, no bus, no
privilege. These pin the invariant every file-writing backend relies on: a
``root`` of ``/`` is a perfect no-op, and a target root is confined to the
``/mnt|/media|/run/media`` prefixes.
"""

import pytest

from gest.core import rootpath


def test_valid_config_root_accepts_running_system_and_confined_targets():
    assert rootpath.valid_config_root("/")
    assert rootpath.valid_config_root("/mnt/gentoo")
    assert rootpath.valid_config_root("/media/usb")
    assert rootpath.valid_config_root("/run/media/u/disk")


def test_valid_config_root_rejects_unsafe_roots():
    for bad in ("/home", "/etc", "/mnt", "/mnt/../etc", "relative", ""):
        assert not rootpath.valid_config_root(bad), bad


def test_resolve_is_a_noop_for_running_system():
    assert rootpath.resolve("/", "/etc/hosts") == "/etc/hosts"
    assert rootpath.resolve("", "/etc/hosts") == "/etc/hosts"


def test_resolve_maps_under_target_root():
    assert rootpath.resolve("/mnt/gentoo", "/etc/conf.d/net") == "/mnt/gentoo/etc/conf.d/net"


def test_resolve_tolerates_a_trailing_slash_on_root():
    assert rootpath.resolve("/mnt/gentoo/", "/etc/x") == "/mnt/gentoo/etc/x"


def test_is_target_distinguishes_running_system_from_target():
    assert rootpath.is_target("/") is False
    assert rootpath.is_target("") is False
    assert rootpath.is_target("/mnt/gentoo") is True


def test_guard_config_root_raises_on_bad_root_and_passes_on_good():
    with pytest.raises(ValueError):
        rootpath.guard_config_root("/home")
    rootpath.guard_config_root("/")
    rootpath.guard_config_root("/mnt/gentoo")
