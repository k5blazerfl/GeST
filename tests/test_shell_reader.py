"""Tests for the shell read helpers (gest.shell.reader)."""

from gest.shell.reader import update_count


def test_update_count_uses_injected_reader():
    assert update_count(lambda: [object(), object(), object()]) == 3


def test_update_count_zero():
    assert update_count(lambda: []) == 0
