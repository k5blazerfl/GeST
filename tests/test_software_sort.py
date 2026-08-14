"""CI-safe tests for the software list ordering (pure, no Portage)."""

from gest.core.software.sortpkg import SORTS, order_by


def test_name_mode_orders_by_cp():
    cps = ["b/z", "a/a", "a/b"]
    repos = ["gentoo", "gentoo", "x"]
    assert order_by(cps, repos, "name") == [1, 2, 0]         # a/a, a/b, b/z


def test_unknown_mode_falls_back_to_name():
    cps = ["b/z", "a/a"]
    assert order_by(cps, ["", ""], "whatever") == [1, 0]


def test_repo_mode_groups_by_repository_then_cp():
    cps = ["a/one", "a/two", "b/one", "c/one"]
    repos = ["gentoo", "gest", "gentoo", "gest"]
    # gentoo group (a/one, b/one) before gest group (a/two, c/one); cp within each
    assert order_by(cps, repos, "repo") == [0, 2, 1, 3]


def test_repo_mode_puts_missing_repo_last():
    cps = ["a/x", "b/y", "c/z"]
    repos = ["", "gentoo", ""]
    order = order_by(cps, repos, "repo")
    assert order[0] == 1                                     # gentoo first
    assert set(order[1:]) == {0, 2}                          # the repo-less ones last
    assert order[1:] == [0, 2]                               # …and cp-ordered among themselves


def test_sorts_catalogue():
    assert [s[0] for s in SORTS] == ["name", "repo"]
    assert dict(SORTS)["repo"] == "Repository"
