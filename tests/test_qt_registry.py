"""Tests for the Qt frontend module registry (Qt-free)."""

from gest.qt.registry import ModuleDescriptor, Registry


def test_grouping_follows_category_order_then_title():
    r = Registry()
    r.register(ModuleDescriptor("b", "Bravo", "System"), lambda: None)
    r.register(ModuleDescriptor("a", "Alpha", "System"), lambda: None)
    r.register(ModuleDescriptor("n", "Net", "Network"), lambda: None)
    grouped = r.by_category()
    # System precedes Network in the shared CATEGORY_ORDER (not alphabetical).
    assert list(grouped.keys()) == ["System", "Network"]
    assert [e.descriptor.title for e in grouped["System"]] == ["Alpha", "Bravo"]


def test_unknown_category_sorts_after_known_ones():
    r = Registry()
    r.register(ModuleDescriptor("z", "Zeta", "Zzz-Unlisted"), lambda: None)
    r.register(ModuleDescriptor("s", "Soft", "Software"), lambda: None)
    assert list(r.by_category().keys()) == ["Software", "Zzz-Unlisted"]


def test_same_id_replaces():
    r = Registry()
    r.register(ModuleDescriptor("x", "One", "C"), lambda: 1)
    r.register(ModuleDescriptor("x", "Two", "C"), lambda: 2)
    assert len(r.entries()) == 1
    assert r.entries()[0].descriptor.title == "Two"


def test_factory_not_called_by_registry():
    calls = []
    r = Registry()
    r.register(ModuleDescriptor("x", "X", "C"), lambda: calls.append(1))
    r.by_category()
    r.entries()
    assert calls == []  # lazy: registry never instantiates widgets
