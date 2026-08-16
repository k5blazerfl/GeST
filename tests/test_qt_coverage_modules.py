"""Tests for the coverage-parity Qt modules: pure helpers + registration.

The widgets themselves read real system state and mutate through polkit, so —
like the other Qt-module tests — we cover the pure logic and assert the modules
register into the shared taxonomy with the expected category.
"""

from types import SimpleNamespace

from gest.qt.app import build_registry
from gest.qt.hwflags import format_flags, parse_flags
from gest.qt.net import parse_tokens
from gest.qt.software import (
    format_cleanup_plan,
    format_news_content,
    format_update_plan,
    news_item_label,
)


def test_format_and_parse_flags_roundtrip():
    assert format_flags(["mmx", "sse", "sse2"]) == "mmx sse sse2"
    assert format_flags([]) == ""
    assert parse_flags("mmx  sse\tsse2") == ["mmx", "sse", "sse2"]
    assert parse_flags("sse sse mmx") == ["sse", "mmx"]  # order-preserving dedup
    assert parse_flags("   ") == []


def test_parse_tokens():
    assert parse_tokens("1.1.1.1  9.9.9.9") == ["1.1.1.1", "9.9.9.9"]
    assert parse_tokens("") == []


def _change(cp, old, new, action):
    return SimpleNamespace(cp=cp, old_version=old, new_version=new, action=action)


class _UpdatePlan:
    def __init__(self, changes, ok=True, error=""):
        self.changes, self.ok, self.error = changes, ok, error

    def counts(self):
        out: dict[str, int] = {}
        for change in self.changes:
            out[change.action] = out.get(change.action, 0) + 1
        return out


def test_format_update_plan():
    assert format_update_plan(_UpdatePlan([])) == "@world is up to date."
    assert format_update_plan(_UpdatePlan([], ok=False, error="boom")) == "boom"
    out = format_update_plan(_UpdatePlan([
        _change("app/foo", "1", "2", "update"),
        _change("app/bar", "", "3", "new"),
    ]))
    assert "app/foo  1 → 2" in out
    assert "app/bar  3" in out
    assert "2 change(s)" in out


class _CleanupPlan:
    def __init__(self, orphans, ok=True, error=""):
        self.orphans, self.ok, self.error = orphans, ok, error

    @property
    def total_size(self):
        return sum(o.size for o in self.orphans)


def test_format_cleanup_plan():
    assert format_cleanup_plan(_CleanupPlan([])) == "Nothing to clean up."
    assert format_cleanup_plan(_CleanupPlan([], ok=False, error="nope")) == "nope"
    out = format_cleanup_plan(_CleanupPlan([SimpleNamespace(cp="app/foo", version="1", size=1024)]))
    assert "app/foo-1" in out
    assert "1 package(s)" in out


def test_news_helpers():
    unread = SimpleNamespace(unread=True, date="2026-01-01", title="Hello")
    read = SimpleNamespace(unread=False, date="2026-01-02", title="Bye")
    assert news_item_label(unread).startswith("●") and "Hello" in news_item_label(unread)
    assert news_item_label(read).startswith(" ")
    content = SimpleNamespace(headers=[("Title", "T"), ("Author", "A")], body=["l1", "l2"])
    rendered = format_news_content(content)
    assert "Title: T" in rendered and "l1" in rendered


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
        "world": "Software",
        "update": "Software",
        "depclean": "Software",
        "sync": "Software",
        "news": "Software",
        "prefs": "Software",
    }
    for module_id, category in expected.items():
        assert module_id in by_id, f"{module_id} is not registered"
        assert by_id[module_id].category == category
