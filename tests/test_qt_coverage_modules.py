"""Tests for the coverage-parity Qt modules: pure helpers + registration.

The widgets themselves read real system state and mutate through polkit, so —
like the other Qt-module tests — we cover the pure logic and assert the modules
register into the shared taxonomy with the expected category.
"""

from gest.qt.app import build_registry
from gest.qt.hwflags import format_flags, parse_flags
from gest.qt.net import parse_tokens


def test_format_and_parse_flags_roundtrip():
    assert format_flags(["mmx", "sse", "sse2"]) == "mmx sse sse2"
    assert format_flags([]) == ""
    assert parse_flags("mmx  sse\tsse2") == ["mmx", "sse", "sse2"]
    assert parse_flags("sse sse mmx") == ["sse", "mmx"]  # order-preserving dedup
    assert parse_flags("   ") == []


def test_parse_tokens():
    assert parse_tokens("1.1.1.1  9.9.9.9") == ["1.1.1.1", "9.9.9.9"]
    assert parse_tokens("") == []


def test_new_modules_register_under_shared_taxonomy():
    by_id = {e.descriptor.id: e.descriptor for e in build_registry().entries()}
    expected = {
        "hostname": "System",
        "locale": "System",
        "keymap": "System",
        "consolefont": "System",
        "hwflags": "Hardware",
        "dns": "Network",
        "hosts": "Network",
    }
    for module_id, category in expected.items():
        assert module_id in by_id, f"{module_id} is not registered"
        assert by_id[module_id].category == category
