"""Software module logic: a pure list label (search results)."""

from __future__ import annotations

from gest.core.software.model import SearchResult


def search_result_label(result: SearchResult) -> str:
    """One row: 'category/package  best-version  ✓' (✓ = installed)."""
    mark = "  ✓" if result.installed else ""
    version = f"  {result.best_version}" if result.best_version else ""
    return f"{result.cp}{version}{mark}"
