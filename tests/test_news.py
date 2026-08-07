"""Tests for the Portage news reader."""

import pytest

from gest.core.software import news


def test_list_news_parses_unread_and_read():
    text = (
        "News items:\n"
        "  [1]   N  2018-08-07  Migration required for OpenSSH with LDAP\n"
        "  [2]      2019-05-23  Change of ACCEPT_LICENSE default\n"
    )
    items = news.list_news(lambda argv: text)
    assert len(items) == 2
    assert items[0].number == 1 and items[0].unread and "OpenSSH" in items[0].title
    assert items[1].number == 2 and not items[1].unread


def test_read_news_uses_number():
    seen = {}

    def runner(argv):
        seen["argv"] = argv
        return "the news body\n"

    assert news.read_news(5, runner) == "the news body"
    assert seen["argv"] == ["eselect", "news", "read", "5"]


def test_mark_read_argv_valid_selectors():
    assert news.mark_read_argv("all") == ["eselect", "news", "read", "all"]
    assert news.mark_read_argv("new") == ["eselect", "news", "read", "new"]
    assert news.mark_read_argv("7") == ["eselect", "news", "read", "7"]
    assert news.mark_read_argv(" 7 ") == ["eselect", "news", "read", "7"]
    assert news.mark_read_argv("3", "/usr/bin/eselect")[0] == "/usr/bin/eselect"


def test_mark_read_argv_rejects_bad_selectors():
    for bad in ("", "0", "-1", "foo", "3; rm -rf /", "all news", "1.2"):
        with pytest.raises(ValueError):
            news.mark_read_argv(bad)
