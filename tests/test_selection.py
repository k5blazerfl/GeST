"""Unit tests for the pending-changes Selection model (pure, CI-safe)."""

from gest.core.software.selection import Selection


def test_toggle_install_adds_and_removes():
    sel = Selection()
    assert sel.is_empty
    sel.toggle_install("app-editors/vim")
    assert sel.is_marked("app-editors/vim")
    assert sel.mark_of("app-editors/vim") == "install"
    sel.toggle_install("app-editors/vim")
    assert not sel.is_marked("app-editors/vim")
    assert sel.is_empty


def test_install_atoms_sorted_and_summary():
    sel = Selection()
    sel.mark_install("sys-apps/portage")
    sel.mark_install("app-editors/vim")
    assert sel.install_atoms() == ["app-editors/vim", "sys-apps/portage"]
    assert sel.summary() == "2 to install"
    assert len(sel) == 2


def test_clear_and_empty_summary():
    sel = Selection()
    assert sel.summary() == "no changes"
    sel.mark_install("x/y")
    sel.clear()
    assert sel.is_empty and sel.summary() == "no changes"


def test_remove_marks_and_mixed_summary():
    sel = Selection()
    sel.mark_install("app-editors/vim")
    sel.mark_remove("app-misc/hello")
    assert sel.install_atoms() == ["app-editors/vim"]
    assert sel.remove_atoms() == ["app-misc/hello"]
    assert sel.summary() == "1 to install · 1 to remove"


def test_toggle_remove_overrides_install():
    sel = Selection()
    sel.toggle_install("x/y")
    assert sel.mark_of("x/y") == "install"
    sel.toggle_remove("x/y")  # switch the same package to remove
    assert sel.mark_of("x/y") == "remove"
    assert sel.install_atoms() == [] and sel.remove_atoms() == ["x/y"]
    sel.toggle_remove("x/y")  # toggling remove again clears it
    assert sel.is_empty
