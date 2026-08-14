"""Ordering for the software package list — a pure helper, no Portage.

The software screen keeps its rows in parallel lists (cps, repos, …). Rather than
sort those lists in the screen, it asks here for an *order* (a list of row indices)
and applies it to every parallel list at once. Keeping this a pure function of the
cp/repo lists makes the sort logic unit-testable without a live Portage tree.
"""

from __future__ import annotations

from collections.abc import Sequence

SORTS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("repo", "Repository"),
)

# Rows with no known repository sort last (installed packages always have one;
# a few third-party/tree hits may not).
_NO_REPO_KEY = "￿"


def order_by(cps: Sequence[str], repos: Sequence[str], mode: str) -> list[int]:
    """Return row indices ordering ``cps``/``repos`` by ``mode``.

    ``mode`` ``"repo"`` groups by repository (packages with no repo last), then by
    cp within a repo; anything else (``"name"``) orders by cp. The sort is stable
    and total, so the same inputs always give the same order.
    """
    indices = range(len(cps))
    if mode == "repo":
        return sorted(indices, key=lambda i: ((repos[i] or _NO_REPO_KEY), cps[i]))
    return sorted(indices, key=lambda i: cps[i])
