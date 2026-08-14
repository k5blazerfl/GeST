"""Tests for the Software module's pure list label (gest.qt.software)."""

from gest.core.software.model import SearchResult
from gest.qt.software import search_result_label


def test_label_installed():
    r = SearchResult(cp="www-client/firefox", best_version="128.0", installed_version="127.0")
    assert search_result_label(r) == "www-client/firefox  128.0  ✓"


def test_label_not_installed():
    r = SearchResult(cp="app-editors/vim", best_version="9.1", installed_version=None)
    assert search_result_label(r) == "app-editors/vim  9.1"


def test_label_no_version():
    r = SearchResult(cp="x/y", best_version="", installed_version=None)
    assert search_result_label(r) == "x/y"
